"""Pydantic schemas for the structured evaluation contract."""

from typing import Literal

from pydantic import BaseModel, Field

Recommendation = Literal["APPLY", "MAYBE", "SKIP"]


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
    reasoning: str = ""
