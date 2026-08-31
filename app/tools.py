"""Deterministic tools exposed to the Strands agent.

The agent workflow is:

    analyze_job ──> normalize_skills ──> calculate_match
        ──> identify_skill_gaps ──> generate_interview_plan

Every tool decides deterministically; the agent only supplies the
interpreted inputs (skills and requirements read from the documents)
and the drafted preparation content.
"""

from strands import tool

from app.career import (
    attach_preparation_steps,
    build_preparation_plan,
    build_skill_gaps,
    normalize_interview_topics,
)
from app.matching import build_match_result, normalize_requirements, normalize_skill
from app.policy import decide_recommendation
from app.schemas import CandidateProfile, GapPreparation, JobRequirements

__all__ = [
    "analyze_job",
    "calculate_match",
    "generate_interview_plan",
    "identify_skill_gaps",
    "normalize_skills",
]


@tool
def normalize_skills(skills: list[str]) -> list[str]:
    """Canonicalize skill names so equivalent variants compare as equals.

    Names are lowercased, whitespace is collapsed, and common aliases
    are unified (for example "postgres" and "postgresql" are the same
    skill). Duplicates are removed.

    Args:
        skills: Skill names to canonicalize, from the resume or the job
            description.

    Returns:
        The sorted list of unique canonical skill names.
    """
    return sorted({normalize_skill(skill) for skill in skills if skill and skill.strip()})


@tool
def analyze_job(
    required_skills: list[str],
    preferred_skills: list[str] | None = None,
    critical_skills: list[str] | None = None,
    unknown_requirements: list[str] | None = None,
    min_years_experience: int | None = None,
) -> dict:
    """Classify and normalize the requirements of a job description.

    Deterministic rules applied to the requirements you identified:
    - skill names are canonicalized;
    - critical skills always count as required;
    - a skill listed as both required and preferred stays required only;
    - a skill already classified as required or preferred is removed
      from unknown_requirements.

    Args:
        required_skills: Skills the job description explicitly lists as required.
        preferred_skills: Skills explicitly listed as preferred or nice-to-have.
        critical_skills: Skills explicitly marked as mandatory or non-negotiable.
        unknown_requirements: Requirements whose required/preferred status the
            job description does not explicitly state.
        min_years_experience: Minimum years of experience explicitly required,
            if any.

    Returns:
        The normalized job requirements: required_skills, preferred_skills,
        critical_skills, unknown_requirements, and min_years_experience.
    """
    requirements = normalize_requirements(
        JobRequirements(
            required_skills=required_skills,
            preferred_skills=preferred_skills or [],
            critical_skills=critical_skills or [],
            unknown_requirements=unknown_requirements or [],
            min_years_experience=min_years_experience,
        )
    )
    return requirements.model_dump()


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


@tool
def identify_skill_gaps(
    candidate_skills: list[str],
    required_skills: list[str],
    preferred_skills: list[str] | None = None,
    critical_skills: list[str] | None = None,
) -> dict:
    """Identify the missing skills of a candidate against a job, ranked by severity.

    Gaps are computed deterministically: a gap is exactly a required,
    preferred, or critical skill the candidate does not evidence.
    Critical gaps come first, then required, then preferred.

    Args:
        candidate_skills: Skills evidenced by the candidate resume.
        required_skills: Skills the job description explicitly lists as required.
        preferred_skills: Skills explicitly listed as preferred, never blocking.
        critical_skills: Skills explicitly marked as mandatory or non-negotiable.

    Returns:
        A dictionary with skill_gaps: a list of
        {"skill", "severity", "preparation_steps"} entries ordered by
        severity. preparation_steps is empty here; fill it through
        generate_interview_plan.
    """
    profile = CandidateProfile(skills=candidate_skills)
    requirements = JobRequirements(
        required_skills=required_skills,
        preferred_skills=preferred_skills or [],
        critical_skills=critical_skills or [],
    )
    match = build_match_result(profile, requirements)
    gaps = build_skill_gaps(match)
    return {"skill_gaps": [gap.model_dump() for gap in gaps]}


@tool
def generate_interview_plan(
    candidate_skills: list[str],
    required_skills: list[str],
    interview_topics: list[str],
    preferred_skills: list[str] | None = None,
    critical_skills: list[str] | None = None,
    preparation_steps: dict[str, list[str]] | None = None,
) -> dict:
    """Validate and assemble a drafted interview preparation plan.

    You draft the plan content; this tool applies the deterministic
    rules before the plan is accepted:

    - gaps and their severity are recomputed, never taken from the draft;
    - preparation steps are only kept for skills that are actually missing;
    - duplicate, empty, and oversized entries are removed;
    - the preparation plan is ordered by severity (critical first).

    Args:
        candidate_skills: Skills evidenced by the candidate resume.
        required_skills: Skills the job description explicitly lists as required.
        interview_topics: Drafted interview topics, each tied to a matched
            or missing skill.
        preferred_skills: Skills explicitly listed as preferred, never blocking.
        critical_skills: Skills explicitly marked as mandatory or non-negotiable.
        preparation_steps: Drafted preparation steps keyed by missing skill
            name, for example {"aws": ["IAM fundamentals", "S3"]}.

    Returns:
        A dictionary with the validated interview_topics, the skill_gaps
        (each with skill, severity, and preparation_steps), and the
        flattened preparation_plan.
    """
    profile = CandidateProfile(skills=candidate_skills)
    requirements = JobRequirements(
        required_skills=required_skills,
        preferred_skills=preferred_skills or [],
        critical_skills=critical_skills or [],
    )
    match = build_match_result(profile, requirements)
    gaps = build_skill_gaps(match)

    preparation = [
        GapPreparation(skill=skill, preparation_steps=steps)
        for skill, steps in (preparation_steps or {}).items()
    ]
    gaps = attach_preparation_steps(gaps, preparation)

    return {
        "interview_topics": normalize_interview_topics(interview_topics),
        "skill_gaps": [gap.model_dump() for gap in gaps],
        "preparation_plan": build_preparation_plan(gaps),
    }
