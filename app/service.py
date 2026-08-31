"""Structured evaluation pipeline.

LLM interprets, code decides:

    Resume ──> LLM extraction ──> CandidateProfile
    Job    ──> LLM extraction ──> JobRequirements
                      ↓
             normalize_requirements (deterministic, analyze_job core)
                      ↓
             build_match_result (deterministic)
                      ↓
             decide_recommendation (deterministic policy)
                      ↓
             build_strengths / build_skill_gaps (deterministic)
                      ↓
             LLM career plan (draft) ──> code validation
                      ↓
             LLM explanation ──> EvaluationResult

Every LLM step runs on a fresh agent so evaluations never share
conversation state.
"""

from strands import Agent

from app.agent import build_agent
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
  Use short canonical skill names, never phrases copied verbatim:
  "AWS experience" is "aws", "Familiarity with CI/CD" is "ci/cd",
  "REST API development" is "rest api".
- preferred_skills: skills explicitly listed as preferred or nice-to-have,
  using short canonical names.
- critical_skills: only skills the description explicitly marks with words
  like "must have", "mandatory", or "non-negotiable". A plain
  "Requirements" list means required, NOT critical.
- unknown_requirements: skills or requirements mentioned whose
  required/preferred status is NOT explicitly stated.
- min_years_experience: minimum years of experience explicitly required,
  or null if not stated.

Never infer that a requirement is optional, preferred, mandatory or
non-mandatory unless the job description explicitly says so. When in
doubt, put the skill in unknown_requirements.

JOB DESCRIPTION
---------------
{job_description}"""

CAREER_PLAN_PROMPT = """You are preparing a candidate for a job decision and interview.

Deterministic analysis of the candidate against the job:
- Matched required skills: {matched_skills}
- Matched preferred skills: {matched_preferred_skills}
- Missing critical skills: {missing_critical_skills}
- Missing required skills: {missing_required_skills}
- Missing preferred skills: {missing_preferred_skills}

Return:
- interview_topics: 3 to 8 concrete topics to prepare for this job's
  interview. Focus on matched skills (the interview will probe them)
  and missing skills (weak points to study first).
- gap_preparation: for each missing skill listed above, 2 to 5 concrete
  preparation steps in learning order. Only include skills from the
  missing lists.

Never mention candidate experience that is not listed here.
Never add skills for the candidate."""

EXPLANATION_PROMPT = """You evaluated a candidate against a job. The deterministic
evaluation result computed by tools is below.

Explain the recommendation to the candidate in 3 to 6 sentences.
Ground every claim in the evaluation result and the resume evidence.
Never invent experience or skills. If something is unknown, say so.
Mention the most important skill gaps and how to prepare them.

Recommendation: {recommendation}
Score: {score}
Matched required skills: {matched_skills}
Matched preferred skills: {matched_preferred_skills}
Missing required skills: {missing_required_skills}
Missing preferred skills: {missing_preferred_skills}
Missing critical skills: {missing_critical_skills}
Unknown requirements: {unknown_requirements}
Experience match: {experience_display}
Resume evidence: {evidence}
Strengths: {strengths}
Skill gaps to prepare: {skill_gaps}"""


def _format_experience(experience_match: bool | None) -> str:
    if experience_match is True:
        return "yes"
    if experience_match is False:
        return "no"
    return "unknown (not stated or not verifiable)"


def _format_list(values: list[str]) -> str:
    return ", ".join(values) if values else "none"


def _extract(agent: Agent, output_model, prompt: str):
    result = agent(prompt, structured_output_model=output_model)
    structured = result.structured_output
    if structured is None:
        raise ValueError(f"Model did not return structured {output_model.__name__}")
    return structured


def extract_candidate_profile(resume: str) -> CandidateProfile:
    """Extract and validate a candidate profile from resume text."""
    agent = build_agent()
    profile = _extract(agent, CandidateProfile, PROFILE_EXTRACTION_PROMPT.format(resume=resume))
    return profile.model_copy(update={"evidence": validate_evidence(profile.evidence, resume)})


def extract_job_requirements(job_description: str) -> JobRequirements:
    """Extract job requirements from job description text."""
    agent = build_agent()
    return _extract(
        agent,
        JobRequirements,
        REQUIREMENTS_EXTRACTION_PROMPT.format(job_description=job_description),
    )


def _format_skill_gaps(gaps: list[SkillGap]) -> str:
    if not gaps:
        return "none"
    return ", ".join(f"{gap.skill} ({gap.severity})" for gap in gaps)


def explain_evaluation(
    profile: CandidateProfile,
    requirements: JobRequirements,
    match: MatchResult,
    recommendation: Recommendation,
    strengths: list[str] | None = None,
    skill_gaps: list[SkillGap] | None = None,
) -> str:
    """Ask the LLM to explain an already computed evaluation result."""
    agent = build_agent()
    prompt = EXPLANATION_PROMPT.format(
        recommendation=recommendation,
        score=match.score,
        matched_skills=_format_list(match.matched_skills),
        matched_preferred_skills=_format_list(match.matched_preferred_skills),
        missing_required_skills=_format_list(match.missing_required_skills),
        missing_preferred_skills=_format_list(match.missing_preferred_skills),
        missing_critical_skills=_format_list(match.missing_critical_skills),
        unknown_requirements=_format_list(requirements.unknown_requirements),
        experience_display=_format_experience(match.experience_match),
        evidence=_format_list(profile.evidence),
        strengths=_format_list(strengths or []),
        skill_gaps=_format_skill_gaps(skill_gaps or []),
    )
    return clean_reasoning(str(agent(prompt)))


def generate_career_plan(match: MatchResult) -> CareerPlan:
    """Ask the LLM to draft interview topics and gap preparation content.

    The draft is content only. Which skills are gaps, their severity,
    and which drafted steps are accepted is always decided by code.
    """
    agent = build_agent()
    prompt = CAREER_PLAN_PROMPT.format(
        matched_skills=_format_list(match.matched_skills),
        matched_preferred_skills=_format_list(match.matched_preferred_skills),
        missing_critical_skills=_format_list(match.missing_critical_skills),
        missing_required_skills=_format_list(match.missing_required_skills),
        missing_preferred_skills=_format_list(match.missing_preferred_skills),
    )
    return _extract(agent, CareerPlan, prompt)


def evaluate_candidate(resume: str, job_description: str) -> EvaluationResult:
    """Run the full structured evaluation pipeline."""
    profile = extract_candidate_profile(resume)
    requirements = extract_job_requirements(job_description)
    requirements = normalize_requirements(requirements)

    match = build_match_result(profile, requirements)
    recommendation = decide_recommendation(match, DEFAULT_POLICY)
    strengths = build_strengths(match, profile, requirements)
    gaps = build_skill_gaps(match)

    plan = generate_career_plan(match)
    gaps = attach_preparation_steps(gaps, plan.gap_preparation)
    interview_topics = normalize_interview_topics(plan.interview_topics)
    preparation_plan = build_preparation_plan(gaps)

    reasoning = explain_evaluation(
        profile,
        requirements,
        match,
        recommendation,
        strengths=strengths,
        skill_gaps=gaps,
    )

    return EvaluationResult(
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


def evaluate_resume_file(
    resume_file: bytes,
    filename: str,
    job_description: str,
) -> EvaluationResult:
    """Parse a resume file (PDF/TXT) and run the evaluation pipeline."""
    resume_text = parse_resume(resume_file, filename)
    return evaluate_candidate(resume_text, job_description)
