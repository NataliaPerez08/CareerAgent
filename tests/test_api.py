from fastapi.testclient import TestClient

from app.main import app
from app.schemas import EvaluationResult

client = TestClient(app)


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
