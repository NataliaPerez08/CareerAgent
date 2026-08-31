"""Repository layer: persistence of evaluations and their inputs.

The evaluation pipeline (app.service) stays LLM-only; this module owns
how results map to Candidate / Resume / Job / Evaluation rows and how
they are recovered. Nothing here talks to an LLM or to HTTP.
"""

import re

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Candidate, Evaluation, Job, Resume
from app.schemas import EvaluationResult, SkillGap

MAX_JOB_TITLE_LENGTH = 120


def job_title(job_description: str) -> str:
    """Deterministic human label for a job: its first non-empty line."""
    for line in job_description.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            return cleaned[:MAX_JOB_TITLE_LENGTH]
    return "Untitled job"


def save_evaluation(
    session: Session,
    *,
    resume_text: str,
    job_description: str,
    result: EvaluationResult,
    filename: str | None = None,
) -> Evaluation:
    """Persist one evaluation with its candidate, resume and job."""
    candidate = Candidate()
    session.add(candidate)
    session.flush()

    resume = Resume(candidate_id=candidate.id, filename=filename, text=resume_text)
    job = Job(title=job_title(job_description), description_text=job_description)
    session.add_all([resume, job])
    session.flush()

    evaluation = Evaluation(
        resume_id=resume.id,
        job_id=job.id,
        recommendation=result.recommendation,
        score=result.score,
        matched_skills=result.matched_skills,
        matched_preferred_skills=result.matched_preferred_skills,
        missing_required_skills=result.missing_required_skills,
        missing_preferred_skills=result.missing_preferred_skills,
        missing_critical_skills=result.missing_critical_skills,
        unknown_requirements=result.unknown_requirements,
        experience_match=result.experience_match,
        evidence=result.evidence,
        strengths=result.strengths,
        skill_gaps=[gap.model_dump() for gap in result.skill_gaps],
        interview_topics=result.interview_topics,
        preparation_plan=result.preparation_plan,
        reasoning=result.reasoning,
    )
    session.add(evaluation)
    session.commit()
    return evaluation


def get_evaluation(session: Session, evaluation_id: int) -> Evaluation | None:
    statement = (
        select(Evaluation)
        .where(Evaluation.id == evaluation_id)
        .options(selectinload(Evaluation.job), selectinload(Evaluation.resume))
    )
    return session.scalar(statement)


def list_evaluations(session: Session, limit: int) -> list[Evaluation]:
    statement = (
        select(Evaluation)
        .order_by(Evaluation.id.desc())
        .limit(limit)
        .options(selectinload(Evaluation.job))
    )
    return list(session.scalars(statement))


def to_evaluation_result(evaluation: Evaluation) -> EvaluationResult:
    """Rebuild the domain result from a stored evaluation."""
    return EvaluationResult(
        recommendation=evaluation.recommendation,
        score=evaluation.score,
        matched_skills=evaluation.matched_skills,
        matched_preferred_skills=evaluation.matched_preferred_skills,
        missing_required_skills=evaluation.missing_required_skills,
        missing_preferred_skills=evaluation.missing_preferred_skills,
        missing_critical_skills=evaluation.missing_critical_skills,
        unknown_requirements=evaluation.unknown_requirements,
        experience_match=evaluation.experience_match,
        evidence=evaluation.evidence,
        strengths=evaluation.strengths,
        skill_gaps=[SkillGap(**gap) for gap in evaluation.skill_gaps],
        interview_topics=evaluation.interview_topics,
        preparation_plan=evaluation.preparation_plan,
        reasoning=evaluation.reasoning,
    )
