from types import SimpleNamespace

from app import service
from app.schemas import CandidateProfile, EvaluationResult, JobRequirements

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
    )

    assert "Recommendation: MAYBE" in prompt
    assert "Score: 50" in prompt
    assert "Missing required skills: aws" in prompt


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
