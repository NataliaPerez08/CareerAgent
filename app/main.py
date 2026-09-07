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

import json
import logging
import queue
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import job_ingestion
from app.db import get_session, get_session_factory, run_migrations
from app.quick_rank import MAX_QUICK_JOBS, fetch_and_rank
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
from app.schemas import EvaluationResult, QuickRankingResult
from app.service import (
    evaluate_candidate,
    evaluate_resume_file,
    extract_candidate_profile,
)
from app.timing import EvaluationTimings

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


class JobFetchRequest(BaseModel):
    """Load a job posting from its URL instead of pasting text."""

    url: str = Field(min_length=8, max_length=2048)


class JobFetchResponse(BaseModel):
    """Structured content extracted from a job posting URL."""

    title: str = ""
    company: str = ""
    description: str
    source_url: str


class QuickRankingRequest(BaseModel):
    """Rank several job URLs against one resume (cheap, single model call)."""

    resume_text: str = Field(min_length=20, max_length=MAX_TEXT_LENGTH)
    job_urls: list[str] = Field(min_length=1, max_length=MAX_QUICK_JOBS)


RESUME_FILE = File(...)
JOB_DESCRIPTION_FORM = Form(min_length=20)
LIST_LIMIT = Query(default=20, ge=1, le=100)
SESSION = Depends(get_session)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Return 502 for any unexpected failure (model, network, runtime).

    Timeout-like failures (Bedrock deadlines, read timeouts) get 504 with a
    clear message so the UI can tell the user the model timed out instead of
    a generic failure.
    """
    if _is_model_timeout(exc):
        logger.warning("Model timeout while processing %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=504,
            content={"detail": "The AI model timed out. Please try again."},
        )
    logger.exception("Unhandled error while processing %s %s", request.method, request.url.path)
    return JSONResponse(status_code=502, content={"detail": "Agent execution failed."})


def _persist(
    session: Session,
    *,
    resume_text: str,
    job_description: str,
    result: EvaluationResult,
    filename: str | None = None,
    timings: EvaluationTimings | None = None,
) -> EvaluationResponse:
    """Best-effort persistence: log and degrade on storage failure."""
    timings = timings or EvaluationTimings()
    try:
        timings.start("persistence")
        saved = save_evaluation(
            session,
            resume_text=resume_text,
            job_description=job_description,
            result=result,
            filename=filename,
        )
        timings.stop("persistence")
    except Exception:
        timings.stop_if_started("persistence")
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
    f"{API_V1}/jobs/fetch",
    response_model=JobFetchResponse,
    tags=["jobs"],
    summary="Load a job posting from a URL",
)
def fetch_job_posting(request: JobFetchRequest) -> JobFetchResponse:
    """Fetch a job URL and return title, company and description.

    Best-effort extraction from public pages. On any failure a specific
    error is returned so the UI can fall back to manual paste.
    """
    try:
        posting = job_ingestion.fetch_job(request.url)
    except job_ingestion.JobUrlError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except job_ingestion.JobEmptyError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except job_ingestion.JobFetchTimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except job_ingestion.JobFetchStatusError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except job_ingestion.JobFetchError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return JobFetchResponse(
        title=posting.title,
        company=posting.company,
        description=posting.description,
        source_url=posting.source_url,
    )


@app.post(
    f"{API_V1}/batch/quick-ranking",
    response_model=QuickRankingResult,
    tags=["jobs"],
    summary="Quick-rank multiple job postings by URL",
)
def quick_rank_jobs(request: QuickRankingRequest) -> QuickRankingResult:
    """Rank job URLs against the candidate without a deep analysis.

    Costs exactly one model call (candidate profile extraction). Each job
    is ranked deterministically from the text fetched at its URL. Select
    one job afterwards for the deep evaluation via the evaluation
    endpoints. A failing URL becomes an error row, never a failed batch.
    """
    profile = extract_candidate_profile(request.resume_text)
    return fetch_and_rank(profile, request.job_urls)


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
    timings = EvaluationTimings()
    timings.start("request_total")
    result = evaluate_candidate(
        request.resume_text,
        request.job_description,
        timings=timings,
    )
    response = _persist(
        session,
        resume_text=request.resume_text,
        job_description=request.job_description,
        result=result,
        timings=timings,
    )
    timings.stop("request_total")
    timings.log(event="api_evaluation_timings", job_title=response.job_title)
    return response


def _is_model_timeout(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    message = str(exc).lower()
    return "timeout" in name or "timed out" in message or "deadline" in message


def _sse(event: str, data: object) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream_events(
    resume_text: str,
    job_description: str,
    *,
    filename: str | None = None,
):
    """Yield SSE events: one per pipeline stage, then ``result`` or ``error``.

    The pipeline runs in a worker thread so the synchronous service calls
    never block the event loop; the generator only drains a thread-safe
    queue. Progress reflects the real stages (no fake timers).
    """
    events: queue.Queue[dict | None] = queue.Queue()

    def queue_stage(stage: str) -> None:
        events.put({"type": "stage", "stage": stage})

    def run() -> None:
        timings = EvaluationTimings()
        timings.start("request_total")
        try:
            if filename is None:
                result = evaluate_candidate(
                    resume_text,
                    job_description,
                    timings=timings,
                    on_stage=queue_stage,
                )
            else:
                try:
                    result = evaluate_resume_file(
                        resume_text,
                        filename,
                        job_description,
                        timings=timings,
                        on_stage=queue_stage,
                    )
                except ResumeTooLargeError as exc:
                    events.put({"type": "error", "data": {"status_code": 413, "detail": str(exc)}})
                    return
                except UnsupportedResumeFormatError as exc:
                    events.put({"type": "error", "data": {"status_code": 415, "detail": str(exc)}})
                    return
                except ResumeParseError as exc:
                    events.put({"type": "error", "data": {"status_code": 422, "detail": str(exc)}})
                    return

            queue_stage("persistence")
            timings.start("persistence")
            try:
                with get_session_factory()() as session:
                    response = _persist(
                        session,
                        resume_text=resume_text,
                        job_description=job_description,
                        result=result,
                        filename=filename,
                        timings=timings,
                    )
            finally:
                timings.stop_if_started("persistence")
            timings.stop("request_total")
            timings.log(
                event="api_evaluation_stream_timings",
                job_title=response.job_title,
            )
            events.put({"type": "result", "data": response.model_dump(mode="json")})
        except HTTPException as exc:
            events.put({"type": "error", "data": {"status_code": exc.status_code, "detail": exc.detail}})
        except Exception as exc:
            if _is_model_timeout(exc):
                events.put(
                    {
                        "type": "error",
                        "data": {"status_code": 504, "detail": "The AI model timed out. Please try again."},
                    }
                )
            else:
                logger.exception("Streaming evaluation failed")
                events.put(
                    {
                        "type": "error",
                        "data": {"status_code": 502, "detail": "Agent execution failed. Please try again."},
                    }
                )
        finally:
            events.put(None)

    threading.Thread(target=run, daemon=True).start()
    while True:
        event = events.get()
        if event is None:
            break
        if event["type"] == "stage":
            yield _sse("stage", event["stage"])
        elif event["type"] == "result":
            yield _sse("result", event["data"])
        elif event["type"] == "error":
            yield _sse("error", event["data"])


@app.post(
    f"{API_V1}/evaluations/stream",
    tags=["evaluations"],
    summary="Evaluate a resume with live streaming progress (SSE)",
)
def create_evaluation_stream(request: EvaluationRequest) -> StreamingResponse:
    """Same pipeline as POST /evaluations, but the response is a
    text/event-stream: one ``stage`` event per pipeline step followed by a
    final ``result`` (or ``error``) event."""
    logger.info(
        "Evaluation stream requested (resume: %d chars, job: %d chars)",
        len(request.resume_text),
        len(request.job_description),
    )
    return StreamingResponse(
        _stream_events(request.resume_text, request.job_description),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post(
    f"{API_V1}/evaluations/upload/stream",
    tags=["evaluations"],
    summary="Evaluate an uploaded file with live streaming progress (SSE)",
)
async def create_evaluation_upload_stream(
    resume: UploadFile = RESUME_FILE,
    job_description: str = JOB_DESCRIPTION_FORM,
) -> StreamingResponse:
    """Stream variant of POST /evaluations/upload."""
    try:
        data = await resume.read(max_resume_size_bytes() + 1)
    except Exception as exc:
        logger.exception("Failed to read uploaded resume")
        raise HTTPException(
            status_code=400,
            detail="Could not read the uploaded resume file.",
        ) from exc
    filename = resume.filename or "resume"
    logger.info("Evaluation stream requested (upload: %s)", filename)
    return StreamingResponse(
        _stream_events(data, job_description, filename=filename),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
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
    timings = EvaluationTimings()
    timings.start("request_total")
    timings.start("resume_parse")
    try:
        resume_text = parse_resume(data, filename)
    except ResumeTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc
    except UnsupportedResumeFormatError as exc:
        raise HTTPException(status_code=415, detail=str(exc)) from exc
    except ResumeParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        timings.stop_if_started("resume_parse")

    result = evaluate_candidate(resume_text, job_description, timings=timings)
    response = _persist(
        session,
        resume_text=resume_text,
        job_description=job_description,
        result=result,
        filename=filename,
        timings=timings,
    )
    timings.stop("request_total")
    timings.log(event="api_evaluation_timings", job_title=response.job_title)
    return response


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
