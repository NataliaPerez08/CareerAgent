"""Deterministic tools exposed to the Strands agent."""

from strands import tool

from app.matching import build_match_result
from app.policy import decide_recommendation
from app.schemas import CandidateProfile, JobRequirements


@tool
def calculate_match(
    candidate_skills: list[str],
    required_skills: list[str],
    preferred_skills: list[str] | None = None,
    critical_skills: list[str] | None = None,
    candidate_years_of_experience: int | None = None,
    required_years_of_experience: int | None = None,
) -> dict:
    """Calculate a deterministic skill match and recommendation for a candidate.

    Skill names are normalized before comparison: lowercase, collapsed
    whitespace, and common aliases unified (for example "postgres" and
    "postgresql" are the same skill).

    The recommendation comes from centralized deterministic rules:
    APPLY requires a high score with no missing critical skills and no
    explicit experience mismatch; missing critical skills or a low score
    produce SKIP; everything else is MAYBE.

    Args:
        candidate_skills: Skills evidenced by the candidate resume.
        required_skills: Skills the job description explicitly lists as required.
        preferred_skills: Skills explicitly listed as preferred, never blocking.
        critical_skills: Skills explicitly marked as mandatory or non-negotiable.
        candidate_years_of_experience: Years of experience stated in the resume, if any.
        required_years_of_experience: Minimum years of experience the job requires, if any.

    Returns:
        A dictionary with the score, matched and missing skills,
        experience_match, and the APPLY/MAYBE/SKIP recommendation.
    """
    profile = CandidateProfile(
        skills=candidate_skills,
        years_of_experience=candidate_years_of_experience,
    )
    requirements = JobRequirements(
        required_skills=required_skills,
        preferred_skills=preferred_skills or [],
        critical_skills=critical_skills or [],
        min_years_experience=required_years_of_experience,
    )
    match = build_match_result(profile, requirements)
    return {
        **match.model_dump(),
        "recommendation": decide_recommendation(match),
    }
