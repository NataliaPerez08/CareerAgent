from app.tools import (
    analyze_job,
    calculate_match,
    generate_interview_plan,
    identify_skill_gaps,
    normalize_skills,
)


def test_normalize_skills_tool_canonicalizes_and_dedupes():
    assert normalize_skills([" REST APIs ", "Postgres", "postgres", "Python"]) == [
        "postgresql",
        "python",
        "rest api",
    ]


def test_normalize_skills_tool_empty_input():
    assert normalize_skills([]) == []
    assert normalize_skills(["", "   "]) == []


def test_analyze_job_normalizes_and_resolves_overlaps():
    result = analyze_job(
        required_skills=["Python", "PostgreSQL"],
        preferred_skills=["postgres", "AWS"],
        unknown_requirements=["python", "Kafka"],
    )

    assert result["required_skills"] == ["postgresql", "python"]
    assert result["preferred_skills"] == ["aws"]
    assert result["unknown_requirements"] == ["kafka"]
    assert result["critical_skills"] == []
    assert result["min_years_experience"] is None


def test_analyze_job_critical_implies_required():
    result = analyze_job(required_skills=["Python"], critical_skills=["AWS"])

    assert result["critical_skills"] == ["aws"]
    assert result["required_skills"] == ["aws", "python"]


def test_identify_skill_gaps_ranks_by_severity():
    result = identify_skill_gaps(
        candidate_skills=["Python", "PostgreSQL"],
        required_skills=["Python", "PostgreSQL", "Terraform", "Docker"],
        preferred_skills=["Kubernetes"],
        critical_skills=["AWS"],
    )

    assert result["skill_gaps"] == [
        {"skill": "aws", "severity": "critical", "preparation_steps": []},
        {"skill": "docker", "severity": "required", "preparation_steps": []},
        {"skill": "terraform", "severity": "required", "preparation_steps": []},
        {"skill": "kubernetes", "severity": "preferred", "preparation_steps": []},
    ]


def test_identify_skill_gaps_no_gaps():
    result = identify_skill_gaps(
        candidate_skills=["Python"],
        required_skills=["Python"],
    )

    assert result["skill_gaps"] == []


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


def test_generate_interview_plan_keeps_only_real_gaps():
    result = generate_interview_plan(
        candidate_skills=["Python", "PostgreSQL"],
        required_skills=["Python", "PostgreSQL", "AWS"],
        interview_topics=["PostgreSQL indexes", "postgresql indexes", "REST design", ""],
        preparation_steps={
            "AWS": ["IAM fundamentals", "S3", "IAM Fundamentals"],
            # Candidate already has it: dropped.
            "Python": ["Advanced typing"],
            # Job never asked for it: dropped.
            "Kafka": ["Event streaming basics"],
        },
    )

    assert result["interview_topics"] == ["PostgreSQL indexes", "REST design"]
    assert result["skill_gaps"] == [
        {"skill": "aws", "severity": "required", "preparation_steps": ["IAM fundamentals", "S3"]}
    ]
    assert result["preparation_plan"] == ["aws: IAM fundamentals", "aws: S3"]


def test_generate_interview_plan_reports_gaps_without_drafted_steps():
    result = generate_interview_plan(
        candidate_skills=["Python"],
        required_skills=["Python", "AWS"],
        interview_topics=[],
    )

    assert result["skill_gaps"] == [
        {"skill": "aws", "severity": "required", "preparation_steps": []}
    ]
    assert result["preparation_plan"] == []


def test_generate_interview_plan_orders_preparation_by_severity():
    result = generate_interview_plan(
        candidate_skills=["Python"],
        required_skills=["Python", "Docker"],
        preferred_skills=["Kubernetes"],
        critical_skills=["AWS"],
        interview_topics=[],
        preparation_steps={
            "AWS": ["IAM fundamentals"],
            "Docker": ["Containers basics"],
            "Kubernetes": ["Cluster basics"],
        },
    )

    assert result["preparation_plan"] == [
        "aws: IAM fundamentals",
        "docker: Containers basics",
        "kubernetes: Cluster basics",
    ]


def test_agent_tools_generate_valid_schemas():
    import json

    agent_tools = (
        analyze_job,
        normalize_skills,
        calculate_match,
        identify_skill_gaps,
        generate_interview_plan,
    )
    for agent_tool in agent_tools:
        spec = agent_tool.tool_spec
        assert spec["name"]
        json.dumps(spec["inputSchema"]["json"])
