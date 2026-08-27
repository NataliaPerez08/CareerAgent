from strands import tool


def _normalize_skill(skill: str) -> str:
    return " ".join(skill.strip().lower().split())


@tool
def calculate_match(
    candidate_skills: list[str],
    required_skills: list[str],
) -> dict:
    """Calculate a deterministic skill match score for a candidate.

    Args:
        candidate_skills: Skills evidenced by the candidate resume.
        required_skills: Mandatory or important skills from the job description.

    Returns:
        A dictionary containing the percentage score, matched skills, and missing skills.
    """
    candidate = {_normalize_skill(skill) for skill in candidate_skills if skill.strip()}
    required = {_normalize_skill(skill) for skill in required_skills if skill.strip()}

    if not required:
        return {"score": 0, "matched": [], "missing": []}

    matched = candidate & required
    missing = required - candidate
    score = round(len(matched) / len(required) * 100)

    return {
        "score": score,
        "matched": sorted(matched),
        "missing": sorted(missing),
    }
