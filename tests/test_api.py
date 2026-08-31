from fastapi.testclient import TestClient

from app.main import app
from app.schemas import EvaluationResult
from tests.pdfgen import make_pdf

client = TestClient(app)

JOB_DESCRIPTION = "Junior backend engineer. Requires Python, REST APIs, PostgreSQL and Docker."
RESUME_PDF = make_pdf(
    [
        "Backend developer with 2 years of professional experience.",
        "- Python for backend services.",
        "- REST API design and integration.",
        "- PostgreSQL for relational persistence.",
        "- Docker for deployment packaging.",
    ]
)

def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_evaluate_validates_input():
    response = client.post(
        "/evaluate",
        json={"resume": "short", "job_description": "also short"},
    )
    assert response.status_code == 422


def test_evaluate_returns_structured_result(monkeypatch):
    def fake_evaluate(resume, job_description):
        return EvaluationResult(
            recommendation="APPLY",
            score=100,
            matched_skills=["docker", "postgresql", "python", "rest api"],
            missing_preferred_skills=["aws"],
            experience_match=True,
            evidence=["2 years of professional software development experience"],
            reasoning="Strong overlap on the core backend stack.",
        )

    monkeypatch.setattr("app.main.evaluate_candidate", fake_evaluate)

    response = client.post(
        "/evaluate",
        json={
            "resume": "Backend developer with 2 years of Python and Docker experience.",
            "job_description": "Junior backend engineer. Requires Python and Docker.",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation"] == "APPLY"
    assert payload["score"] == 100
    assert payload["matched_skills"] == ["docker", "postgresql", "python", "rest api"]
    assert payload["missing_preferred_skills"] == ["aws"]
    assert payload["experience_match"] is True
    assert payload["evidence"] == ["2 years of professional software development experience"]


def test_evaluate_returns_502_on_model_failure(monkeypatch):
    def failing_evaluate(resume, job_description):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr("app.main.evaluate_candidate", failing_evaluate)

    response = client.post(
        "/evaluate",
        json={
            "resume": "Backend developer with 2 years of Python and Docker experience.",
            "job_description": "Junior backend engineer. Requires Python and Docker.",
        },
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Agent execution failed."


def test_upload_returns_structured_result(monkeypatch):
    def fake_evaluate_resume_file(data, filename, job_description):
        assert filename == "resume.pdf"
        assert len(data) == len(RESUME_PDF)
        return EvaluationResult(
            recommendation="APPLY",
            score=100,
            matched_skills=["docker", "postgresql", "python", "rest api"],
            experience_match=True,
            reasoning="Strong overlap on the core backend stack.",
        )

    monkeypatch.setattr("app.main.evaluate_resume_file", fake_evaluate_resume_file)

    response = client.post(
        "/evaluate/upload",
        files={"resume": ("resume.pdf", RESUME_PDF, "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["recommendation"] == "APPLY"
    assert payload["score"] == 100
    assert payload["matched_skills"] == ["docker", "postgresql", "python", "rest api"]


def test_upload_rejects_unsupported_format():
    response = client.post(
        "/evaluate/upload",
        files={"resume": ("resume.docx", b"fake docx", "application/octet-stream")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 415
    assert "Supported" in response.json()["detail"]


def test_upload_rejects_oversized_file(monkeypatch):
    monkeypatch.setattr("app.resume_parser.max_resume_size_bytes", lambda: 10)

    response = client.post(
        "/evaluate/upload",
        files={"resume": ("resume.pdf", b"x" * 100, "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 413


def test_upload_rejects_empty_file():
    response = client.post(
        "/evaluate/upload",
        files={"resume": ("resume.pdf", b"", "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 422
    assert "empty" in response.json()["detail"]


def test_upload_rejects_corrupt_pdf():
    response = client.post(
        "/evaluate/upload",
        files={"resume": ("resume.pdf", b"%PDF-1.4 broken content", "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 422


def test_upload_rejects_scanned_pdf_without_text():
    response = client.post(
        "/evaluate/upload",
        files={"resume": ("resume.pdf", make_pdf([]), "application/pdf")},
        data={"job_description": JOB_DESCRIPTION},
    )

    assert response.status_code == 422
    assert "scanned or image-based" in response.json()["detail"]


def test_upload_validates_job_description_length():
    response = client.post(
        "/evaluate/upload",
        files={"resume": ("resume.pdf", RESUME_PDF, "application/pdf")},
        data={"job_description": "too short"},
    )

    assert response.status_code == 422
