import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import run_migrations
from app.models import Base, Candidate, Evaluation, Job, Resume
from app.repository import (
    get_evaluation,
    job_title,
    list_evaluations,
    save_evaluation,
    to_evaluation_result,
)
from app.schemas import EvaluationResult, SkillGap

RESUME = "Backend developer with 2 years of professional experience. Python, PostgreSQL."
JOB = "Junior Backend Engineer\n\nRequirements:\n- Python.\n- PostgreSQL."


def make_result(**overrides) -> EvaluationResult:
    defaults: dict = {
        "recommendation": "APPLY",
        "score": 85,
        "matched_skills": ["python", "postgresql"],
        "matched_preferred_skills": ["docker"],
        "missing_required_skills": ["aws"],
        "missing_preferred_skills": ["go"],
        "missing_critical_skills": [],
        "unknown_requirements": ["ci/cd"],
        "experience_match": True,
        "evidence": ["2 years of professional experience"],
        "strengths": ["Meets 2 of 2 required skills: python, postgresql"],
        "skill_gaps": [
            SkillGap(skill="aws", severity="required", preparation_steps=["IAM fundamentals", "S3"])
        ],
        "interview_topics": ["PostgreSQL indexes"],
        "preparation_plan": ["aws: IAM fundamentals"],
        "reasoning": "Strong overlap on the backend stack.",
    }
    defaults.update(overrides)
    return EvaluationResult(**defaults)


@pytest.fixture
def session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as session:
        yield session
    engine.dispose()


def test_save_creates_linked_entities(session):
    saved = save_evaluation(
        session,
        resume_text=RESUME,
        job_description=JOB,
        result=make_result(),
        filename="cv.pdf",
    )

    assert session.scalar(select(func.count()).select_from(Candidate)) == 1
    assert session.scalar(select(func.count()).select_from(Resume)) == 1
    assert session.scalar(select(func.count()).select_from(Job)) == 1
    assert session.scalar(select(func.count()).select_from(Evaluation)) == 1

    resume = session.get(Resume, saved.resume_id)
    assert resume.text == RESUME
    assert resume.filename == "cv.pdf"
    assert resume.candidate_id is not None

    job = session.get(Job, saved.job_id)
    assert job.title == "Junior Backend Engineer"
    assert job.description_text == JOB


def test_save_roundtrips_full_result(session):
    result = make_result()
    saved = save_evaluation(session, resume_text=RESUME, job_description=JOB, result=result)

    stored = get_evaluation(session, saved.id)
    assert stored is not None
    assert to_evaluation_result(stored) == result


def test_get_evaluation_missing_id_returns_none(session):
    save_evaluation(session, resume_text=RESUME, job_description=JOB, result=make_result())
    assert get_evaluation(session, 999) is None


def test_list_evaluations_newest_first_with_limit(session):
    first = save_evaluation(
        session, resume_text=RESUME, job_description=JOB, result=make_result(score=50)
    )
    second = save_evaluation(
        session, resume_text=RESUME, job_description=JOB, result=make_result(score=60)
    )
    third = save_evaluation(
        session, resume_text=RESUME, job_description=JOB, result=make_result(score=70)
    )

    listed = list_evaluations(session, limit=2)
    assert [evaluation.id for evaluation in listed] == [third.id, second.id]

    all_evaluations = list_evaluations(session, limit=100)
    assert [evaluation.id for evaluation in all_evaluations] == [third.id, second.id, first.id]


def test_save_each_evaluation_creates_own_candidate(session):
    save_evaluation(session, resume_text=RESUME, job_description=JOB, result=make_result())
    save_evaluation(session, resume_text=RESUME, job_description=JOB, result=make_result())

    assert session.scalar(select(func.count()).select_from(Candidate)) == 2
    assert session.scalar(select(func.count()).select_from(Evaluation)) == 2


def test_job_title_deterministic_heuristics():
    assert job_title("Junior Backend Engineer\n\nRequires Python.") == "Junior Backend Engineer"
    assert job_title("\n\n   \nSenior   Data   Engineer\nstuff") == "Senior Data Engineer"
    assert job_title("") == "Untitled job"
    assert job_title("x" * 300) == "x" * 120


def test_migrations_produce_working_schema(tmp_path):
    """The real Alembic migration must yield a schema the repository can use."""
    url = f"sqlite:///{tmp_path / 'migrated.db'}"
    run_migrations(url)

    engine = create_engine(url)
    with sessionmaker(bind=engine, expire_on_commit=False)() as migrated_session:
        result = make_result()
        saved = save_evaluation(
            migrated_session, resume_text=RESUME, job_description=JOB, result=result
        )
        stored = get_evaluation(migrated_session, saved.id)

        assert stored is not None
        assert to_evaluation_result(stored) == result
        assert stored.job.title == "Junior Backend Engineer"
    engine.dispose()
