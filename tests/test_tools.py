from app.tools import calculate_match


def test_calculate_match():
    result = calculate_match(
        candidate_skills=["Python", "Go", "PostgreSQL", "Docker"],
        required_skills=["Python", "PostgreSQL", "Docker", "AWS"],
    )

    assert result["score"] == 75
    assert result["matched_skills"] == ["docker", "postgresql", "python"]
    assert result["missing_required_skills"] == ["aws"]
    assert result["missing_preferred_skills"] == []
    assert result["missing_critical_skills"] == []
    assert result["experience_match"] is None
    assert result["recommendation"] == "APPLY"


def test_calculate_match_normalizes_whitespace_and_case():
    result = calculate_match(
        candidate_skills=[" REST   APIs ", "PYTHON"],
        required_skills=["rest APIs", "python"],
    )

    assert result["score"] == 100
    assert result["missing_required_skills"] == []
    assert result["recommendation"] == "APPLY"


def test_calculate_match_empty_requirements():
    result = calculate_match(["Python"], [])

    assert result["score"] == 0
    assert result["matched_skills"] == []
    assert result["missing_required_skills"] == []
    assert result["recommendation"] == "SKIP"


def test_calculate_match_unifies_skill_aliases():
    result = calculate_match(
        candidate_skills=["REST APIs", "Postgres"],
        required_skills=["REST API development", "PostgreSQL"],
    )

    assert result["score"] == 100
    assert result["matched_skills"] == ["postgresql", "rest api"]
    assert result["missing_required_skills"] == []
    assert result["recommendation"] == "APPLY"


def test_calculate_match_alias_with_missing_skill():
    result = calculate_match(
        candidate_skills=["POSTGRES"],
        required_skills=["PostgreSQL", "rest apis"],
    )

    assert result["score"] == 50
    assert result["matched_skills"] == ["postgresql"]
    assert result["missing_required_skills"] == ["rest api"]
    assert result["recommendation"] == "MAYBE"


def test_calculate_match_resume_phrase_vs_job_phrase():
    result = calculate_match(
        candidate_skills=["REST API design and integration"],
        required_skills=["REST API development"],
    )

    assert result["score"] == 100
    assert result["matched_skills"] == ["rest api"]
    assert result["missing_required_skills"] == []


def test_calculate_match_missing_preferred_skill_does_not_block_apply():
    result = calculate_match(
        candidate_skills=["Python"],
        required_skills=["Python"],
        preferred_skills=["AWS", "Kubernetes"],
    )

    assert result["score"] == 100
    assert result["missing_preferred_skills"] == ["aws", "kubernetes"]
    assert result["recommendation"] == "APPLY"


def test_calculate_match_missing_critical_skill_forces_skip():
    result = calculate_match(
        candidate_skills=["Python"],
        required_skills=["Python"],
        critical_skills=["AWS"],
    )

    assert result["score"] == 50
    assert result["missing_critical_skills"] == ["aws"]
    assert result["recommendation"] == "SKIP"


def test_calculate_match_experience_mismatch_downgrades_to_maybe():
    result = calculate_match(
        candidate_skills=["Python"],
        required_skills=["Python"],
        candidate_years_of_experience=1,
        required_years_of_experience=5,
    )

    assert result["score"] == 100
    assert result["experience_match"] is False
    assert result["recommendation"] == "MAYBE"
