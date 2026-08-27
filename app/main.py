from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.service import evaluate_candidate


app = FastAPI(
    title="CareerAgent API",
    version="0.1.0",
    description="Evaluate a resume against a job description using a Strands agent.",
)


class EvaluationRequest(BaseModel):
    resume: str = Field(min_length=20)
    job_description: str = Field(min_length=20)


class EvaluationResponse(BaseModel):
    analysis: str


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/evaluate", response_model=EvaluationResponse)
def evaluate(request: EvaluationRequest) -> EvaluationResponse:
    try:
        analysis = evaluate_candidate(request.resume, request.job_description)
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Agent execution failed: {exc}",
        ) from exc

    return EvaluationResponse(analysis=analysis)
