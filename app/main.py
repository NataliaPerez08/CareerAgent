"""HTTP API for CareerAgent.

The core evaluation pipeline (app.service) is transport-agnostic: this
module only maps HTTP requests to service calls and service errors to
HTTP responses. Anything unexpected (model, network, runtime) is caught
by the global exception handler and returned as a 502.
"""

import logging

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.resume_parser import (
    ResumeParseError,
    ResumeTooLargeError,
    UnsupportedResumeFormatError,
    max_resume_size_bytes,
)
from app.schemas import EvaluationResult
from app.service import evaluate_candidate, evaluate_resume_file

logger = logging.getLogger(__name__)

API_V1 = "/api/v1"
MAX_TEXT_LENGTH = 100_000

app = FastAPI(
    title="CareerAgent API",
    version="0.5.0",
    description="Evaluate a resume against a job description using a Strands agent.",
)


class EvaluationRequest(BaseModel):
    """Stable v1 request contract for text evaluations."""

    resume_text: str = Field(min_length=20, max_length=MAX_TEXT_LENGTH)
    job_description: str = Field(min_length=20, max_length=MAX_TEXT_LENGTH)


RESUME_FILE = File(...)
JOB_DESCRIPTION_FORM = Form(min_length=20)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return 502 for any unexpected failure (model, network, runtime)."""
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
    return JSONResponse(status_code=502, content={"detail": "Agent execution failed."})


@app.get("/health", tags=["health"], summary="Liveness check")
def health() -> dict[str, str]:
    """Report service availability."""
    return {"status": "ok"}


@app.post(
    f"{API_V1}/evaluations",
    response_model=EvaluationResult,
    tags=["evaluations"],
    summary="Evaluate a resume against a job description",
)
def create_evaluation(request: EvaluationRequest) -> EvaluationResult:
    """Run the full evaluation pipeline on pasted text inputs."""
    logger.info(
        "Evaluation requested (resume: %d chars, job: %d chars)",
        len(request.resume_text),
        len(request.job_description),
    )
    return evaluate_candidate(request.resume_text, request.job_description)


@app.post(
    f"{API_V1}/evaluations/upload",
    response_model=EvaluationResult,
    tags=["evaluations"],
    summary="Evaluate an uploaded resume file against a job description",
)
async def create_evaluation_upload(
    resume: UploadFile = RESUME_FILE,
    job_description: str = JOB_DESCRIPTION_FORM,
) -> EvaluationResult:
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
        return evaluate_resume_file(data, filename, job_description)
    except ResumeTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsupportedResumeFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ResumeParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
