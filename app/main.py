"""HTTP API for CareerAgent.

The core evaluation pipeline (app.service) is transport-agnostic: this
module only maps HTTP requests to service calls, persists results through
the repository layer, and maps errors to HTTP responses. Anything
unexpected (model, network, runtime) is caught by the global exception
handler and returned as a 502.

Persistence is best-effort per request: if storing an evaluation fails
after the (expensive) agent run succeeded, the result is still returned
without an id and the failure is logged.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_session, run_migrations
from app.repository import (
    get_evaluation,
    list_evaluations,
    save_evaluation,
    to_evaluation_result,
)
from app.resume_parser import (
    ResumeParseError,
    ResumeTooLargeError,
    UnsupportedResumeFormatError,
    max_resume_size_bytes,
    parse_resume,
)
from app.schemas import EvaluationResult
from app.service import evaluate_candidate

logger = logging.getLogger(__name__)

API_V1 = "/api/v1"
MAX_TEXT_LENGTH = 100_000
STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    run_migrations()
    yield


app = FastAPI(
    title="CareerAgent API",
    version="1.0.0",
    description="Evaluate a resume against a job description using a Strands agent.",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


class EvaluationRequest(BaseModel):
    """Stable v1 request contract for text evaluations."""

    resume_text: str = Field(min_length=20, max_length=MAX_TEXT_LENGTH)
    job_description: str = Field(min_length=20, max_length=MAX_TEXT_LENGTH)


class EvaluationResponse(EvaluationResult):
    """EvaluationResult plus the metadata gained from persistence."""

    id: int | None = None
    created_at: datetime | None = None
    job_title: str | None = None


class EvaluationSummary(BaseModel):
    id: int
    created_at: datetime
    job_title: str
    score: int
    recommendation: str


RESUME_FILE = File(...)
JOB_DESCRIPTION_FORM = Form(min_length=20)
LIST_LIMIT = Query(default=20, ge=1, le=100)
SESSION = Depends(get_session)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return 502 for any unexpected failure (model, network, runtime)."""
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
    return JSONResponse(status_code=502, content={"detail": "Agent execution failed."})


def _persist(
    session: Session,
    *,
    resume_text: str,
    job_description: str,
    result: EvaluationResult,
    filename: str | None = None,
) -> EvaluationResponse:
    """Best-effort persistence: log and degrade on storage failure."""
    try:
        saved = save_evaluation(
            session,
            resume_text=resume_text,
            job_description=job_description,
            result=result,
            filename=filename,
        )
    except Exception:
        logger.exception("Failed to persist evaluation")
        session.rollback()
        return EvaluationResponse(**result.model_dump())

    return EvaluationResponse(
        id=saved.id,
        created_at=saved.created_at,
        job_title=saved.job.title,
        **result.model_dump(),
    )


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """Serve the CareerAgent web UI."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["health"], summary="Liveness check")
def health() -> dict[str, str]:
    """Report service availability."""
    return {"status": "ok"}


@app.post(
    f"{API_V1}/evaluations",
    response_model=EvaluationResponse,
    tags=["evaluations"],
    summary="Evaluate a resume against a job description",
)
def create_evaluation(
    request: EvaluationRequest,
    session: Session = SESSION,
) -> EvaluationResponse:
    """Run the full evaluation pipeline on pasted text inputs."""
    logger.info(
        "Evaluation requested (resume: %d chars, job: %d chars)",
        len(request.resume_text),
        len(request.job_description),
    )
    result = evaluate_candidate(request.resume_text, request.job_description)
    return _persist(
        session,
        resume_text=request.resume_text,
        job_description=request.job_description,
        result=result,
    )


@app.post(
    f"{API_V1}/evaluations/upload",
    response_model=EvaluationResponse,
    tags=["evaluations"],
    summary="Evaluate an uploaded resume file against a job description",
)
async def create_evaluation_upload(
    resume: UploadFile = RESUME_FILE,
    job_description: str = JOB_DESCRIPTION_FORM,
    session: Session = SESSION,
) -> EvaluationResponse:
    """Parse an uploaded resume (PDF/TXT) and evaluate it against the job."""
    try:
        data = await resume.read(max_resume_size_bytes() + 1)
    except Exception as exc:
        logger.exception("Failed to read uploaded resume")
        raise HTTPException(
            status_code=400,
            detail="Could not read the uploaded resume file.",
        ) from exc

    filename = resume.filename or "resume"
    try:
        resume_text = parse_resume(data, filename)
    except ResumeTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsupportedResumeFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ResumeParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    result = evaluate_candidate(resume_text, job_description)
    return _persist(
        session,
        resume_text=resume_text,
        job_description=job_description,
        result=result,
        filename=filename,
    )


@app.get(
    f"{API_V1}/evaluations",
    response_model=list[EvaluationSummary],
    tags=["evaluations"],
    summary="List recent evaluations",
)
def get_evaluations(
    limit: int = LIST_LIMIT,
    session: Session = SESSION,
) -> list[EvaluationSummary]:
    """Return the most recent evaluations, newest first."""
    return [
        EvaluationSummary(
            id=evaluation.id,
            created_at=evaluation.created_at,
            job_title=evaluation.job.title,
            score=evaluation.score,
            recommendation=evaluation.recommendation,
        )
        for evaluation in list_evaluations(session, limit)
    ]


@app.get(
    f"{API_V1}/evaluations/{{evaluation_id}}",
    response_model=EvaluationResponse,
    tags=["evaluations"],
    summary="Get a stored evaluation",
)
def get_evaluation_by_id(
    evaluation_id: int,
    session: Session = SESSION,
) -> EvaluationResponse:
    """Recover a previously stored evaluation by id."""
    stored = get_evaluation(session, evaluation_id)
    if stored is None:
        raise HTTPException(status_code=404, detail="Evaluation not found.")
    return EvaluationResponse(
        id=stored.id,
        created_at=stored.created_at,
        job_title=stored.job.title,
        **to_evaluation_result(stored).model_dump(),
    )
