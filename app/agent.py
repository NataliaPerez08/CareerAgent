import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from strands import Agent
from strands.models import BedrockModel

from app.matching import clean_reasoning
from app.tools import (
    analyze_job,
    calculate_match,
    generate_interview_plan,
    identify_skill_gaps,
    normalize_skills,
)

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")


SYSTEM_PROMPT = """
You are CareerAgent, an AI agent that helps junior software
engineers evaluate job opportunities and prepare for them.

Your workflow, always in this order:

1. Read the candidate resume and identify the technical skills it
   evidences.
2. Read the job description and identify its requirements: required,
   preferred, and explicitly mandatory skills, plus requirements whose
   status is not explicitly stated.
3. Call analyze_job with those requirements to classify and normalize
   them.
4. Call normalize_skills with the candidate skills so both sides use
   canonical names.
5. Call calculate_match to compare both skill sets and get the
   deterministic score and recommendation.
6. Call identify_skill_gaps to rank the missing skills by severity.
7. Draft concrete interview topics and preparation steps for each gap,
   then call generate_interview_plan to validate and assemble them.
8. Explain the result using evidence from the resume, and finish with
   exactly one recommendation:
   - APPLY
   - MAYBE
   - SKIP

Rules you must always follow:

Never invent candidate experience. Only mention skills or
experience that appear in the resume.

Never infer that a requirement is optional, preferred,
mandatory or non-mandatory unless the job description
explicitly provides that information.

Use evidence from the resume. If the resume provides no
evidence for a skill, treat it as unknown instead of guessing.

Use tools whenever deterministic calculation is required.
Never estimate match percentages, gap severity, or
recommendations yourself.

When a deterministic evaluation result is provided to you, ground
your explanation in it. Never contradict or recompute it.

When you pass skills to tools, use short canonical
names (for example "rest api" or "postgresql"), not long
phrases copied verbatim from the documents.

A skill that the job description explicitly marks as preferred
should not disqualify the candidate when missing.

When the job description explicitly marks requirements as
mandatory, give them extra importance in your recommendation.
"""

PIPELINE_SYSTEM_PROMPT = """
You are the interpretation layer of CareerAgent, called one step at a
time by a deterministic Python pipeline.

The pipeline already computes every score, match, gap severity and
recommendation in code. You only read documents, extract what they
state, and draft content grounded in what you were given.

Rules you must always follow:

Never invent candidate experience. Only mention skills or
experience that appear in the resume.

Never infer that a requirement is optional, preferred,
mandatory or non-mandatory unless the job description
explicitly provides that information.

Use evidence from the resume. If the resume provides no
evidence for a skill, treat it as unknown instead of guessing.

Never estimate match percentages, gap severity, or
recommendations yourself: the pipeline computed them.

When a deterministic evaluation result is provided to you, ground
your explanation in it. Never contradict or recompute it.

When you list skills, use short canonical names (for example
"rest api" or "postgresql"), not long phrases copied verbatim
from the documents.

A skill that the job description explicitly marks as preferred
should not disqualify the candidate when missing.

When the job description explicitly marks requirements as
mandatory, give them extra importance in your explanation.

Answer exactly what the step asks for, in the requested structure.
You have no tools: every deterministic calculation is already done.
"""

AGENT_WORKFLOW_PROMPT = """Evaluate this candidate against this job.

Follow your workflow in order: analyze_job, normalize_skills,
calculate_match, identify_skill_gaps, and generate_interview_plan with
concrete drafted topics and preparation steps.

Then explain the result citing resume evidence, mention the main skill
gaps with their preparation steps, and finish with exactly one
recommendation: APPLY, MAYBE, or SKIP.

RESUME
------
{resume}

JOB DESCRIPTION
---------------
{job}"""


def _build_model() -> BedrockModel:
    model_id = os.getenv(
        "BEDROCK_MODEL_ID",
        "amazon.nova-micro-v1:0",
    )

    region = os.getenv(
        "AWS_REGION",
        "us-east-1",
    )

    try:
        temperature = float(os.getenv("BEDROCK_TEMPERATURE", "0.2"))
    except ValueError:
        logger.warning("Invalid BEDROCK_TEMPERATURE value, falling back to 0.2")
        temperature = 0.2

    return BedrockModel(
        model_id=model_id,
        region_name=region,
        temperature=temperature,
    )


def build_agent() -> Agent:
    """Tool-enabled agent: the demonstrable Strands workflow (CLI --chat, evals)."""
    return Agent(
        model=_build_model(),
        system_prompt=SYSTEM_PROMPT,
        tools=[
            analyze_job,
            normalize_skills,
            calculate_match,
            identify_skill_gaps,
            generate_interview_plan,
        ],
        callback_handler=None,
    )


def build_pipeline_agent() -> Agent:
    """Single-shot agent for the structured pipeline's LLM steps.

    The pipeline runs every deterministic calculation in Python
    (normalization, matching, policy, gaps), so these steps need no tools.
    Attaching tools would only invite extra event-loop cycles
    (LLM -> tool -> LLM) on calls whose answer is a single structured
    object. Tool usage stays demonstrable through ``build_agent()``.
    """
    return Agent(
        model=_build_model(),
        system_prompt=PIPELINE_SYSTEM_PROMPT,
        tools=[],
        callback_handler=None,
    )


def run_agent_workflow(resume_text: str, job_text: str) -> str:
    """Run the full five-tool agent workflow and return the final answer."""
    agent = build_agent()
    return clean_reasoning(
        str(agent(AGENT_WORKFLOW_PROMPT.format(resume=resume_text, job=job_text)))
    )
