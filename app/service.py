from functools import lru_cache

from app.agent import build_agent


@lru_cache(maxsize=1)
def get_agent():
    return build_agent()


def evaluate_candidate(resume: str, job_description: str) -> str:
    prompt = f"""
Evaluate this candidate for the job below.

RESUME
------
{resume}

JOB DESCRIPTION
---------------
{job_description}

Use your tools where appropriate and finish with one recommendation:
APPLY, MAYBE, or SKIP.
""".strip()

    result = get_agent()(prompt)
    return str(result)
