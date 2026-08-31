from app.schemas import CandidateProfile, EvaluationResult, JobRequirements, SkillGap


def test_candidate_profile_defaults():
    profile = CandidateProfile()

    assert profile.skills == []
    assert profile.years_of_experience is None
    assert profile.evidence == []


def test_job_requirements_defaults():
    requirements = JobRequirements()

    assert requirements.required_skills == []
    assert requirements.preferred_skills == []
    assert requirements.critical_skills == []
    assert requirements.unknown_requirements == []
    assert requirements.min_years_experience is None


def test_evaluation_result_serializes_expected_contract():
    result = EvaluationResult(
        recommendation="APPLY",
        score=85,
        matched_skills=["python", "postgresql", "rest api"],
        missing_required_skills=["aws"],
        experience_match=True,
        evidence=["2 years of backend development"],
        reasoning="Strong overlap on core backend skills.",
    )

    payload = result.model_dump()

    for key in (
        "recommendation",
        "score",
        "matched_skills",
        "missing_required_skills",
        "missing_preferred_skills",
        "experience_match",
        "evidence",
        "reasoning",
    ):
        assert key in payload

    assert payload["recommendation"] == "APPLY"
    assert payload["score"] == 85
    assert payload["missing_required_skills"] == ["aws"]


def test_evaluation_result_defaults_career_intelligence_fields():
    result = EvaluationResult(recommendation="APPLY", score=85)

    assert result.strengths == []
    assert result.skill_gaps == []
    assert result.interview_topics == []
    assert result.preparation_plan == []


def test_evaluation_result_serializes_skill_gaps():
    result = EvaluationResult(
        recommendation="MAYBE",
        score=50,
        skill_gaps=[
            SkillGap(
                skill="aws",
                severity="required",
                preparation_steps=["IAM fundamentals", "S3"],
            )
        ],
        interview_topics=["PostgreSQL indexes"],
        preparation_plan=["aws: IAM fundamentals", "aws: S3"],
        strengths=["Meets 1 of 2 required skills: python"],
    )

    payload = result.model_dump()

    assert payload["skill_gaps"] == [
        {
            "skill": "aws",
            "severity": "required",
            "preparation_steps": ["IAM fundamentals", "S3"],
        }
    ]
    assert payload["interview_topics"] == ["PostgreSQL indexes"]
    assert payload["preparation_plan"] == ["aws: IAM fundamentals", "aws: S3"]
    assert payload["strengths"] == ["Meets 1 of 2 required skills: python"]
