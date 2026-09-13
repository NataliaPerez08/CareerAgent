"""Unit and API tests for job ingestion (Día 4).

All network traffic is mocked with ``httpx.MockTransport`` — nothing here
touches the internet. The HTTP layer is exercised through the FastAPI
client with ``app.main.fetch_job_posting`` calling a stubbed
``job_ingestion.fetch_job``.
"""

import httpx
import pytest
from fastapi.testclient import TestClient

from app import job_ingestion

SAMPLE_HTML = """
<html><head>
  <meta property="og:title" content="Senior Backend Engineer">
  <meta property="og:site_name" content="Acme Corp">
  <meta property="og:description" content="We are hiring a senior backend
    engineer. You will work with Python, PostgreSQL, REST APIs and AWS.">
  <title>Senior Backend Engineer — Acme Corp</title>
</head><body><script>document.write("noise")</script>
<p>You will build logistics software.</p>
</body></html>
"""


def mock_get(handler):
    return httpx.MockTransport(handler)


def transport_responding(body: bytes, content_type: str = "text/html", status: int = 200):
    def handler(request):
        return httpx.Response(status, content=body, headers={"content-type": content_type})
    return mock_get(handler)


def test_fetch_extracts_structured_posting():
    posting = job_ingestion.fetch_job(
        "https://jobs.acme.com/senior-backend",
        transport=transport_responding(SAMPLE_HTML.encode()),
    )
    assert posting.title == "Senior Backend Engineer"
    assert posting.company == "Acme Corp"
    assert "Python, PostgreSQL, REST APIs and AWS" in posting.description
    assert posting.source_url == "https://jobs.acme.com/senior-backend"


def test_fetch_falls_back_to_body_text_when_no_meta():
    html = ("<html><head><title>Backend</title></head><body>"
            "<p>We need a backend developer with Python and SQL experience "
            "to build our internal tooling platform.</p></body></html>")
    posting = job_ingestion.fetch_job(
        "https://example.com/jobs/1",
        transport=transport_responding(html.encode()),
    )
    assert posting.title == "Backend"
    assert "Python" in posting.description


def test_fetch_plain_text_response_uses_raw_text():
    text = ("Backend engineer role. Requires Python, PostgreSQL and "
            "Docker. Start working on our platform team.")
    posting = job_ingestion.fetch_job(
        "https://example.com/jobs.txt",
        transport=transport_responding(text.encode(), content_type="text/plain"),
    )
    assert posting.description == text
    assert posting.company == "Example"


def test_fetch_rejects_non_http_scheme():
    with pytest.raises(job_ingestion.JobUrlError):
        job_ingestion.fetch_job("ftp://jobs.example.com/a", transport=None)


def test_fetch_rejects_url_without_host():
    with pytest.raises(job_ingestion.JobUrlError):
        job_ingestion.fetch_job("https:///path", transport=None)


def test_fetch_rejects_loopback_and_private_hosts():
    for url in ("http://localhost/jobs/1", "http://127.0.0.1/jobs/1",
                "http://192.168.0.5/jobs/1", "http://10.0.0.5/jobs/1"):
        with pytest.raises(job_ingestion.JobUrlError):
            job_ingestion.fetch_job(url, transport=None)


def test_fetch_reports_timeout():
    def handler(request):
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(job_ingestion.JobFetchTimeoutError):
        job_ingestion.fetch_job(
            "https://example.com/slow",
            transport=mock_get(handler),
        )


def test_fetch_reports_upstream_status():
    with pytest.raises(job_ingestion.JobFetchStatusError):
        job_ingestion.fetch_job(
            "https://example.com/gone",
            transport=transport_responding(b"", status=404),
        )


def test_fetch_rejects_empty_description(monkeypatch):
    monkeypatch.setattr(job_ingestion, "MIN_DESCRIPTION_CHARS", 20)
    html = "<html><head><title>Job</title></head><body><p>No content</p></body></html>"
    with pytest.raises(job_ingestion.JobEmptyError):
        job_ingestion.fetch_job(
            "https://example.com/empty",
            transport=transport_responding(html),
        )


def test_fetch_rejects_oversized_page(monkeypatch):
    monkeypatch.setattr(job_ingestion, "MAX_RESPONSE_BYTES", 100)
    with pytest.raises(job_ingestion.JobFetchError):
        job_ingestion.fetch_job(
            "https://example.com/big",
            transport=transport_responding(b"x" * 200),
        )


def test_fetch_extracts_job_from_embedded_json():
    """SPA-style page: the posting lives in a data script tag (Phenom-style)."""
    html = """
    <html><head>
      <meta property="og:title" content="Technical Services Engineer">
      <meta property="og:site_name" content="MongoDB">
      <meta property="og:description" content="Mexico City">
      <title>Technical Services Engineer</title>
    </head><body>
      <script id="data-job" type="text/template">
        {"id": 8055356, "title": "Technical Services Engineer",
         "location": {"name": "Mexico City"},
         "content": "<p>Advise customers on complex MongoDB problems.</p>\\n<h3>Cool things you'll do</h3>\\n<p>Combine MongoDB expertise with teamwork.</p>"}
      </script>
      <script type="application/ld+json">{"@type": "MongoDB", "url": "https://x"}</script>
    </body></html>
    """
    posting = job_ingestion.fetch_job(
        "https://www.mongodb.com/careers/jobs/8055356",
        transport=transport_responding(html.encode()),
    )
    assert posting.title == "Technical Services Engineer"
    assert posting.company == "MongoDB"
    assert "Advise customers on complex MongoDB problems." in posting.description
    assert "Cool things you'll do" in posting.description


def test_fetch_extracts_json_ld_job_posting():
    """schema.org JobPosting JSON-LD (Greenhouse/Lever/Workday style)."""
    html = """
    <html><head><title>Platform Engineer</title></head><body>
      <script type="application/ld+json">
        {"@type": "JobPosting", "title": "Platform Engineer",
         "hiringOrganization": {"name": "Acme Corp"},
         "description": "<p>Own our CI/CD with Docker and Kubernetes.</p>"}
      </script>
    </body></html>
    """
    posting = job_ingestion.fetch_job(
        "https://example.com/jobs/42",
        transport=transport_responding(html.encode()),
    )
    assert posting.title == "Platform Engineer"
    assert posting.company == "Acme Corp"
    assert "Docker and Kubernetes" in posting.description


def test_fetch_ignores_broken_json_and_falls_back_to_body():
    html = (
        "<html><head><title>Backend</title></head><body>"
        "<script type='text/template'>{not valid json</script>"
        "<p>We need a backend developer with Python and SQL experience "
        "to build our internal tooling platform.</p></body></html>"
    )
    posting = job_ingestion.fetch_job(
        "https://example.com/jobs/7",
        transport=transport_responding(html.encode()),
    )
    assert "Python" in posting.description


def test_fetch_rejects_json_title_without_description():
    html = (
        '<html><head><title>Job</title></head><body>'
        '<script type="application/json">{"title": "Just a title"}</script>'
        "</body></html>"
    )
    with pytest.raises(job_ingestion.JobEmptyError):
        job_ingestion.fetch_job(
            "https://example.com/jobs/8",
            transport=transport_responding(html.encode()),
        )


def test_page_metadata_wins_over_body():
    posting = job_ingestion.fetch_job(
        "https://jobs.acme.com/senior-backend",
        transport=transport_responding(SAMPLE_HTML.encode()),
    )
    # og:site_name is preferred over a hostname-derived company.
    assert posting.company == "Acme Corp"


class Target:
    from app.main import app


def test_api_fetch_job_success(monkeypatch):
    monkeypatch.setattr(
        job_ingestion,
        "fetch_job",
        lambda url: job_ingestion.JobPosting(
            title="Senior Backend Engineer",
            company="Acme Corp",
            description="Python, PostgreSQL and REST APIs role.",
            source_url="https://jobs.acme.com/senior-backend",
        ),
    )
    client = TestClient(Target.app, raise_server_exceptions=False)
    response = client.post(
        "/api/v1/jobs/fetch", json={"url": "https://jobs.acme.com/senior-backend"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Senior Backend Engineer"
    assert body["company"] == "Acme Corp"
    assert "Python" in body["description"]


@pytest.mark.parametrize(
    ("exception", "expected_status"),
    [
        (job_ingestion.JobUrlError("bad url"), 400),
        (job_ingestion.JobEmptyError("empty page"), 422),
        (job_ingestion.JobFetchTimeoutError("timeout"), 504),
        (job_ingestion.JobFetchStatusError("404"), 502),
        (job_ingestion.JobFetchError("network"), 502),
    ],
)
def test_api_fetch_job_maps_errors(monkeypatch, exception, expected_status):
    monkeypatch.setattr(job_ingestion, "fetch_job", lambda url: (_ for _ in ()).throw(exception))
    client = TestClient(Target.app, raise_server_exceptions=False)
    response = client.post("/api/v1/jobs/fetch", json={"url": "https://example.com/jobs/1"})
    assert response.status_code == expected_status


def test_api_fetch_job_rejects_malformed_requests():
    client = TestClient(Target.app, raise_server_exceptions=False)
    assert client.post("/api/v1/jobs/fetch", json={}).status_code == 422
    assert client.post("/api/v1/jobs/fetch", json={"url": "short"}).status_code == 422