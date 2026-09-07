"""Pydantic schemas for the structured evaluation contract."""

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field

Recommendation = Literal["APPLY", "MAYBE", "SKIP"]
SkillSeverity = Literal["critical", "required", "preferred"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class CandidateProfile(BaseModel):
    """Technical profile extracted from a candidate resume."""

    skills: list[str] = Field(default_factory=list)
    years_of_experience: int | None = None
    evidence: list[str] = Field(default_factory=list)


class JobRequirements(BaseModel):
    """Requirements extracted from a job description."""

    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    critical_skills: list[str] = Field(default_factory=list)
    unknown_requirements: list[str] = Field(default_factory=list)
    min_years_experience: int | None = None


class MatchResult(BaseModel):
    """Deterministic match between a candidate profile and job requirements."""

    score: int = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    matched_preferred_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    missing_preferred_skills: list[str] = Field(default_factory=list)
    missing_critical_skills: list[str] = Field(default_factory=list)
    experience_match: bool | None = None


class SkillGap(BaseModel):
    """A missing skill ranked by severity, with validated preparation steps."""

    skill: str
    severity: SkillSeverity
    preparation_steps: list[str] = Field(default_factory=list)


class GapPreparation(BaseModel):
    """LLM-drafted preparation for a missing skill.

    Severity is never taken from the LLM: only the preparation content
    is used, and only for skills that are actually missing.
    """

    skill: str
    preparation_steps: list[str] = Field(default_factory=list)


class CareerPlan(BaseModel):
    """LLM-drafted career intelligence content, validated by code before use.

    Produced by a single model call that also drafts ``reasoning``; the
    explanation is cleaned and kept only if it is grounded in the
    deterministic result, and the gap content is filtered against the
    skills that are actually missing.
    """

    interview_topics: list[str] = Field(default_factory=list)
    gap_preparation: list[GapPreparation] = Field(default_factory=list)
    reasoning: str = ""


class EvaluationResult(BaseModel):
    """Final structured evaluation of a candidate against a job."""

    recommendation: Recommendation
    score: int = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    matched_preferred_skills: list[str] = Field(default_factory=list)
    missing_required_skills: list[str] = Field(default_factory=list)
    missing_preferred_skills: list[str] = Field(default_factory=list)
    missing_critical_skills: list[str] = Field(default_factory=list)
    unknown_requirements: list[str] = Field(default_factory=list)
    experience_match: bool | None = None
    evidence: list[str] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    skill_gaps: list[SkillGap] = Field(default_factory=list)
    interview_topics: list[str] = Field(default_factory=list)
    preparation_plan: list[str] = Field(default_factory=list)
    reasoning: str = ""


class QuickRankingJob(BaseModel):
    """One shallow-ranked job posting from the batch endpoint."""

    url: str
    title: str = ""
    company: str = ""
    score: int = Field(default=0, ge=0, le=100)
    recommendation: Recommendation = "SKIP"
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    error: str | None = None


class QuickRankingResult(BaseModel):
    """Cheap ranking of several jobs against one candidate profile."""

    candidate_skills: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=_utcnow)
    jobs: list[QuickRankingJob] = Field(default_factory=list)
    note: str = ""
