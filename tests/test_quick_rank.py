"""Deterministic quick-ranking tests (sprint Day 8).

No LLM involved: ranking is pure code, so these tests are fast and part
of `make test`. They cover ranking order, alias-aware matching, per-job
error rows, and the shared recommendation policy.
"""

from app import job_ingestion
from app.quick_rank import fetch_and_rank, rank_jobs
from app.schemas import CandidateProfile


def _profile(*skills: str) -> CandidateProfile:
    return CandidateProfile(skills=list(skills), years_of_experience=3, evidence=[])


def _job(url: str, description: str, title: str = "Job", company: str = "") -> dict:
    return {"url": url, "title": title, "company": company, "description": description}


def test_ranking_orders_by_matched_skill_share():
    profile = _profile("python", "postgresql", "docker", "kubernetes")
    jobs = [
        _job("https://a.example/1", "We need python and postgresql.", title="Python job"),
        _job("https://a.example/2", "We need python.", title="Python only"),
        _job("https://a.example/3", "Nothing relevant here.", title="Irrelevant"),
    ]
    result = rank_jobs(profile, jobs)
    assert [row.url for row in result.jobs] == [
        "https://a.example/1",
        "https://a.example/2",
        "https://a.example/3",
    ]
    assert result.jobs[0].score == 50
    assert result.jobs[0].matched_skills == ["postgresql", "python"]
    assert result.jobs[2].score == 0
    assert result.jobs[2].recommendation == "SKIP"


def test_ranking_is_alias_and_case_aware():
    profile = _profile("postgresql", "rest api")
    jobs = [
        _job("https://a.example/r", "Experience with Postgres and REST APIs."),
        _job("https://a.example/b", "We use PostgreSQL."),
    ]
    result = rank_jobs(profile, jobs)
    # "Postgres" and "REST APIs" both map onto the candidate skills
    # ("postgres" is an alias of "postgresql"; "rest apis" of "rest api").
    assert result.jobs[0].score == 100
    assert result.jobs[0].matched_skills == ["postgresql", "rest api"]
    # Job b only mentions the database; "PostgreSQL" single word also
    # matches the "postgresql" skill (plain word match, case-insensitive).
    assert result.jobs[1].score == 50
    assert result.jobs[1].matched_skills == ["postgresql"]


def test_word_boundary_prevents_partial_token_matches():
    profile = _profile("go", "aws")
    # "goto" must NOT match skill "go"; standalone "go" and "aws" must.
    jobs = [_job("https://a.example/g", "You will goto the office. Go fast. Certify in aws.")]
    result = rank_jobs(profile, jobs)
    assert result.jobs[0].score == 100
    assert result.jobs[0].matched_skills == ["aws", "go"]


def test_ranking_with_errors_keeps_batch_and_sinks_error_rows():
    profile = _profile("python")
    jobs = [
        _job("https://a.example/good", "We need python.", title="Good"),
        {"url": "https://a.example/bad", "error": "blocked"},
    ]
    result = rank_jobs(profile, jobs)
    assert len(result.jobs) == 2
    assert result.jobs[0].title == "Good"
    assert result.jobs[0].error is None
    assert result.jobs[1].error == "blocked"
    assert result.jobs[1].score == 0


def test_recommendation_uses_shared_policy_thresholds():
    profile = _profile(*[f"skill{i}" for i in range(10)])
    result = rank_jobs(
        profile,
        [_job("https://a.example/full", " ".join(profile.skills)), _job("https://a.example/half", "skill0")],
    )
    by_score = {row.score: row for row in result.jobs}
    assert by_score[100].recommendation == "APPLY"
    assert by_score[10].recommendation == "SKIP"


def test_empty_candidate_skills_never_divides_by_zero():
    result = rank_jobs(_profile(), [_job("https://a.example/x", "python")])
    assert result.jobs[0].score == 0
    assert result.jobs[0].recommendation == "SKIP"


def test_fetch_and_rank_resolves_fetch_at_call_time(monkeypatch):
    def fake_fetch(url):
        return job_ingestion.JobPosting(
            title="Fake", company="Corp", description="We need python.", source_url=url
        )

    monkeypatch.setattr(job_ingestion, "fetch_job", fake_fetch)
    result = fetch_and_rank(_profile("python"), ["https://a.example/1"])
    assert result.jobs[0].score == 100


def test_fetch_and_rank_turns_fetch_failure_into_error_row(monkeypatch):
    def fake_fetch(url):
        raise job_ingestion.JobFetchTimeoutError("did not respond")

    monkeypatch.setattr(job_ingestion, "fetch_job", fake_fetch)
    result = fetch_and_rank(_profile("python"), ["https://a.example/1"])
    assert result.jobs[0].error == "did not respond"