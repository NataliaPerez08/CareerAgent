"""SQLAlchemy models for evaluation history.

Portable column types only (Integer, String, Text, Boolean, DateTime,
JSON) so the same models and migrations run on SQLite (local dev and
tests) and PostgreSQL (docker compose / production).
"""

from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Candidate(Base):
    """A person being evaluated. One candidate is created per evaluation."""

    __tablename__ = "candidates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    resumes: Mapped[list["Resume"]] = relationship(back_populates="candidate")


class Resume(Base):
    """The resume text a candidate was evaluated with."""

    __tablename__ = "resumes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    candidate_id: Mapped[int] = mapped_column(ForeignKey("candidates.id"))
    filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    candidate: Mapped[Candidate] = relationship(back_populates="resumes")
    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="resume")


class Job(Base):
    """A job description an evaluation ran against."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    evaluations: Mapped[list["Evaluation"]] = relationship(back_populates="job")


class Evaluation(Base):
    """A persisted evaluation result.

    Stores the structured outcome (score, recommendation, skill lists,
    evidence, gaps) and the metadata needed to recover it later. Internal
    prompts are never stored.
    """

    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    resume_id: Mapped[int] = mapped_column(ForeignKey("resumes.id"))
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"))
    recommendation: Mapped[str] = mapped_column(String(16))
    score: Mapped[int] = mapped_column(Integer)
    matched_skills: Mapped[list] = mapped_column(JSON, default=list)
    matched_preferred_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_required_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_preferred_skills: Mapped[list] = mapped_column(JSON, default=list)
    missing_critical_skills: Mapped[list] = mapped_column(JSON, default=list)
    unknown_requirements: Mapped[list] = mapped_column(JSON, default=list)
    experience_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    strengths: Mapped[list] = mapped_column(JSON, default=list)
    skill_gaps: Mapped[list] = mapped_column(JSON, default=list)
    interview_topics: Mapped[list] = mapped_column(JSON, default=list)
    preparation_plan: Mapped[list] = mapped_column(JSON, default=list)
    reasoning: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    resume: Mapped[Resume] = relationship(back_populates="evaluations")
    job: Mapped[Job] = relationship(back_populates="evaluations")
