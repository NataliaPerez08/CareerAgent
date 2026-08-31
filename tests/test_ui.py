from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_root_serves_ui():
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert "CareerAgent" in response.text


def test_static_assets_are_served():
    for path, kind in (
        ("/static/styles.css", "text/css"),
        ("/static/app.js", "text/javascript"),
    ):
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith(kind)


def test_ui_calls_versioned_api():
    response = client.get("/static/app.js")
    assert response.status_code == 200
    assert "/api/v1/evaluations" in response.text
    assert "/api/v1/evaluations/upload" in response.text


def test_ui_html_declares_elements_used_by_app_js():
    html = client.get("/").text
    element_ids = (
        "tab-paste",
        "tab-upload",
        "resume-text",
        "resume-file",
        "job-description",
        "analyze",
        "status",
        "error",
        "result",
        "recommendation",
        "score-value",
        "matched",
        "missing",
        "evidence",
        "gaps",
        "topics",
        "plan",
        "reasoning",
    )
    for element_id in element_ids:
        assert f'id="{element_id}"' in html
