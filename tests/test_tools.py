from app.tools import calculate_match


def test_calculate_match():
    result = calculate_match(
        candidate_skills=["Python", "Go", "PostgreSQL", "Docker"],
        required_skills=["Python", "PostgreSQL", "Docker", "AWS"],
    )

    assert result["score"] == 75
    assert result["matched"] == ["docker", "postgresql", "python"]
    assert result["missing"] == ["aws"]


def test_calculate_match_normalizes_whitespace_and_case():
    result = calculate_match(
        candidate_skills=[" REST   APIs ", "PYTHON"],
        required_skills=["rest APIs", "python"],
    )

    assert result["score"] == 100
    assert result["missing"] == []


def test_calculate_match_empty_requirements():
    result = calculate_match(["Python"], [])

    assert result == {"score": 0, "matched": [], "missing": []}
