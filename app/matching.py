"""Deterministic skill normalization, matching, evidence validation, and
text cleanup.

This module is the single source of truth for every calculation:
the calculate_match tool and the evaluation pipeline both call
build_match_result, and skill aliases live here.
"""

import re

from app.schemas import CandidateProfile, JobRequirements, MatchResult

SKILL_ALIASES = {
    "postgres": "postgresql",
    "cicd": "ci/cd",
    "cpp": "c++",
    "rest api development": "rest api",
    "rest apis": "rest api",
    "rest api design": "rest api",
    "rest api design and integration": "rest api",
    "rest api integration": "rest api",
}

# Context words models attach to skill names, for example
# "AWS experience" or "Familiarity with CI/CD". They are stripped so
# only the skill name itself is compared.
SKILL_CONTEXT_PREFIXES = (
    "experience with ",
    "familiarity with ",
    "knowledge of ",
    "proficiency in ",
    "expertise in ",
)
SKILL_CONTEXT_SUFFIXES = (
    " experience",
    " familiarity",
    " knowledge",
    " proficiency",
    " expertise",
    " skills",
)


def _strip_context_words(skill: str) -> str:
    changed = True
    while changed:
        changed = False
        for prefix in SKILL_CONTEXT_PREFIXES:
            if skill.startswith(prefix):
                skill = skill[len(prefix) :]
                changed = True
        for suffix in SKILL_CONTEXT_SUFFIXES:
            if skill.endswith(suffix):
                skill = skill[: -len(suffix)]
                changed = True
    return skill


def normalize_skill(skill: str) -> str:
    normalized = " ".join(skill.strip().lower().split())
    normalized = _strip_context_words(normalized)
    return SKILL_ALIASES.get(normalized, normalized)


def _normalize_set(skills: list[str]) -> set[str]:
    return {normalize_skill(skill) for skill in skills if skill and skill.strip()}


def _normalize_list(skills: list[str]) -> list[str]:
    return sorted(_normalize_set(skills))


def normalize_requirements(requirements: JobRequirements) -> JobRequirements:
    """Classify and normalize job requirements deterministically.

    Rules:
    - skill names are canonicalized (lowercase, aliases unified);
    - critical skills always count as required;
    - a skill listed as both required and preferred stays required only;
    - a skill already classified as required/preferred is removed from
      unknown_requirements.
    """
    critical = _normalize_list(requirements.critical_skills)
    required = _normalize_list(requirements.required_skills + critical)
    preferred = _normalize_list(requirements.preferred_skills)
    unknown = _normalize_list(requirements.unknown_requirements)

    preferred = [skill for skill in preferred if skill not in set(required)]
    unknown = [
        skill for skill in unknown if skill not in set(required) and skill not in set(preferred)
    ]

    return JobRequirements(
        required_skills=required,
        preferred_skills=preferred,
        critical_skills=critical,
        unknown_requirements=unknown,
        min_years_experience=requirements.min_years_experience,
    )


def build_match_result(profile: CandidateProfile, requirements: JobRequirements) -> MatchResult:
    """Compute the deterministic match between a profile and job requirements.

    Critical skills count as required. Unknown requirements never count
    toward the score. The score is required-skill coverage, falling back
    to preferred-skill coverage when nothing is explicitly required.
    """
    requirements = normalize_requirements(requirements)
    candidate = _normalize_set(profile.skills)
    critical = set(requirements.critical_skills)
    required = set(requirements.required_skills)
    preferred = set(requirements.preferred_skills)

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


def clean_reasoning(text: str) -> str:
    """Remove model artifacts from free-text explanations.

    Strips leaked reasoning blocks such as <thinking>...</thinking>
    and collapses excess blank lines. The explanation content itself
    is never altered.
    """
    cleaned = re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL | re.IGNORECASE)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()
