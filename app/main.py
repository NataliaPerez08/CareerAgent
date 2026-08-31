import logging

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
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

app = FastAPI(
    title="CareerAgent API",
    version="0.4.0",
    description="Evaluate a resume against a job description using a Strands agent.",
)


class EvaluationRequest(BaseModel):
    resume: str = Field(min_length=20)
    job_description: str = Field(min_length=20)


RESUME_FILE = File(...)
JOB_DESCRIPTION_FORM = Form(min_length=20)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluationResult)
def evaluate(request: EvaluationRequest) -> EvaluationResult:
    try:
        return evaluate_candidate(request.resume, request.job_description)
    except Exception as exc:
        logger.exception("Agent execution failed")
        raise HTTPException(
            status_code=502,
            detail="Agent execution failed.",
        ) from exc


@app.post("/evaluate/upload", response_model=EvaluationResult)
async def evaluate_upload(
    resume: UploadFile = RESUME_FILE,
    job_description: str = JOB_DESCRIPTION_FORM,
) -> EvaluationResult:
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
    except Exception as exc:
        logger.exception("Agent execution failed")
        raise HTTPException(
            status_code=502,
            detail="Agent execution failed.",
        ) from exc
