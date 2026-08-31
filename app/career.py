"""Deterministic career intelligence: strengths, skill gaps, preparation plans.

The LLM only drafts preparation content (topics, steps). This module
decides everything that can be computed:

- which skills are gaps and their severity;
- which strengths the candidate has;
- which drafted steps are accepted (only for skills that are actually
  missing);
- ordering, deduplication, and size limits.
"""

from app.matching import normalize_skill
from app.schemas import (
    CandidateProfile,
    GapPreparation,
    JobRequirements,
    MatchResult,
    SkillGap,
)

MAX_INTERVIEW_TOPICS = 10
MAX_PREPARATION_STEPS = 8


def build_skill_gaps(match: MatchResult) -> list[SkillGap]:
    """Rank missing skills by severity: critical, then required, then preferred.

    A critical skill missing also appears in missing_required_skills,
    so it is reported once with the highest severity only.
    """
    critical = set(match.missing_critical_skills)
    gaps = [SkillGap(skill=skill, severity="critical") for skill in match.missing_critical_skills]
    gaps += [
        SkillGap(skill=skill, severity="required")
        for skill in match.missing_required_skills
        if skill not in critical
    ]
    gaps += [
        SkillGap(skill=skill, severity="preferred") for skill in match.missing_preferred_skills
    ]
    return gaps


def build_strengths(
    match: MatchResult,
    profile: CandidateProfile,
    requirements: JobRequirements,
) -> list[str]:
    """Build factual strengths derived only from the deterministic match.

    Strengths never invent experience: they state matched skills, the
    experience requirement when explicitly met, and mandatory coverage.
    """
    strengths: list[str] = []
    if match.matched_skills:
        required_total = len(match.matched_skills) + len(match.missing_required_skills)
        strengths.append(
            f"Meets {len(match.matched_skills)} of {required_total} required skills: "
            f"{', '.join(match.matched_skills)}"
        )
    if match.matched_preferred_skills:
        strengths.append(
            f"Also brings preferred skills: {', '.join(match.matched_preferred_skills)}"
        )
    if match.experience_match is True and profile.years_of_experience is not None:
        strengths.append(f"Experience requirement met: {profile.years_of_experience} years")
    if requirements.critical_skills and not match.missing_critical_skills:
        strengths.append("All explicitly mandatory skills are covered")
    return strengths


def clean_steps(steps: list[str], limit: int = MAX_PREPARATION_STEPS) -> list[str]:
    """Strip, deduplicate (case-insensitive), and cap preparation steps."""
    cleaned: list[str] = []
    for step in steps:
        text = " ".join(step.strip().split())
        if text and text.lower() not in {s.lower() for s in cleaned}:
            cleaned.append(text)
    return cleaned[:limit]


def normalize_interview_topics(topics: list[str]) -> list[str]:
    """Strip, deduplicate (case-insensitive), and cap interview topics."""
    return clean_steps(topics, limit=MAX_INTERVIEW_TOPICS)


def attach_preparation_steps(
    gaps: list[SkillGap],
    preparation: list[GapPreparation],
) -> list[SkillGap]:
    """Attach validated preparation steps to deterministic skill gaps.

    Drafted steps are only accepted for skills that are actually gaps.
    Steps for skills the candidate already has, or that the job never
    asked for, are dropped: preparing them is not grounded in the match.
    """
    steps_by_skill: dict[str, list[str]] = {}
    for item in preparation:
        skill = normalize_skill(item.skill)
        steps_by_skill[skill] = clean_steps(steps_by_skill.get(skill, []) + item.preparation_steps)

    return [
        gap.model_copy(update={"preparation_steps": steps_by_skill.get(gap.skill, [])})
        for gap in gaps
    ]


def build_preparation_plan(gaps: list[SkillGap]) -> list[str]:
    """Flatten the gap preparation into a single ordered study plan.

    Gaps arrive ordered by severity, so the plan starts with what
    blocks the application most.
    """
    return [f"{gap.skill}: {step}" for gap in gaps for step in gap.preparation_steps]
