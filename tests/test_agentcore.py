import base64
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.agentcore_runtime import agentcore_app, evaluate
from app.schemas import EvaluationResult
from tests.pdfgen import make_pdf

client = TestClient(agentcore_app, raise_server_exceptions=False)

JOB_DESCRIPTION = "Junior backend engineer. Requires Python, REST APIs, PostgreSQL and Docker."
RESUME_TEXT = (
    "Backend developer with 2 years of professional experience. "
    "Python, REST API design, PostgreSQL and Docker."
)
RESUME_PDF = make_pdf(
    [
        "Backend developer with 2 years of professional experience.",
        "- Python for backend services.",
        "- Docker for deployment packaging.",
    ]
)


def fake_result() -> EvaluationResult:
    return EvaluationResult(
        recommendation="APPLY",
        score=100,
        matched_skills=["docker", "python"],
        experience_match=True,
        evidence=["2 years of professional software development experience"],
        reasoning="Strong overlap on the core backend stack.",
    )


@pytest.fixture
def mock_evaluate(monkeypatch):
    seen = {}

    def fake_evaluate(resume_text, job_description, timings=None):
        seen["resume_text"] = resume_text
        seen["job_description"] = job_description
        return fake_result()

    monkeypatch.setattr("app.agentcore_runtime.evaluate_candidate", fake_evaluate)
    return seen


def test_evaluate_text_payload(mock_evaluate):
    payload = {"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION}

    result = evaluate(payload)

    assert result["recommendation"] == "APPLY"
    assert result["score"] == 100
    assert mock_evaluate["resume_text"] == RESUME_TEXT
    assert mock_evaluate["job_description"] == JOB_DESCRIPTION


def test_evaluate_base64_pdf_payload(mock_evaluate):
    payload = {
        "resume_b64": base64.b64encode(RESUME_PDF).decode(),
        "resume_filename": "cv.pdf",
        "job_description": JOB_DESCRIPTION,
    }

    result = evaluate(payload)

    assert result["recommendation"] == "APPLY"
    assert "Backend developer with 2 years" in mock_evaluate["resume_text"]


def test_evaluate_rejects_non_object_payload():
    with pytest.raises(ValueError, match="JSON object"):
        evaluate("just a string")


def test_evaluate_rejects_both_resume_inputs():
    payload = {
        "resume_text": RESUME_TEXT,
        "resume_b64": base64.b64encode(RESUME_PDF).decode(),
        "job_description": JOB_DESCRIPTION,
    }

    with pytest.raises(ValueError, match="not both"):
        evaluate(payload)


def test_evaluate_rejects_short_job(mock_evaluate):
    with pytest.raises(ValueError, match="job_description"):
        evaluate({"resume_text": RESUME_TEXT, "job_description": "short"})


def test_evaluate_rejects_missing_resume(mock_evaluate):
    with pytest.raises(ValueError, match="resume_text"):
        evaluate({"job_description": JOB_DESCRIPTION})


def test_evaluate_rejects_oversized_resume_text(mock_evaluate):
    with pytest.raises(ValueError, match="resume_text"):
        evaluate({"resume_text": "x" * 100_001, "job_description": JOB_DESCRIPTION})


def test_evaluate_rejects_invalid_base64(mock_evaluate):
    with pytest.raises(ValueError, match="base64"):
        evaluate(
            {
                "resume_b64": "%%%not-base64%%%",
                "job_description": JOB_DESCRIPTION,
            }
        )


def test_evaluate_rejects_oversized_file(mock_evaluate, monkeypatch):
    monkeypatch.setattr("app.agentcore_runtime.max_resume_size_bytes", lambda: 10)

    with pytest.raises(ValueError, match="maximum allowed size"):
        evaluate(
            {
                "resume_b64": base64.b64encode(b"x" * 100).decode(),
                "resume_filename": "cv.pdf",
                "job_description": JOB_DESCRIPTION,
            }
        )


def test_evaluate_rejects_scanned_pdf(mock_evaluate):
    with pytest.raises(ValueError, match="scanned or image-based"):
        evaluate(
            {
                "resume_b64": base64.b64encode(make_pdf([])).decode(),
                "resume_filename": "cv.pdf",
                "job_description": JOB_DESCRIPTION,
            }
        )


def test_evaluate_logs_structured_timings(monkeypatch, caplog):
    def fake_evaluate(resume_text, job_description, timings=None):
        assert timings is not None
        timings.start("profile_extraction")
        timings.stop("profile_extraction")
        return fake_result()

    monkeypatch.setattr("app.agentcore_runtime.evaluate_candidate", fake_evaluate)

    with caplog.at_level(logging.INFO):
        evaluate({"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION})

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if '"event": "agentcore_evaluation_timings"' in record.getMessage()
    ]
    assert len(events) == 1
    assert events[0]["request_total_ms"] >= 0
    assert events[0]["profile_extraction_ms"] >= 0
    assert events[0]["llm_ms"] >= 0
    assert events[0]["recommendation"] == "APPLY"


def test_evaluate_base64_records_resume_parse_timing(monkeypatch, caplog):
    seen = {}

    def fake_evaluate(resume_text, job_description, timings=None):
        seen["resume_text"] = resume_text
        return fake_result()

    monkeypatch.setattr("app.agentcore_runtime.evaluate_candidate", fake_evaluate)

    with caplog.at_level(logging.INFO):
        evaluate(
            {
                "resume_b64": base64.b64encode(RESUME_PDF).decode(),
                "resume_filename": "cv.pdf",
                "job_description": JOB_DESCRIPTION,
            }
        )

    events = [
        json.loads(record.getMessage())
        for record in caplog.records
        if '"event": "agentcore_evaluation_timings"' in record.getMessage()
    ]
    assert len(events) == 1
    assert events[0]["resume_parse_ms"] >= 0
    assert events[0]["request_total_ms"] >= 0


def test_ping_endpoint():
    response = client.get("/ping")
    assert response.status_code == 200


def test_invocations_endpoint_returns_result(mock_evaluate):
    response = client.post(
        "/invocations",
        json={"resume_text": RESUME_TEXT, "job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation"] == "APPLY"
    assert payload["score"] == 100


def test_invocations_endpoint_reports_invalid_payload(mock_evaluate):
    response = client.post(
        "/invocations",
        json={"resume_text": RESUME_TEXT, "job_description": "short"},
    )

    assert response.status_code == 500
    assert "job_description" in response.json()["error"]
