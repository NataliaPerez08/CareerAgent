"""Deterministic skill normalization, matching, and evidence validation.

This module is the single source of truth for every calculation:
the calculate_match tool and the evaluation pipeline both call
build_match_result, and skill aliases live here.
"""

from app.schemas import CandidateProfile, JobRequirements, MatchResult

SKILL_ALIASES = {
    "postgres": "postgresql",
    "rest api development": "rest api",
    "rest apis": "rest api",
    "rest api design": "rest api",
    "rest api design and integration": "rest api",
    "rest api integration": "rest api",
}


def normalize_skill(skill: str) -> str:
    normalized = " ".join(skill.strip().lower().split())
    return SKILL_ALIASES.get(normalized, normalized)


def _normalize_set(skills: list[str]) -> set[str]:
    return {normalize_skill(skill) for skill in skills if skill and skill.strip()}


def build_match_result(profile: CandidateProfile, requirements: JobRequirements) -> MatchResult:
    """Compute the deterministic match between a profile and job requirements.

    Critical skills count as required. Unknown requirements never count
    toward the score. The score is required-skill coverage, falling back
    to preferred-skill coverage when nothing is explicitly required.
    """
    candidate = _normalize_set(profile.skills)
    critical = _normalize_set(requirements.critical_skills)
    required = _normalize_set(requirements.required_skills) | critical
    preferred = _normalize_set(requirements.preferred_skills) - required

    matched = candidate & required
    matched_preferred = candidate & preferred

    if required:
        score = round(len(matched) / len(required) * 100)
    elif preferred:
        score = round(len(matched_preferred) / len(preferred) * 100)
    else:
        score = 0

    if requirements.min_years_experience is None or profile.years_of_experience is None:
        experience_match = None
    else:
        experience_match = profile.years_of_experience >= requirements.min_years_experience

    return MatchResult(
        score=score,
        matched_skills=sorted(matched),
        matched_preferred_skills=sorted(matched_preferred),
        missing_required_skills=sorted(required - candidate),
        missing_preferred_skills=sorted(preferred - candidate),
        missing_critical_skills=sorted(critical - candidate),
        experience_match=experience_match,
    )


def validate_evidence(evidence: list[str], resume_text: str) -> list[str]:
    """Keep only evidence strings that appear verbatim in the resume.

    Comparison ignores case and whitespace differences. Any evidence
    not found in the resume is dropped: it cannot be trusted.
    """
    haystack = " ".join(resume_text.lower().split())
    kept = []
    for item in evidence:
        needle = " ".join(item.strip().lower().split())
        if needle and needle in haystack:
            kept.append(item.strip())
    return kept
