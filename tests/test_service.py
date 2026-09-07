import json
import logging
from types import SimpleNamespace

from app import service
from app.schemas import (
    CandidateProfile,
    CareerPlan,
    EvaluationResult,
    GapPreparation,
    JobRequirements,
)
from app.timing import EvaluationTimings

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


class FakeAgent:
    """Stands-in for the Strands agent: returns canned structured outputs.

    Every pipeline step is a structured single-shot call, so an unstructured
    call is a bug: the pipeline must not make free-text model calls.
    """

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
                    reasoning="Strong overlap on the core backend stack.",
                )
            )
        raise AssertionError(f"unexpected unstructured model call: {structured_output_model!r}")


class FailingAgent:
    def __call__(self, prompt, structured_output_model=None):
        raise RuntimeError("model unavailable")


def test_extract_candidate_profile_drops_invented_evidence(monkeypatch):
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

    profile = service.extract_candidate_profile(RESUME)

    assert profile.skills == ["Python", "REST API design and integration", "PostgreSQL", "Docker"]
    assert profile.years_of_experience == 2
    assert profile.evidence == ["2 years of professional software development experience"]


def test_extract_job_requirements_returns_structured(monkeypatch):
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

    requirements = service.extract_job_requirements(JOB)

    assert requirements.required_skills == [
        "Python",
        "REST API development",
        "PostgreSQL",
        "Docker",
    ]
    assert requirements.preferred_skills == ["AWS"]
    assert requirements.min_years_experience == 1


def test_evaluate_candidate_reports_stage_progress(monkeypatch):
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

    stages = []
    service.evaluate_candidate(RESUME, JOB, on_stage=stages.append)

    assert stages == [
        "profile_extraction",
        "requirements_extraction",
        "deterministic_matching",
        "recommendation",
        "plan_and_explanation",
    ]


def test_evaluate_candidate_composes_structured_result(monkeypatch):
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

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
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

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

    monkeypatch.setattr(service, "build_pipeline_agent", lambda: OverlappingAgent())

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

    monkeypatch.setattr(service, "build_pipeline_agent", lambda: VerboseSkillsAgent())

    result = service.evaluate_candidate(RESUME, JOB)

    assert result.missing_preferred_skills == ["aws", "ci/cd"]
    assert [(gap.skill, gap.severity) for gap in result.skill_gaps] == [
        ("aws", "preferred"),
        ("ci/cd", "preferred"),
    ]
    assert result.skill_gaps[0].preparation_steps == ["IAM fundamentals"]


def test_explanation_cleaned_of_model_artifacts(monkeypatch):
    # Regression: Nova Micro leaks <thinking> blocks into generated text.
    class LeakyAgent(FakeAgent):
        def __call__(self, prompt, structured_output_model=None):
            result = super().__call__(prompt, structured_output_model)
            if structured_output_model is CareerPlan:
                plan = result.structured_output.model_copy(
                    update={
                        "reasoning": (
                            "<thinking>score is 100</thinking>\n\n\n\n"
                            "Strong overlap on the core backend stack."
                        )
                    }
                )
                return SimpleNamespace(structured_output=plan)
            return result

    monkeypatch.setattr(service, "build_pipeline_agent", lambda: LeakyAgent())

    result = service.evaluate_candidate(RESUME, JOB)

    assert result.reasoning == "Strong overlap on the core backend stack."


def test_evaluate_candidate_matches_deterministic_expectation(monkeypatch):
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

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


def test_draft_career_plan_returns_structured_draft(monkeypatch):
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

    profile = CandidateProfile(skills=["Python"], years_of_experience=2)
    requirements = JobRequirements(
        required_skills=["Python"], preferred_skills=["AWS"], min_years_experience=1
    )
    match = service.build_match_result(profile, requirements)

    plan = service.draft_career_plan(
        profile,
        requirements,
        match,
        service.decide_recommendation(match),
        strengths=["Meets 1 of 1 required skills: python"],
        skill_gaps=service.build_skill_gaps(match),
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
    assert plan.reasoning == "Strong overlap on the core backend stack."


def test_evaluate_candidate_propagates_model_failure(monkeypatch):
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FailingAgent())

    try:
        service.evaluate_candidate(RESUME, JOB)
    except RuntimeError as exc:
        assert "model unavailable" in str(exc)
    else:
        raise AssertionError("expected RuntimeError to propagate")


def test_career_plan_prompt_contains_deterministic_result():
    prompt = service.CAREER_PLAN_PROMPT.format(
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
    # The single merged call must ask for the explanation too.
    assert "reasoning" in prompt
    assert "interview_topics" in prompt
    assert "gap_preparation" in prompt


def test_evaluate_candidate_records_pipeline_stage_timings(monkeypatch):
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

    timings = EvaluationTimings()
    result = service.evaluate_candidate(RESUME, JOB, timings=timings)

    assert result.recommendation == "APPLY"
    ms = timings.aggregate_ms()
    for stage in (
        "profile_extraction",
        "requirements_extraction",
        "deterministic_matching",
        "recommendation",
        "plan_and_explanation",
    ):
        assert f"{stage}_ms" in ms, f"missing stage: {stage}"
    assert ms["llm_ms"] > 0
    assert ms["tools_ms"] >= 0


def test_record_model_call_extracts_strands_metrics():
    """The loop cost of a real agent call is read from Strands metrics."""
    tool_metric = SimpleNamespace(call_count=2)
    result = SimpleNamespace(
        metrics=SimpleNamespace(
            cycle_count=3,
            tool_metrics={"calculate_match": tool_metric},
            accumulated_usage={"inputTokens": 1500, "outputTokens": 320, "totalTokens": 1820},
        )
    )

    timings = EvaluationTimings()
    service._record_model_call(timings, result)

    assert timings.counters() == {
        "input_tokens": 1500,
        "llm_calls": 1,
        "llm_cycles": 3,
        "output_tokens": 320,
        "tool_calls": 2,
    }


def test_record_model_call_without_metrics_counts_only_the_call():
    result = SimpleNamespace(structured_output=None)

    timings = EvaluationTimings()
    service._record_model_call(timings, result)

    # Nothing is invented: no metrics means no cycles/tools/tokens reported.
    assert timings.counters() == {"llm_calls": 1}


def test_record_model_call_is_a_noop_without_a_collector():
    service._record_model_call(None, SimpleNamespace(metrics=None))


def test_record_model_call_ignores_structured_output_pseudo_tool():
    """Strands registers the schema as an internal pseudo-tool; that is not
    an agent tool call and must not inflate ``tool_calls``."""
    schema_metric = SimpleNamespace(call_count=1)
    real_tool_metric = SimpleNamespace(call_count=2)
    result = SimpleNamespace(
        metrics=SimpleNamespace(
            cycle_count=1,
            tool_metrics={
                "CandidateProfile": schema_metric,
                "calculate_match": real_tool_metric,
            },
            accumulated_usage={"inputTokens": 900, "outputTokens": 200},
        )
    )

    timings = EvaluationTimings()
    service._record_model_call(timings, result, output_model=service.CandidateProfile)

    assert timings.counters()["tool_calls"] == 2
    assert timings.counters()["llm_cycles"] == 1


def test_pipeline_makes_three_model_calls_and_no_tool_calls(monkeypatch):
    """Day 2 contract: 3 single-shot calls, no agent loop, no tool round-trips."""
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

    timings = EvaluationTimings()
    service.evaluate_candidate(RESUME, JOB, timings=timings)

    counters = timings.counters()
    assert counters["llm_calls"] == 3
    assert counters.get("tool_calls", 0) == 0
    # The merged plan+explanation call replaced two separate model calls.
    assert "career_plan_ms" not in timings.as_ms()
    assert "explanation_ms" not in timings.as_ms()


def test_evaluate_candidate_logs_structured_summary_when_owning_timings(monkeypatch, caplog):
    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

    with caplog.at_level(logging.INFO):
        service.evaluate_candidate(RESUME, JOB)

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if '"event": "evaluation_pipeline_timings"' in record.getMessage()
    ]
    assert len(events) == 1
    assert events[0]["llm_ms"] >= 0
    assert events[0]["recommendation"] == "APPLY"
    # No resume/job content leaks into the timing summary.
    assert not any(word in json.dumps(events[0]) for word in ("Python", "backend", "Requirements"))


def test_evaluate_resume_file_records_resume_parse(monkeypatch):
    from tests.pdfgen import make_pdf

    monkeypatch.setattr(service, "build_pipeline_agent", lambda: FakeAgent())

    timings = EvaluationTimings()
    pdf = make_pdf(
        [
            "Backend developer with 2 years of professional backend development experience.",
            "- Python for backend services.",
            "- PostgreSQL for relational persistence.",
            "- Docker for deployment packaging.",
        ]
    )
    service.evaluate_resume_file(pdf, "resume.pdf", JOB, timings=timings)

    ms = timings.aggregate_ms()
    assert "resume_parse_ms" in ms
    assert ms["resume_parse_ms"] >= 0


def test_evaluate_resume_file_parses_then_evaluates(monkeypatch):
    from tests.pdfgen import make_pdf

    captured = {}

    def fake_evaluate(resume, job_description, timings=None, on_stage=None):
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
