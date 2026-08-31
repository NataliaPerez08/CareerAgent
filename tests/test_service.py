from types import SimpleNamespace

from app import service
from app.schemas import (
    CandidateProfile,
    CareerPlan,
    EvaluationResult,
    GapPreparation,
    JobRequirements,
)

RESUME = (
    "Backend developer with 2 years of professional software development experience. "
    "Python for backend services. REST API design and integration. "
    "PostgreSQL for relational persistence. Docker for deployment packaging."
)

JOB = (
    "Junior Backend Engineer\n\n"
    "Requirements:\n- 1+ years of backend software development experience.\n"
    "- Python.\n- REST API development.\n- PostgreSQL.\n- Docker.\n\n"
    "Preferred:\n- AWS experience.\n- Familiarity with CI/CD."
)


class FakeTextResult:
    structured_output = None

    def __str__(self):
        return "Strong overlap on the core backend stack."


class FakeAgent:
    """Stands-in for the Strands agent: returns canned structured outputs."""

    def __call__(self, prompt, structured_output_model=None):
        if structured_output_model is CandidateProfile:
            return SimpleNamespace(
                structured_output=CandidateProfile(
                    skills=["Python", "REST API design and integration", "PostgreSQL", "Docker"],
                    years_of_experience=2,
                    evidence=[
                        "2 years of professional software development experience",
                        "Led a 50-person platform organization",
                    ],
                )
            )
        if structured_output_model is JobRequirements:
            return SimpleNamespace(
                structured_output=JobRequirements(
                    required_skills=[
                        "Python",
                        "REST API development",
                        "PostgreSQL",
                        "Docker",
                    ],
                    preferred_skills=["AWS"],
                    min_years_experience=1,
                )
            )
        if structured_output_model is CareerPlan:
            return SimpleNamespace(
                structured_output=CareerPlan(
                    interview_topics=[
                        "PostgreSQL indexes",
                        "REST design",
                        "postgresql indexes",
                        "",
                        "IAM fundamentals",
                    ],
                    gap_preparation=[
                        GapPreparation(
                            skill="AWS",
                            preparation_steps=[
                                "IAM fundamentals",
                                "S3",
                                "Lambda",
                                "API Gateway",
                            ],
                        ),
                        # Not a gap for this job: must be dropped by validation.
                        GapPreparation(skill="Kubernetes", preparation_steps=["Container basics"]),
                    ],
                )
            )
        return FakeTextResult()


class FailingAgent:
    def __call__(self, prompt, structured_output_model=None):
        raise RuntimeError("model unavailable")


def test_extract_candidate_profile_drops_invented_evidence(monkeypatch):
    monkeypatch.setattr(service, "build_agent", lambda: FakeAgent())

    profile = service.extract_candidate_profile(RESUME)

    assert profile.skills == ["Python", "REST API design and integration", "PostgreSQL", "Docker"]
    assert profile.years_of_experience == 2
    assert profile.evidence == ["2 years of professional software development experience"]


def test_extract_job_requirements_returns_structured(monkeypatch):
    monkeypatch.setattr(service, "build_agent", lambda: FakeAgent())

    requirements = service.extract_job_requirements(JOB)

    assert requirements.required_skills == [
        "Python",
        "REST API development",
        "PostgreSQL",
        "Docker",
    ]
    assert requirements.preferred_skills == ["AWS"]
    assert requirements.min_years_experience == 1


def test_evaluate_candidate_composes_structured_result(monkeypatch):
    monkeypatch.setattr(service, "build_agent", lambda: FakeAgent())

    result = service.evaluate_candidate(RESUME, JOB)

    assert isinstance(result, EvaluationResult)
    assert result.recommendation == "APPLY"
    assert result.score == 100
    assert result.matched_skills == ["docker", "postgresql", "python", "rest api"]
    assert result.missing_required_skills == []
    assert result.missing_preferred_skills == ["aws"]
    assert result.experience_match is True
    assert result.evidence == ["2 years of professional software development experience"]
    assert result.reasoning == "Strong overlap on the core backend stack."


def test_evaluate_candidate_composes_career_intelligence(monkeypatch):
    monkeypatch.setattr(service, "build_agent", lambda: FakeAgent())

    result = service.evaluate_candidate(RESUME, JOB)

    assert result.strengths == [
        "Meets 4 of 4 required skills: docker, postgresql, python, rest api",
        "Experience requirement met: 2 years",
    ]
    # Only real gaps survive: the drafted Kubernetes preparation is dropped.
    assert [gap.model_dump() for gap in result.skill_gaps] == [
        {
            "skill": "aws",
            "severity": "preferred",
            "preparation_steps": ["IAM fundamentals", "S3", "Lambda", "API Gateway"],
        }
    ]
    # Topics are deduplicated case-insensitively and empties removed.
    assert result.interview_topics == ["PostgreSQL indexes", "REST design", "IAM fundamentals"]
    assert result.preparation_plan == [
        "aws: IAM fundamentals",
        "aws: S3",
        "aws: Lambda",
        "aws: API Gateway",
    ]


def test_evaluate_candidate_normalizes_extracted_requirements(monkeypatch):
    class OverlappingAgent(FakeAgent):
        def __call__(self, prompt, structured_output_model=None):
            if structured_output_model is JobRequirements:
                return SimpleNamespace(
                    structured_output=JobRequirements(
                        required_skills=["Python", "PostgreSQL"],
                        preferred_skills=["postgres", "AWS"],
                        unknown_requirements=["python"],
                        min_years_experience=1,
                    )
                )
            return super().__call__(prompt, structured_output_model)

    monkeypatch.setattr(service, "build_agent", lambda: OverlappingAgent())

    result = service.evaluate_candidate(RESUME, JOB)

    assert result.matched_skills == ["postgresql", "python"]
    assert result.missing_required_skills == []
    assert result.missing_preferred_skills == ["aws"]
    assert result.unknown_requirements == []
    assert result.score == 100


def test_evaluate_candidate_strips_context_words_from_extracted_skills(monkeypatch):
    # Regression: Nova Micro extracts "AWS experience" / "Familiarity with
    # CI/CD" from the example job. The gaps must be reported as "aws"/"ci/cd".
    class VerboseSkillsAgent(FakeAgent):
        def __call__(self, prompt, structured_output_model=None):
            if structured_output_model is JobRequirements:
                return SimpleNamespace(
                    structured_output=JobRequirements(
                        required_skills=["Python"],
                        preferred_skills=["AWS experience", "Familiarity with CI/CD"],
                    )
                )
            if structured_output_model is CareerPlan:
                return SimpleNamespace(
                    structured_output=CareerPlan(
                        gap_preparation=[
                            GapPreparation(
                                skill="AWS experience", preparation_steps=["IAM fundamentals"]
                            ),
                        ]
                    )
                )
            return super().__call__(prompt, structured_output_model)

    monkeypatch.setattr(service, "build_agent", lambda: VerboseSkillsAgent())

    result = service.evaluate_candidate(RESUME, JOB)

    assert result.missing_preferred_skills == ["aws", "ci/cd"]
    assert [(gap.skill, gap.severity) for gap in result.skill_gaps] == [
        ("aws", "preferred"),
        ("ci/cd", "preferred"),
    ]
    assert result.skill_gaps[0].preparation_steps == ["IAM fundamentals"]


def test_explanation_cleaned_of_model_artifacts(monkeypatch):
    # Regression: Nova Micro leaks <thinking> blocks into free-text output.
    class LeakyTextResult:
        structured_output = None

        def __str__(self):
            return (
                "<thinking>score is 100</thinking>\n\n\n\nStrong overlap on the core backend stack."
            )

    class LeakyAgent(FakeAgent):
        def __call__(self, prompt, structured_output_model=None):
            if structured_output_model is None:
                return LeakyTextResult()
            return super().__call__(prompt, structured_output_model)

    monkeypatch.setattr(service, "build_agent", lambda: LeakyAgent())

    result = service.evaluate_candidate(RESUME, JOB)

    assert result.reasoning == "Strong overlap on the core backend stack."


def test_evaluate_candidate_matches_deterministic_expectation(monkeypatch):
    monkeypatch.setattr(service, "build_agent", lambda: FakeAgent())

    result = service.evaluate_candidate(RESUME, JOB)

    profile = CandidateProfile(
        skills=["Python", "REST API design and integration", "PostgreSQL", "Docker"],
        years_of_experience=2,
    )
    requirements = JobRequirements(
        required_skills=["Python", "REST API development", "PostgreSQL", "Docker"],
        preferred_skills=["AWS"],
        min_years_experience=1,
    )
    expected_match = service.build_match_result(profile, requirements)

    assert result.score == expected_match.score
    assert result.matched_skills == expected_match.matched_skills
    assert result.missing_required_skills == expected_match.missing_required_skills
    assert result.recommendation == service.decide_recommendation(expected_match)


def test_generate_career_plan_returns_structured_draft(monkeypatch):
    monkeypatch.setattr(service, "build_agent", lambda: FakeAgent())

    plan = service.generate_career_plan(
        service.build_match_result(
            CandidateProfile(skills=["Python"], years_of_experience=2),
            JobRequirements(
                required_skills=["Python"], preferred_skills=["AWS"], min_years_experience=1
            ),
        )
    )

    assert isinstance(plan, CareerPlan)
    # Raw LLM draft: validation and normalization happen afterwards in code.
    assert plan.interview_topics == [
        "PostgreSQL indexes",
        "REST design",
        "postgresql indexes",
        "",
        "IAM fundamentals",
    ]
    assert [p.skill for p in plan.gap_preparation] == ["AWS", "Kubernetes"]


def test_evaluate_candidate_propagates_model_failure(monkeypatch):
    monkeypatch.setattr(service, "build_agent", lambda: FailingAgent())

    try:
        service.evaluate_candidate(RESUME, JOB)
    except RuntimeError as exc:
        assert "model unavailable" in str(exc)
    else:
        raise AssertionError("expected RuntimeError to propagate")


def test_explanation_prompt_contains_deterministic_result():
    prompt = service.EXPLANATION_PROMPT.format(
        recommendation="MAYBE",
        score=50,
        matched_skills="python",
        matched_preferred_skills="none",
        missing_required_skills="aws",
        missing_preferred_skills="none",
        missing_critical_skills="none",
        unknown_requirements="none",
        experience_display="unknown (not stated or not verifiable)",
        evidence="2 years of backend development",
        strengths="Meets 1 of 2 required skills: python",
        skill_gaps="aws (required)",
    )

    assert "Recommendation: MAYBE" in prompt
    assert "Score: 50" in prompt
    assert "Missing required skills: aws" in prompt
    assert "Strengths: Meets 1 of 2 required skills: python" in prompt
    assert "Skill gaps to prepare: aws (required)" in prompt


def test_evaluate_resume_file_parses_then_evaluates(monkeypatch):
    from tests.pdfgen import make_pdf

    captured = {}

    def fake_evaluate(resume, job_description):
        captured["resume"] = resume
        captured["job"] = job_description
        return EvaluationResult(recommendation="APPLY", score=100)

    monkeypatch.setattr(service, "evaluate_candidate", fake_evaluate)

    pdf = make_pdf(
        [
            "Backend developer with 2 years of experience.",
            "- Python for backend services.",
        ]
    )
    result = service.evaluate_resume_file(pdf, "resume.pdf", JOB)

    assert result.recommendation == "APPLY"
    assert "Backend developer with 2 years" in captured["resume"]
    assert "Python for backend services" in captured["resume"]
    assert captured["job"] == JOB


def test_evaluate_resume_file_rejects_corrupt_pdf(monkeypatch):
    monkeypatch.setattr(
        service,
        "evaluate_candidate",
        lambda resume, job: (_ for _ in ()).throw(AssertionError("should not be reached")),
    )

    try:
        service.evaluate_resume_file(b"%PDF-1.4 broken", "resume.pdf", JOB)
    except ValueError as exc:
        assert "Corrupt" in str(exc)
    else:
        raise AssertionError("expected ResumeParseError to propagate")
