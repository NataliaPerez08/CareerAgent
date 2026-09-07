import json
import logging

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import get_session
from app.main import app
from app.models import Base
from app.resume_parser import ResumeTooLargeError
from app.schemas import EvaluationResult
from tests.pdfgen import make_pdf

# raise_server_exceptions=False lets the tests observe the 502 response
# produced by the global exception handler instead of re-raising the error.
client = TestClient(app, raise_server_exceptions=False)

JOB_DESCRIPTION = "Junior backend engineer. Requires Python, REST APIs, PostgreSQL and Docker."
RESUME_TEXT = (
    "Backend developer with 2 years of professional experience. "
    "Python, REST API design, PostgreSQL and Docker."
)
RESUME_PDF = make_pdf(
    [
        "Backend developer with 2 years of professional experience.",
        "- Python for backend services.",
        "- REST API design and integration.",
        "- PostgreSQL for relational persistence.",
        "- Docker for deployment packaging.",
    ]
)


@pytest.fixture(autouse=True)
def db_session():
    """Give every API test an isolated in-memory database."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)

    def override():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override
    yield
    app.dependency_overrides.pop(get_session, None)
    engine.dispose()


def fake_result() -> EvaluationResult:
    return EvaluationResult(
        recommendation="APPLY",
        score=100,
        matched_skills=["docker", "postgresql", "python", "rest api"],
        missing_preferred_skills=["aws"],
        experience_match=True,
        evidence=["2 years of professional software development experience"],
        reasoning="Strong overlap on the core backend stack.",
    )


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_documents_api():
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/health" in paths
    assert "/api/v1/evaluations" in paths
    assert "/api/v1/evaluations/upload" in paths
    assert "/api/v1/evaluations/{evaluation_id}" in paths
    assert "/api/v1/evaluations/stream" in paths
    assert "/api/v1/evaluations/upload/stream" in paths
    assert "/api/v1/batch/quick-ranking" in paths
    assert "/api/v1/jobs/fetch" in paths


def _parse_sse(text: str):
    """Parse the SSE body into [(event, data_json_str), ...]."""
    events = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        event_type = None
        data = None
        for line in block.split("\n"):
            if line.startswith("event:"):
                event_type = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
        if event_type and data is not None:
            events.append((event_type, data))
    return events


def test_stream_emits_progress_stages_then_result(monkeypatch):
    def fake(resume_text, job_description, timings=None, on_stage=None):
        for stage in (
            "profile_extraction",
            "requirements_extraction",
            "deterministic_matching",
            "recommendation",
            "plan_and_explanation",
        ):
            on_stage(stage)
        return fake_result()

    monkeypatch.setattr("app.main.evaluate_candidate", fake)

    response = client.post(
        "/api/v1/evaluations/stream",
        json={"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    events = _parse_sse(response.text)
    stages = [json.loads(data) for event, data in events if event == "stage"]
    assert stages == [
        "profile_extraction",
        "requirements_extraction",
        "deterministic_matching",
        "recommendation",
        "plan_and_explanation",
        "persistence",
    ]

    result_event = next((data for event, data in events if event == "result"), None)
    assert result_event is not None
    payload = json.loads(result_event)
    assert payload["recommendation"] == "APPLY"
    assert payload["score"] == 100
    assert payload["matched_skills"] == ["docker", "postgresql", "python", "rest api"]


def test_stream_reports_error_event_on_model_failure(monkeypatch):
    def failing(resume_text, job_description, timings=None, on_stage=None):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.main.evaluate_candidate", failing)
    response = client.post(
        "/api/v1/evaluations/stream",
        json={"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION},
    )
    assert response.status_code == 200
    error_event = next((data for event, data in _parse_sse(response.text) if event == "error"), None)
    assert error_event is not None
    assert json.loads(error_event)["status_code"] == 502


def test_stream_reports_model_timeout(monkeypatch):
    def timing_out(resume_text, job_description, timings=None, on_stage=None):
        raise TimeoutError("read timed out")

    monkeypatch.setattr("app.main.evaluate_candidate", timing_out)
    response = client.post(
        "/api/v1/evaluations/stream",
        json={"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION},
    )
    error_event = next((data for event, data in _parse_sse(response.text) if event == "error"))
    assert json.loads(error_event)["status_code"] == 504


def test_stream_upload_emits_resume_parse_stage(monkeypatch):
    def fake(resume_text, filename, job_description, timings=None, on_stage=None):
        on_stage("resume_parse")
        return fake_result()

    monkeypatch.setattr("app.main.evaluate_resume_file", fake)
    response = client.post(
        "/api/v1/evaluations/upload/stream",
        files={"resume": ("resume.txt", b"Backend developer 2 years Python SQL.", "text/plain")},
        data={"job_description": JOB_DESCRIPTION},
    )
    assert response.status_code == 200
    events = _parse_sse(response.text)
    stages = [json.loads(data) for event, data in events if event == "stage"]
    assert "resume_parse" in stages
    assert stages.index("resume_parse") < len(stages)
    assert any(event == "result" for event, _ in events)


def test_stream_upload_reports_oversized_file_error(monkeypatch):
    def failing(resume_text, filename, job_description, timings=None, on_stage=None):
        raise ResumeTooLargeError("resume too large")

    monkeypatch.setattr("app.main.evaluate_resume_file", failing)
    response = client.post(
        "/api/v1/evaluations/upload/stream",
        files={"resume": ("resume.pdf", b"%PDF-1.4 fake", "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )
    error_event = next((data for event, data in _parse_sse(response.text) if event == "error"))
    assert json.loads(error_event)["status_code"] == 413


def test_create_evaluation_returns_structured_result(monkeypatch):
    monkeypatch.setattr(
        "app.main.evaluate_candidate", lambda resume_text, job_description, timings=None: fake_result()
    )

    response = client.post(
        "/api/v1/evaluations",
        json={"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation"] == "APPLY"
    assert payload["score"] == 100
    assert payload["matched_skills"] == ["docker", "postgresql", "python", "rest api"]
    assert payload["missing_preferred_skills"] == ["aws"]
    assert payload["experience_match"] is True
    assert payload["evidence"] == ["2 years of professional software development experience"]


def test_create_evaluation_persists_and_is_recoverable(monkeypatch):
    monkeypatch.setattr(
        "app.main.evaluate_candidate", lambda resume_text, job_description, timings=None: fake_result()
    )

    created = client.post(
        "/api/v1/evaluations",
        json={
            "resume_text": RESUME_TEXT,
            "job_description": "Junior Backend Engineer\n\nRequires Python.",
        },
    )
    assert created.status_code == 200
    payload = created.json()
    assert isinstance(payload["id"], int)
    assert payload["job_title"] == "Junior Backend Engineer"
    assert payload["created_at"] is not None

    fetched = client.get(f"/api/v1/evaluations/{payload['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["score"] == payload["score"]
    assert fetched.json()["recommendation"] == payload["recommendation"]
    assert fetched.json()["matched_skills"] == payload["matched_skills"]
    assert fetched.json()["job_title"] == "Junior Backend Engineer"


def test_persistence_failure_returns_result_without_id(monkeypatch):
    monkeypatch.setattr(
        "app.main.evaluate_candidate", lambda resume_text, job_description, timings=None: fake_result()
    )

    def failing_save(*args, **kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr("app.main.save_evaluation", failing_save)

    response = client.post(
        "/api/v1/evaluations",
        json={"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["id"] is None
    assert payload["recommendation"] == "APPLY"
    assert payload["score"] == 100


def test_list_evaluations_returns_history(monkeypatch):
    def fake_evaluate(resume_text, job_description, timings=None):
        return fake_result()

    monkeypatch.setattr("app.main.evaluate_candidate", fake_evaluate)

    first = client.post(
        "/api/v1/evaluations",
        json={"resume_text": RESUME_TEXT, "job_description": "First Job\n\nRequires Python."},
    )
    second = client.post(
        "/api/v1/evaluations",
        json={"resume_text": RESUME_TEXT, "job_description": "Second Job\n\nRequires Python."},
    )
    assert first.status_code == second.status_code == 200

    response = client.get("/api/v1/evaluations")
    assert response.status_code == 200
    history = response.json()
    assert [entry["id"] for entry in history] == [
        second.json()["id"],
        first.json()["id"],
    ]
    assert history[0]["job_title"] == "Second Job"
    assert history[0]["score"] == 100
    assert history[0]["recommendation"] == "APPLY"


def test_get_evaluation_unknown_id_returns_404():
    response = client.get("/api/v1/evaluations/999")
    assert response.status_code == 404
    assert response.json()["detail"] == "Evaluation not found."


def test_create_evaluation_logs_structured_timings(monkeypatch, caplog):
    def fake_evaluate(resume_text, job_description, timings=None):
        assert timings is not None
        timings.start("profile_extraction")
        timings.stop("profile_extraction")
        return fake_result()

    monkeypatch.setattr("app.main.evaluate_candidate", fake_evaluate)

    with caplog.at_level(logging.INFO):
        response = client.post(
            "/api/v1/evaluations",
            json={"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION},
        )

    assert response.status_code == 200
    payload = json.loads(
        next(m for m in caplog.messages if '"event": "api_evaluation_timings"' in m)
    )
    assert payload["event"] == "api_evaluation_timings"
    assert payload["request_total_ms"] >= 0
    assert payload["persistence_ms"] >= 0
    assert payload["profile_extraction_ms"] >= 0
    assert payload["llm_ms"] >= 0
    assert payload["job_title"] == "Junior backend engineer. Requires Python, REST APIs, PostgreSQL and Docker."


def test_create_evaluation_rejects_invalid_payload():
    response = client.post("/api/v1/evaluations", json=["not", "an", "object"])
    assert response.status_code == 422


def test_create_evaluation_rejects_missing_fields():
    response = client.post("/api/v1/evaluations", json={})
    assert response.status_code == 422


def test_create_evaluation_rejects_empty_resume():
    response = client.post(
        "/api/v1/evaluations",
        json={"resume_text": "", "job_description": JOB_DESCRIPTION},
    )
    assert response.status_code == 422


def test_create_evaluation_rejects_empty_job():
    response = client.post(
        "/api/v1/evaluations",
        json={"resume_text": RESUME_TEXT, "job_description": ""},
    )
    assert response.status_code == 422


def test_create_evaluation_rejects_oversized_text():
    response = client.post(
        "/api/v1/evaluations",
        json={"resume_text": "x" * 100_001, "job_description": JOB_DESCRIPTION},
    )
    assert response.status_code == 422


def test_create_evaluation_returns_502_on_model_failure(monkeypatch):
    def failing_evaluate(resume_text, job_description, timings=None):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.main.evaluate_candidate", failing_evaluate)

    response = client.post(
        "/api/v1/evaluations",
        json={"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Agent execution failed."


def test_upload_returns_structured_result(monkeypatch):
    seen = {}

    def fake_evaluate(resume_text, job_description, timings=None):
        seen["resume_text"] = resume_text
        seen["job_description"] = job_description
        return fake_result()

    monkeypatch.setattr("app.main.evaluate_candidate", fake_evaluate)

    response = client.post(
        "/api/v1/evaluations/upload",
        files={"resume": ("resume.pdf", RESUME_PDF, "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 200
    assert "Backend developer with 2 years" in seen["resume_text"]
    assert seen["job_description"] == JOB_DESCRIPTION
    payload = response.json()
    assert payload["recommendation"] == "APPLY"
    assert payload["score"] == 100
    assert isinstance(payload["id"], int)


def test_upload_rejects_unsupported_format():
    response = client.post(
        "/api/v1/evaluations/upload",
        files={"resume": ("resume.docx", b"fake docx", "application/octet-stream")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 415
    assert "Supported" in response.json()["detail"]


def test_upload_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr("app.resume_parser.max_resume_size_bytes", lambda: 10)

    response = client.post(
        "/api/v1/evaluations/upload",
        files={"resume": ("resume.pdf", b"x" * 100, "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 413


def test_upload_rejects_empty_file():
    response = client.post(
        "/api/v1/evaluations/upload",
        files={"resume": ("resume.pdf", b"", "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_upload_rejects_corrupt_pdf():
    response = client.post(
        "/api/v1/evaluations/upload",
        files={"resume": ("resume.pdf", b"%PDF-1.4 broken content", "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 422


def test_upload_rejects_scanned_pdf_without_text():
    response = client.post(
        "/api/v1/evaluations/upload",
        files={"resume": ("resume.pdf", make_pdf([]), "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 422
    assert "scanned or image-based" in response.json()["detail"]


def test_upload_validates_job_description_length():
    response = client.post(
        "/api/v1/evaluations/upload",
        files={"resume": ("resume.pdf", RESUME_PDF, "application/pdf")},
        data={"job_description": "too short"},
    )

    assert response.status_code == 422


def test_upload_returns_502_on_model_failure(monkeypatch):
    def failing_evaluate(resume_text, job_description, timings=None):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.main.evaluate_candidate", failing_evaluate)

    response = client.post(
        "/api/v1/evaluations/upload",
        files={"resume": ("resume.pdf", RESUME_PDF, "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Agent execution failed."


def _fake_profile(*skills):
    from app.schemas import CandidateProfile

    return CandidateProfile(skills=list(skills), years_of_experience=2, evidence=[])


def _fake_fetch(postings_by_url):
    from app import job_ingestion

    def fake_fetch(url):
        posting = postings_by_url.get(url)
        if posting is not None:
            return job_ingestion.JobPosting(
                title=posting[0], company="Corp", description=posting[1], source_url=url
            )
        raise job_ingestion.JobFetchStatusError(f"blocked: {url}")

    return fake_fetch


def test_quick_ranking_sorted_and_deterministic(monkeypatch):
    monkeypatch.setattr(
        "app.main.extract_candidate_profile",
        lambda resume: _fake_profile("python", "postgresql", "docker"),
    )
    monkeypatch.setattr(
        "app.job_ingestion.fetch_job",
        _fake_fetch(
            {
                "https://a.example/python": ("Python job", "Need python and docker."),
                "https://a.example/full": ("Full stack", "python postgresql docker all three"),
            }
        ),
    )

    response = client.post(
        "/api/v1/batch/quick-ranking",
        json={
            "resume_text": RESUME_TEXT,
            "job_urls": ["https://a.example/python", "https://a.example/full"],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["candidate_skills"] == ["docker", "postgresql", "python"]
    assert [job["url"] for job in body["jobs"]] == [
        "https://a.example/full",
        "https://a.example/python",
    ]
    assert body["jobs"][0]["score"] == 100
    assert body["jobs"][0]["recommendation"] == "APPLY"
    assert body["jobs"][1]["score"] == 67


def test_quick_ranking_turns_failed_url_into_error_row(monkeypatch):
    monkeypatch.setattr(
        "app.main.extract_candidate_profile",
        lambda resume: _fake_profile("python"),
    )
    monkeypatch.setattr(
        "app.job_ingestion.fetch_job",
        _fake_fetch({"https://a.example/ok": ("OK", "Need python.")}),
    )

    response = client.post(
        "/api/v1/batch/quick-ranking",
        json={
            "resume_text": RESUME_TEXT,
            "job_urls": ["https://a.example/ok", "https://a.example/broken"],
        },
    )
    assert response.status_code == 200, response.text
    jobs = response.json()["jobs"]
    assert len(jobs) == 2
    assert jobs[0]["error"] is None
    assert jobs[1]["error"] == "blocked: https://a.example/broken"


def test_quick_ranking_validates_payload():
    response = client.post(
        "/api/v1/batch/quick-ranking",
        json={"resume_text": "short", "job_urls": []},
    )
    assert response.status_code == 422
