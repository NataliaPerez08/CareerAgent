"""Structured evaluation pipeline.

LLM interprets, code decides:

    Resume ──> LLM extraction ──> CandidateProfile
    Job    ──> LLM extraction ──> JobRequirements
                     ↓
            build_match_result (deterministic)
                     ↓
            decide_recommendation (deterministic policy)
                     ↓
            LLM explanation ──> EvaluationResult

Every LLM step runs on a fresh agent so evaluations never share
conversation state.
"""

from strands import Agent

from app.agent import build_agent
from app.matching import build_match_result, validate_evidence
from app.policy import DEFAULT_POLICY, decide_recommendation
from app.resume_parser import parse_resume
from app.schemas import (
    CandidateProfile,
    EvaluationResult,
    JobRequirements,
    MatchResult,
    Recommendation,
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
  Use short canonical names (for example "aws", "ci/cd"), not long phrases.
- preferred_skills: skills explicitly listed as preferred or nice-to-have,
  using short canonical names.
- critical_skills: skills explicitly marked as mandatory, "must have",
  or non-negotiable.
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

EXPLANATION_PROMPT = """You evaluated a candidate against a job. The deterministic
evaluation result computed by tools is below.

Explain the recommendation to the candidate in 3 to 6 sentences.
Ground every claim in the evaluation result and the resume evidence.
Never invent experience or skills. If something is unknown, say so.

Recommendation: {recommendation}
Score: {score}
Matched required skills: {matched_skills}
Matched preferred skills: {matched_preferred_skills}
Missing required skills: {missing_required_skills}
Missing preferred skills: {missing_preferred_skills}
Missing critical skills: {missing_critical_skills}
Unknown requirements: {unknown_requirements}
Experience match: {experience_display}
Resume evidence: {evidence}"""


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


def explain_evaluation(
    profile: CandidateProfile,
    requirements: JobRequirements,
    match: MatchResult,
    recommendation: Recommendation,
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
    )
    return str(agent(prompt)).strip()


def evaluate_candidate(resume: str, job_description: str) -> EvaluationResult:
    """Run the full structured evaluation pipeline."""
    profile = extract_candidate_profile(resume)
    requirements = extract_job_requirements(job_description)

    match = build_match_result(profile, requirements)
    recommendation = decide_recommendation(match, DEFAULT_POLICY)
    reasoning = explain_evaluation(profile, requirements, match, recommendation)

    return EvaluationResult(
        recommendation=recommendation,
        **match.model_dump(),
        unknown_requirements=requirements.unknown_requirements,
        evidence=profile.evidence,
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
