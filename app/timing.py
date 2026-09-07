"""Latency instrumentation for evaluation pipelines.

Day 1 of the 11-day sprint: know exactly where an evaluation spends its
time before optimizing anything. Only durations and tiny metadata are ever
recorded; resume text, job text, prompts and model outputs are never
included in the logs.

Stage names are shared across layers (service, HTTP, AgentCore, benchmark):

    request_total           one full evaluation request, end to end
    resume_parse            PDF/TXT -> plain text
    profile_extraction      LLM extraction of the candidate profile
    requirements_extraction LLM extraction of the job requirements
    deterministic_matching  normalization + matching + strengths/gaps (code)
    recommendation          deterministic recommendation policy (code)
    plan_and_explanation    LLM draft of interview topics, preparation steps
                            and the grounded explanation (one model call)
    persistence             storing the evaluation in the database
    agentcore_overhead      AgentCore runtime / transport overhead

Aggregates computed for every logged evaluation:

    llm_ms    profile_extraction + requirements_extraction + plan_and_explanation
    tools_ms  deterministic_matching

Counters (not durations) make the agent-loop cost explicit:

    llm_calls      agent invocations made by the pipeline
    llm_cycles     model round-trips (an agent loop with tool calls needs >1)
    tool_calls     tool executions triggered by the model
    input_tokens   accumulated prompt tokens
    output_tokens  accumulated generated tokens
"""

from __future__ import annotations

import json
import logging
import time

logger = logging.getLogger(__name__)

LLM_STAGES = (
    "profile_extraction",
    "requirements_extraction",
    "plan_and_explanation",
)

# Canonical stage names so every layer and the benchmark tool agree.
EVALUATION_STAGES = (
    "request_total",
    "resume_parse",
    *LLM_STAGES,
    "deterministic_matching",
    "recommendation",
    "persistence",
    "agentcore_overhead",
)

# Counters (not durations) recorded per evaluation. They make the agent-loop
# cost visible: how many model round-trips and tool calls one evaluation needs.
COUNTER_NAMES = (
    "llm_calls",
    "llm_cycles",
    "tool_calls",
    "input_tokens",
    "output_tokens",
)


def _ms(seconds: float) -> float:
    return round(seconds * 1000.0, 2)


class EvaluationTimings:
    """Collects per-stage durations for a single evaluation.

    Stages may overlap (spans): each stage accumulates wall time between
    ``start``/``stop``. One collector can be threaded through the whole
    stack (HTTP -> service -> repository) so a single structured JSON line
    captures the complete latency breakdown of one evaluation.
    """

    def __init__(self) -> None:
        self._durations: dict[str, float] = {}
        self._started: dict[str, float] = {}
        self._counters: dict[str, int] = {}
        self._ref = time.perf_counter()

    def start(self, name: str) -> None:
        if name in self._started or name in self._durations:
            raise ValueError(f"stage already recorded: {name}")
        self._started[name] = time.perf_counter()

    def stop(self, name: str) -> None:
        started = self._started.pop(name, None)
        if started is None:
            raise ValueError(f"stage not started: {name}")
        self._durations[name] = self._durations.get(name, 0.0) + (
            time.perf_counter() - started
        )

    def stop_if_started(self, name: str) -> None:
        """Stop a stage only if it is currently running (no-op otherwise)."""
        if name in self._started:
            self.stop(name)

    def elapsed(self) -> float:
        """Seconds since the collector was created (for request_total)."""
        return time.perf_counter() - self._ref

    def get_ms(self, name: str) -> float:
        return _ms(self._durations.get(name, 0.0))

    def count(self, name: str, amount: int = 1) -> None:
        """Accumulate a counter (model calls, tool calls, tokens)."""
        self._counters[name] = self._counters.get(name, 0) + amount

    def counters(self) -> dict[str, int]:
        return dict(sorted(self._counters.items()))

    def as_seconds(self) -> dict[str, float]:
        return dict(sorted(self._durations.items()))

    def as_ms(self) -> dict[str, float]:
        return {f"{name}_ms": _ms(seconds) for name, seconds in self.as_seconds().items()}

    def aggregate_ms(self) -> dict[str, float]:
        """Recorded stages plus the derived llm_ms / tools_ms aggregates."""
        ms = self.as_ms()
        llm = sum(ms.get(f"{stage}_ms", 0.0) for stage in LLM_STAGES)
        return {
            **ms,
            "llm_ms": round(llm, 2),
            "tools_ms": ms.get("deterministic_matching_ms", 0.0),
        }

    def log(self, *, event: str = "evaluation_timings", **extra: object) -> None:
        """Emit exactly one structured JSON line: durations and counters only."""
        payload: dict[str, object] = {
            "event": event,
            **self.aggregate_ms(),
            **self.counters(),
        }
        if extra:
            payload.update(extra)
        logger.info(json.dumps(payload, sort_keys=True))