from app.matching import (
    build_match_result,
    clean_reasoning,
    normalize_requirements,
    normalize_skill,
    validate_evidence,
)
from app.schemas import CandidateProfile, JobRequirements


def make_profile(skills, years=None, evidence=None):
    return CandidateProfile(skills=skills, years_of_experience=years, evidence=evidence or [])


def make_requirements(required=None, preferred=None, critical=None, unknown=None, min_years=None):
    return JobRequirements(
        required_skills=required or [],
        preferred_skills=preferred or [],
        critical_skills=critical or [],
        unknown_requirements=unknown or [],
        min_years_experience=min_years,
    )


def test_normalize_skill_applies_aliases():
    assert normalize_skill("PostGres") == "postgresql"
    assert normalize_skill("REST APIs") == "rest api"
    assert normalize_skill("REST API development") == "rest api"
    assert normalize_skill("  JAVA   script ") == "java script"


def test_normalize_skill_strips_context_words():
    # Regression: Nova Micro extracts "AWS experience" / "ci/cd familiarity"
    # from "AWS experience. Familiarity with CI/CD." Context words must not
    # turn one skill into a different one.
    assert normalize_skill("AWS experience") == "aws"
    assert normalize_skill("CI/CD familiarity") == "ci/cd"
    assert normalize_skill("Familiarity with Kubernetes") == "kubernetes"
    assert normalize_skill("Experience with REST API development") == "rest api"
    assert normalize_skill("Knowledge of PostgreSQL") == "postgresql"


def test_clean_reasoning_strips_leaked_thinking_blocks():
    raw = (
        "<thinking>The candidate matches all required skills.</thinking>\n\n\n"
        "Here is the recommendation for the candidate.\n"
    )

    assert clean_reasoning(raw) == "Here is the recommendation for the candidate."


def test_clean_reasoning_keeps_plain_text():
    assert clean_reasoning("  Strong overlap on the core backend stack. ") == (
        "Strong overlap on the core backend stack."
    )


def test_normalize_requirements_unifies_aliases_and_dedupes():
    requirements = normalize_requirements(
        make_requirements(required=["PostgreSQL"], preferred=["postgres", "AWS"])
    )

    assert requirements.required_skills == ["postgresql"]
    assert requirements.preferred_skills == ["aws"]


def test_normalize_requirements_critical_implies_required():
    requirements = normalize_requirements(make_requirements(critical=["AWS"]))

    assert requirements.critical_skills == ["aws"]
    assert requirements.required_skills == ["aws"]


def test_normalize_requirements_removes_classified_from_unknown():
    requirements = normalize_requirements(
        make_requirements(
            required=["Python"], preferred=["Docker"], unknown=["python", "docker", "Rust"]
        )
    )

    assert requirements.unknown_requirements == ["rust"]


def test_normalize_requirements_keeps_min_years_experience():
    requirements = normalize_requirements(make_requirements(required=["Python"], min_years=3))

    assert requirements.min_years_experience == 3


def test_required_match_score_and_lists():
    match = build_match_result(
        make_profile(["Python", "Go", "PostgreSQL", "Docker"]),
        make_requirements(required=["Python", "PostgreSQL", "Docker", "AWS"]),
    )

    assert match.score == 75
    assert match.matched_skills == ["docker", "postgresql", "python"]
    assert match.missing_required_skills == ["aws"]


def test_preferred_skills_do_not_lower_score():
    match = build_match_result(
        make_profile(["Python"]),
        make_requirements(required=["Python"], preferred=["AWS", "Kubernetes"]),
    )

    assert match.score == 100
    assert match.missing_preferred_skills == ["aws", "kubernetes"]
    assert match.matched_preferred_skills == []


def test_unknown_requirements_never_count_toward_score():
    match = build_match_result(
        make_profile(["Python"]),
        make_requirements(required=["Python"], unknown=["Rust", "Kafka"]),
    )

    assert match.score == 100
    assert match.missing_required_skills == []


def test_critical_skills_count_as_required():
    match = build_match_result(
        make_profile(["Python"]),
        make_requirements(required=["Python"], critical=["AWS"]),
    )

    assert match.score == 50
    assert match.missing_required_skills == ["aws"]
    assert match.missing_critical_skills == ["aws"]


def test_skill_aliases_unify_across_documents():
    match = build_match_result(
        make_profile(["REST API design and integration", "Postgres"]),
        make_requirements(required=["REST API development", "PostgreSQL"]),
    )

    assert match.score == 100
    assert match.matched_skills == ["postgresql", "rest api"]


def test_preferred_only_job_scores_on_preferred_coverage():
    match = build_match_result(
        make_profile(["Python", "Docker"]),
        make_requirements(preferred=["Python", "Docker", "AWS"]),
    )

    assert match.score == 67
    assert match.missing_preferred_skills == ["aws"]


def test_no_requirements_at_all_scores_zero():
    match = build_match_result(make_profile(["Python"]), make_requirements())

    assert match.score == 0
    assert match.matched_skills == []


def test_experience_match_none_when_either_side_unstated():
    both_missing = build_match_result(
        make_profile(["Python"]), make_requirements(required=["Python"])
    )
    assert both_missing.experience_match is None

    no_job_requirement = build_match_result(
        make_profile(["Python"], years=2),
        make_requirements(required=["Python"]),
    )
    assert no_job_requirement.experience_match is None

    no_resume_evidence = build_match_result(
        make_profile(["Python"]),
        make_requirements(required=["Python"], min_years=3),
    )
    assert no_resume_evidence.experience_match is None


def test_experience_match_true_and_false():
    junior_ok = build_match_result(
        make_profile(["Python"], years=2),
        make_requirements(required=["Python"], min_years=1),
    )
    assert junior_ok.experience_match is True

    junior_short = build_match_result(
        make_profile(["Python"], years=1),
        make_requirements(required=["Python"], min_years=5),
    )
    assert junior_short.experience_match is False


def test_validate_evidence_keeps_verbatim_and_drops_invented():
    resume = "Backend developer with 2 years of experience. Built REST APIs with Python."
    evidence = [
        "2 years of experience",
        "Built REST APIs with Python",
        "Led a team of 10 engineers",
    ]

    assert validate_evidence(evidence, resume) == [
        "2 years of experience",
        "Built REST APIs with Python",
    ]


def test_validate_evidence_ignores_case_and_whitespace():
    resume = "Python   developer with 2 years"
    assert validate_evidence(["python developer with   2 years"], resume) == [
        "python developer with   2 years"
    ]
