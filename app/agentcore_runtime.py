"""Amazon Bedrock AgentCore Runtime adapter for CareerAgent.

Layer separation (see docs/deploy/agentcore.md):

    domain/core (service, matching, policy, schemas, resume_parser)
                       ↑
        local FastAPI service (app.main)   |   AgentCore Runtime (this module)

The entrypoint exposes the same evaluation contract as `POST /api/v1`
without HTTP-framework or persistence concerns: JSON payload in,
`EvaluationResult` JSON out. The core pipeline is never modified for
deployment and stays fully testable locally.

Payload contract:

    {"resume_text": "...", "job_description": "..."}
    or
    {"resume_b64": "<base64 resume file>", "resume_filename": "cv.pdf",
     "job_description": "..."}

Run locally (protocol-compatible server, no AWS required):

    python -m app.agentcore_runtime
"""

import base64
import binascii
import logging

from bedrock_agentcore import BedrockAgentCoreApp

from app.resume_parser import max_resume_size_bytes, parse_resume
from app.service import evaluate_candidate

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH = 20
MAX_TEXT_LENGTH = 100_000

agentcore_app = BedrockAgentCoreApp()


def _validated_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not MIN_TEXT_LENGTH <= len(value) <= MAX_TEXT_LENGTH:
        raise ValueError(
            f"{field} must be a string of {MIN_TEXT_LENGTH} to {MAX_TEXT_LENGTH} characters."
        )
    return value


def _resume_text_from_payload(payload: dict) -> str:
    resume_text = payload.get("resume_text")
    resume_b64 = payload.get("resume_b64")

    if resume_text is not None and resume_b64 is not None:
        raise ValueError("Provide either resume_text or resume_b64, not both.")

    if resume_b64 is not None:
        if not isinstance(resume_b64, str) or not resume_b64:
            raise ValueError("resume_b64 must be a non-empty base64 string.")
        filename = payload.get("resume_filename", "resume")
        if not isinstance(filename, str) or not filename:
            raise ValueError("resume_filename must be a non-empty string.")
        try:
            data = base64.b64decode(resume_b64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("resume_b64 is not valid base64.") from exc
        if len(data) > max_resume_size_bytes():
            raise ValueError("Resume file exceeds the maximum allowed size.")
        return parse_resume(data, filename)

    return _validated_text(resume_text, "resume_text")


@agentcore_app.entrypoint
def evaluate(payload: dict) -> dict:
    """Evaluate a candidate against a job and return the structured result."""
    if not isinstance(payload, dict):
        raise ValueError("Payload must be a JSON object.")  # noqa: TRY004 - malformed input, not a type bug

    job_description = _validated_text(payload.get("job_description"), "job_description")
    resume_text = _resume_text_from_payload(payload)

    logger.info(
        "AgentCore invocation (resume: %d chars, job: %d chars)",
        len(resume_text),
        len(job_description),
    )
    result = evaluate_candidate(resume_text, job_description)
    logger.info(
        "AgentCore invocation complete (recommendation=%s, score=%d)",
        result.recommendation,
        result.score,
    )
    return result.model_dump()


if __name__ == "__main__":
    agentcore_app.run()
