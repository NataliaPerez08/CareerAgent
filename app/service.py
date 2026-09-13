"""Structured evaluation pipeline.

LLM interprets, code decides. Exactly three model calls, none of them in a
tool loop (the pipeline agent has no tools; every deterministic calculation
runs in Python):

    Resume ──> LLM extraction (call 1) ──> CandidateProfile
    Job    ──> LLM extraction (call 2) ──> JobRequirements
                       ↓
              normalize_requirements (deterministic, analyze_job core)
                       ↓
              build_match_result (deterministic)
                       ↓
              decide_recommendation (deterministic policy)
                       ↓
              build_strengths / build_skill_gaps (deterministic)
                       ↓
              LLM plan + explanation (call 3) ──> code validation
                       ↓
              EvaluationResult

Every LLM step runs on a fresh agent so evaluations never share
conversation state.

Each pipeline stage records its duration into an EvaluationTimings
collector and logs a human-readable line, and the whole pipeline emits a
single structured JSON line at the end (durations plus counters: model
calls, event-loop cycles, tool calls, tokens). Both are visible locally
and in Amazon CloudWatch when deployed to AgentCore, so latency
breakdowns are always available and never include resume/job content or
prompts.
"""

import logging
from collections.abc import Callable

import botocore.exceptions
from strands import Agent

from app.agent import build_pipeline_agent
from app.career import (
    attach_preparation_steps,
    build_preparation_plan,
    build_skill_gaps,
    build_strengths,
    normalize_interview_topics,
)
from app.matching import (
    build_match_result,
    clean_reasoning,
    normalize_requirements,
    validate_evidence,
)
from app.policy import DEFAULT_POLICY, decide_recommendation
from app.resume_parser import parse_resume
from app.schemas import (
    CandidateProfile,
    CareerPlan,
    EvaluationResult,
    JobRequirements,
    MatchResult,
    Recommendation,
    SkillGap,
)
from app.timing import EvaluationTimings

logger = logging.getLogger(__name__)


def _stage_stopped(name: str, timings: EvaluationTimings) -> None:
    logger.info("Evaluation stage complete: %s (%.2fs)", name, timings.get_ms(name) / 1000.0)


def _notify(on_stage, name: str) -> None:
    if on_stage is not None:
        on_stage(name)


PROFILE_EXTRACTION_PROMPT = """Extract the candidate profile from the resume below.

Return:
- skills: technical skills evidenced in the resume, using short canonical
  names (for example "rest api", "postgresql"), not long phrases.
- years_of_experience: total years of professional software development
  experience stated in the resume, or null if not stated.
- evidence: short verbatim quotes from the resume that prove the skills
  and experience. Every quote must appear word-for-word in the resume.

Never invent skills, experience, or evidence that is not in the resume.

RESUME
------
{resume}"""

REQUIREMENTS_EXTRACTION_PROMPT = """Extract the requirements from the job description below.

Return:
- required_skills: skills the job description explicitly lists as required,
  for example under a "Requirements" heading or with words like "requires".
  A skill listed under a "Requirements" heading is required, never unknown.
  Extract every item from every explicit requirements list; never drop or
  ignore listed requirements.
  Use short canonical skill names, never phrases copied verbatim:
  "AWS experience" is "aws", "Familiarity with CI/CD" is "ci/cd",
  "REST API development" is "rest api".
  Never list experience durations (for example "1+ year of experience")
  as skills: durations belong in min_years_experience only.
- preferred_skills: skills explicitly listed as preferred or nice-to-have,
  using short canonical names.
- critical_skills: only skills the description explicitly marks with words
  like "must have", "mandatory", or "non-negotiable". A plain
  "Requirements" list means required, NOT critical. The words "must
  have", "mandatory" and "non-negotiable" are classification cues,
  never skill names.
- unknown_requirements: skills or requirements mentioned whose
  required/preferred status is NOT explicitly stated. A skill that
  appears only in prose describing the role or the company stack,
  outside any requirements list and without required/preferred
  wording, is unknown — never required, never dropped entirely.
- min_years_experience: minimum years of experience explicitly required,
  or null if not stated.

Never infer that a requirement is optional, preferred, mandatory or
non-mandatory unless the job description explicitly says so. When in
doubt, put the skill in unknown_requirements.

JOB DESCRIPTION
---------------
{job_description}"""

CAREER_PLAN_PROMPT = """You are preparing a candidate for a job decision and interview.

The deterministic analysis below was computed by code. Never recompute,
contradict or re-rank any of it.

Recommendation: {recommendation}
Score: {score}
Matched required skills: {matched_skills}
Matched preferred skills: {matched_preferred_skills}
Missing critical skills: {missing_critical_skills}
Missing required skills: {missing_required_skills}
Missing preferred skills: {missing_preferred_skills}
Unknown requirements: {unknown_requirements}
Experience match: {experience_display}
Resume evidence: {evidence}
Strengths: {strengths}
Skill gaps to prepare: {skill_gaps}

Return:
- reasoning: explain the recommendation to the candidate in 3 to 6
  sentences. Ground every claim in the analysis above and the resume
  evidence. Never invent experience or skills. If something is unknown,
  say so. Mention the most important skill gaps and how to prepare them.
- interview_topics: 3 to 8 concrete topics to prepare for this job's
  interview. Focus on matched skills (the interview will probe them)
  and missing skills (weak points to study first).
- gap_preparation: for each missing skill listed above, 2 to 5 concrete
  preparation steps in learning order. Only include skills from the
  missing lists.

Never mention candidate experience that is not listed here.
Never add skills for the candidate."""


def _format_experience(experience_match: bool | None) -> str:
    if experience_match is True:
        return "yes"
    if experience_match is False:
        return "no"
    return "unknown (not stated or not verifiable)"


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _record_model_call(
    timings: EvaluationTimings | None,
    result,
    output_model=None,
) -> None:
    """Record how many model round-trips and tool calls one agent call needed.

    A single-shot structured call costs 1 cycle; an agent loop that calls
    tools costs more. Counting them makes the loop cost of the pipeline
    measurable instead of assumed.

    Strands registers the structured-output schema as an internal pseudo-tool
    (named after the schema class). That is not an agent tool call — ``tools``
    on the pipeline agent is empty — so it is excluded from ``tool_calls``.
    """
    if timings is None:
        return
    timings.count("llm_calls")
    metrics = getattr(result, "metrics", None)
    if metrics is None:
        return
    timings.count("llm_cycles", getattr(metrics, "cycle_count", 0) or 0)
    schema_name = output_model.__name__ if output_model is not None else ""
    tool_metrics = getattr(metrics, "tool_metrics", None) or {}
    real_tool_calls = sum(
        getattr(tool, "call_count", 0) or 0
        for name, tool in tool_metrics.items()
        if name != schema_name
    )
    timings.count("tool_calls", real_tool_calls)
    usage = getattr(metrics, "accumulated_usage", None) or {}
    timings.count("input_tokens", usage.get("inputTokens", 0) or 0)
    timings.count("output_tokens", usage.get("outputTokens", 0) or 0)


_RETRYABLE_MODEL_CODES = frozenset(
    {
        "throttlingException",
        "modelStreamErrorException",
        "serviceUnavailableException",
        "internalServerError",
    }
)
_MAX_MODEL_ATTEMPTS = 2


def _call_model(agent: Agent, output_model, prompt: str):
    """Run one structured model call; a single retry absorbs transient Bedrock errors."""
    attempts = 0
    while True:
        attempts += 1
        try:
            return agent(prompt, structured_output_model=output_model)
        except botocore.exceptions.EventStreamError:
            if attempts >= _MAX_MODEL_ATTEMPTS:
                raise
            logger.warning(
                "Transient Bedrock stream error (attempt %d); retrying once.", attempts
            )
        except botocore.exceptions.ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in _RETRYABLE_MODEL_CODES or attempts >= _MAX_MODEL_ATTEMPTS:
                raise
            logger.warning(
                "Retryable Bedrock error %r (attempt %d); retrying once.", code, attempts
            )


def _extract(
    agent: Agent,
    output_model,
    prompt: str,
    timings: EvaluationTimings | None = None,
):
    result = _call_model(agent, output_model, prompt)
    _record_model_call(timings, result, output_model=output_model)
    structured = result.structured_output
    if structured is None:
        raise ValueError(f"Model did not return structured {output_model.__name__}")
    return structured


def extract_candidate_profile(
    resume: str,
    timings: EvaluationTimings | None = None,
) -> CandidateProfile:
    """Extract and validate a candidate profile from resume text."""
    agent = build_pipeline_agent()
    profile = _extract(
        agent,
        CandidateProfile,
        PROFILE_EXTRACTION_PROMPT.format(resume=resume),
        timings,
    )
    return profile.model_copy(update={"evidence": validate_evidence(profile.evidence, resume)})


def extract_job_requirements(
    job_description: str,
    timings: EvaluationTimings | None = None,
) -> JobRequirements:
    """Extract job requirements from job description text."""
    agent = build_pipeline_agent()
    return _extract(
        agent,
        JobRequirements,
        REQUIREMENTS_EXTRACTION_PROMPT.format(job_description=job_description),
        timings,
    )


def _format_skill_gaps(gaps: list[SkillGap]) -> str:
    if not gaps:
        return "none"
    return ", ".join(f"{gap.skill} ({gap.severity})" for gap in gaps)


def draft_career_plan(
    profile: CandidateProfile,
    requirements: JobRequirements,
    match: MatchResult,
    recommendation: Recommendation,
    strengths: list[str] | None = None,
    skill_gaps: list[SkillGap] | None = None,
    timings: EvaluationTimings | None = None,
) -> CareerPlan:
    """One model call: explanation + interview topics + gap preparation.

    The draft is content only. Which skills are gaps, their severity, which
    drafted steps are accepted, and the recommendation itself are always
    decided by code before this call and never recomputed by the model.
    """
    agent = build_pipeline_agent()
    prompt = CAREER_PLAN_PROMPT.format(
        recommendation=recommendation,
        score=match.score,
        matched_skills=_format_list(match.matched_skills),
        matched_preferred_skills=_format_list(match.matched_preferred_skills),
        missing_critical_skills=_format_list(match.missing_critical_skills),
        missing_required_skills=_format_list(match.missing_required_skills),
        missing_preferred_skills=_format_list(match.missing_preferred_skills),
        unknown_requirements=_format_list(requirements.unknown_requirements),
        experience_display=_format_experience(match.experience_match),
        evidence=_format_list(profile.evidence),
        strengths=_format_list(strengths or []),
        skill_gaps=_format_skill_gaps(skill_gaps or []),
    )
    return _extract(agent, CareerPlan, prompt, timings)


def evaluate_candidate(
    resume: str,
    job_description: str,
    timings: EvaluationTimings | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> EvaluationResult:
    """Run the full structured evaluation pipeline.

    ``timings`` optionally receives each stage's duration; the caller that
    owns it is responsible for logging the summary. When absent, the
    service creates one internally and logs a single structured JSON line
    (used by CLI and any direct callers).

    ``on_stage`` is invoked with the canonical stage name each time a stage
    starts, so callers can stream live progress to a user (see the SSE
    endpoint in app/main.py).
    """
    owned = timings is None
    timings = timings or EvaluationTimings()

    timings.start("profile_extraction")
    _notify(on_stage, "profile_extraction")
    profile = extract_candidate_profile(resume, timings)
    timings.stop("profile_extraction")
    _stage_stopped("profile_extraction", timings)

    timings.start("requirements_extraction")
    _notify(on_stage, "requirements_extraction")
    requirements = extract_job_requirements(job_description, timings)
    timings.stop("requirements_extraction")
    _stage_stopped("requirements_extraction", timings)

    timings.start("deterministic_matching")
    _notify(on_stage, "deterministic_matching")
    requirements = normalize_requirements(requirements)

    match = build_match_result(profile, requirements)
    strengths = build_strengths(match, profile, requirements)
    gaps = build_skill_gaps(match)
    timings.start("recommendation")
    _notify(on_stage, "recommendation")
    recommendation = decide_recommendation(match, DEFAULT_POLICY)
    timings.stop("recommendation")
    timings.stop("deterministic_matching")
    _stage_stopped("deterministic_matching", timings)

    # Single model call: explanation + interview topics + gap preparation.
    # Everything deterministic is already computed above, so the model has
    # nothing left to calculate and no reason to loop.
    timings.start("plan_and_explanation")
    _notify(on_stage, "plan_and_explanation")
    plan = draft_career_plan(
        profile,
        requirements,
        match,
        recommendation,
        strengths=strengths,
        skill_gaps=gaps,
        timings=timings,
    )
    gaps = attach_preparation_steps(gaps, plan.gap_preparation)
    interview_topics = normalize_interview_topics(plan.interview_topics)
    preparation_plan = build_preparation_plan(gaps)
    reasoning = clean_reasoning(plan.reasoning)
    timings.stop("plan_and_explanation")
    _stage_stopped("plan_and_explanation", timings)

    result = EvaluationResult(
        recommendation=recommendation,
        **match.model_dump(),
        unknown_requirements=requirements.unknown_requirements,
        evidence=profile.evidence,
        strengths=strengths,
        skill_gaps=gaps,
        interview_topics=interview_topics,
        preparation_plan=preparation_plan,
        reasoning=reasoning,
    )
    logger.info(
        "Evaluation complete (%.2fs total, recommendation=%s, score=%d)",
        timings.elapsed(),
        result.recommendation,
        result.score,
    )
    if owned:
        timings.log(
            event="evaluation_pipeline_timings",
            recommendation=result.recommendation,
            score=result.score,
        )
    return result


def evaluate_resume_file(
    resume_file: bytes,
    filename: str,
    job_description: str,
    timings: EvaluationTimings | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> EvaluationResult:
    """Parse a resume file (PDF/TXT) and run the evaluation pipeline."""
    owned = timings is None
    timings = timings or EvaluationTimings()
    timings.start("resume_parse")
    _notify(on_stage, "resume_parse")
    resume_text = parse_resume(resume_file, filename)
    timings.stop("resume_parse")
    result = evaluate_candidate(
        resume_text,
        job_description,
        timings=timings,
        on_stage=on_stage,
    )
    if owned:
        timings.log(
            event="evaluation_pipeline_timings",
            recommendation=result.recommendation,
            score=result.score,
        )
    return result
