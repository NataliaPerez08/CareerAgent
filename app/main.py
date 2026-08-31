import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.schemas import EvaluationResult
from app.service import evaluate_candidate

logger = logging.getLogger(__name__)

app = FastAPI(
    title="CareerAgent API",
    version="0.2.0",
    description="Evaluate a resume against a job description using a Strands agent.",
)


class EvaluationRequest(BaseModel):
    resume: str = Field(min_length=20)
    job_description: str = Field(min_length=20)


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
