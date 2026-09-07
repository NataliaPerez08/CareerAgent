"""Latency benchmark for CareerAgent (sprint Day 1).

Runs N evaluations of a fixed resume/job pair and produces a reproducible
latency baseline:

    python scripts/benchmark.py               # 5 real Bedrock runs
    python scripts/benchmark.py --count 10
    python scripts/benchmark.py --mock        # no LLM: deterministic pipeline only
    python scripts/benchmark.py --compare     # print delta vs previous baseline

Real mode requires AWS credentials (Bedrock invocations). Mock mode needs
nothing and is the reproducible "floor" (deterministic pipeline + I/O).

Every run records per-stage durations through app.timing.EvaluationTimings;
the report only contains metrics that were actually executed. Report and a
machine-readable baseline are written to dist/benchmark/.

NOTE: benchmarked latency is the in-process service pipeline. End-to-end
request latency through HTTP (request_total + persistence) is logged by the
API as structured JSON lines; remote AgentCore-invocation latency is logged
by the runtime the same way.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import service
from app.timing import EvaluationTimings

DEFAULT_REPORT = ROOT / "dist" / "benchmark" / "report.md"
DEFAULT_BASELINE = ROOT / "dist" / "benchmark" / "baseline.json"
DEFAULT_RESUME = ROOT / "examples" / "demo_resume.txt"
DEFAULT_JOB = ROOT / "examples" / "demo_job.txt"


class _FakeAgent:
    """Canned structured outputs for mock mode (mirrors tests/test_service.py).

    The pipeline makes exactly three single-shot structured calls, so an
    unstructured call would be a bug.
    """

    def __call__(self, prompt, structured_output_model=None):
        from app.schemas import CandidateProfile, CareerPlan, GapPreparation, JobRequirements

        if structured_output_model is CandidateProfile:
            return SimpleNamespace(
                structured_output=CandidateProfile(
                    skills=["Python", "PostgreSQL", "Docker"],
                    years_of_experience=2,
                    evidence=["2 years of professional backend development experience"],
                )
            )
        if structured_output_model is JobRequirements:
            return SimpleNamespace(
                structured_output=JobRequirements(
                    required_skills=["Python", "PostgreSQL", "Docker", "AWS"],
                    preferred_skills=["CI/CD"],
                    min_years_experience=1,
                )
            )
        if structured_output_model is CareerPlan:
            return SimpleNamespace(
                structured_output=CareerPlan(
                    interview_topics=["PostgreSQL indexes", "REST design", "AWS IAM"],
                    gap_preparation=[
                        GapPreparation(
                            skill="AWS",
                            preparation_steps=["IAM fundamentals", "S3", "Lambda"],
                        )
                    ],
                    reasoning="Mock explanation: deterministic pipeline completed without LLM.",
                )
            )
        raise AssertionError(f"unexpected unstructured model call: {structured_output_model!r}")


def _percentile(sorted_values: list[float], percent: float) -> float:
    if not sorted_values:
        return 0.0
    index = max(0, min(len(sorted_values) - 1, math.ceil(percent / 100.0 * len(sorted_values)) - 1))
    return sorted_values[index]


def _stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "min_ms": round(min(values), 2),
        "p50_ms": round(_percentile(ordered, 50), 2),
        "p95_ms": round(_percentile(ordered, 95), 2),
        "max_ms": round(max(values), 2),
        "mean_ms": round(sum(values) / len(values), 2),
        "runs": len(ordered),
    }


def run_one(resume: str, job: str, mock: bool) -> tuple[object, dict[str, float]]:
    """Run one evaluation and return (result, stage metrics + counters)."""
    original = service.build_pipeline_agent
    try:
        if mock:
            service.build_pipeline_agent = lambda: _FakeAgent()
        timings = EvaluationTimings()
        timings.start("request_total")
        result = service.evaluate_candidate(resume, job, timings=timings)
        timings.stop("request_total")
        return result, {**timings.aggregate_ms(), **timings.counters()}
    finally:
        service.build_pipeline_agent = original


def run_benchmark(
    resume: str,
    job: str,
    count: int,
    mock: bool,
    resume_source: str,
    job_source: str,
) -> tuple[list[dict], dict]:
    """Run count evaluations and aggregate per-stage percentiles."""
    per_run: list[dict] = []
    recommendations: dict[str, int] = {}
    for i in range(1, count + 1):
        started = time.perf_counter()
        result, metrics = run_one(resume, job, mock)
        wall_ms = round((time.perf_counter() - started) * 1000, 2)
        metrics["wall_ms"] = wall_ms
        per_run.append(metrics)
        recommendations[str(result.recommendation)] = (
            recommendations.get(str(result.recommendation), 0) + 1
        )
        print(f"  run {i}/{count}: total={metrics.get('request_total_ms')}ms "
              f"llm={metrics.get('llm_ms')}ms tools={metrics.get('tools_ms')}ms "
              f"calls={metrics.get('llm_calls')} cycles={metrics.get('llm_cycles')} "
              f"tool_calls={metrics.get('tool_calls')} "
              f"recommendation={result.recommendation} score={result.score}")

    durations = {k: v for k, v in per_run[0].items() if k.endswith("_ms")}
    counters = {k: v for k, v in per_run[0].items() if not k.endswith("_ms")}

    aggregated: dict[str, dict] = {}
    for key in durations:
        aggregated[key] = _stats([m[key] for m in per_run if key in m])
    aggregated_counters: dict[str, dict] = {}
    for key in counters:
        aggregated_counters[key] = _stats([float(m[key]) for m in per_run if key in m])

    summary = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "mode": "mock (no LLM)" if mock else "real (Amazon Bedrock)",
        "model": os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0"),
        "region": os.getenv("AWS_REGION", "us-east-1"),
        "resume_input": resume_source,
        "job_input": job_source,
        "count": count,
        "recommendations": recommendations,
        "wall_clock_p50_ms": round(_percentile(sorted(m["wall_ms"] for m in per_run), 50), 2),
        "wall_clock_p95_ms": round(_percentile(sorted(m["wall_ms"] for m in per_run), 95), 2),
        "metrics": {key: aggregated[key] for key in sorted(aggregated)},
        "counters": {key: aggregated_counters[key] for key in sorted(aggregated_counters)},
    }
    return per_run, summary


def build_report(summary: dict) -> str:
    lines: list[str] = []
    lines.append("CareerAgent Latency Benchmark")
    lines.append("==============================")
    lines.append("")
    lines.append(f"Generated: {summary['generated_at']}")
    lines.append(f"Mode: {summary['mode']}")
    lines.append(f"Model: {summary['model']} ({summary['region']})")
    lines.append(f"Runs: {summary['count']}")
    lines.append(f"Resume input: {summary['resume_input']}")
    lines.append(f"Job input: {summary['job_input']}")
    lines.append(f"Recommendations observed: {summary['recommendations']}")
    lines.append("")
    lines.append("Wall clock (benchmark harness, total per run):")
    lines.append("")
    lines.append(f"  p50: {summary['wall_clock_p50_ms']} ms   p95: {summary['wall_clock_p95_ms']} ms")
    lines.append("")
    lines.append("Per-stage latency (ms)")
    lines.append("-----------------------")
    lines.append(f"{'stage':<26}{'p50':>10}{'p95':>10}{'mean':>10}{'min':>10}{'max':>10}")
    for key, stats in summary["metrics"].items():
        if not stats:
            continue
        label = key.removesuffix("_ms")
        mark = "*" if key in ("llm_ms", "tools_ms") else " "
        lines.append(
            f"{label}{mark:<25}{stats['p50_ms']:>10}{stats['p95_ms']:>10}"
            f"{stats['mean_ms']:>10}{stats['min_ms']:>10}{stats['max_ms']:>10}"
        )
    lines.append("")
    lines.append("(*) llm = profile + requirements + plan_and_explanation;")
    lines.append("    tools = deterministic matching (normalize + match + policy + strengths/gaps).")
    lines.append("")
    counters = summary.get("counters") or {}
    if counters:
        lines.append("Agent-loop cost (per evaluation)")
        lines.append("-------------------------------")
        lines.append(f"{'counter':<26}{'p50':>10}{'min':>10}{'max':>10}")
        for key, stats in counters.items():
            if not stats:
                continue
            lines.append(
                f"{key:<26}{stats['p50_ms']:>10.0f}{stats['min_ms']:>10.0f}"
                f"{stats['max_ms']:>10.0f}"
            )
        lines.append("")
        lines.append("llm_calls = agent invocations; llm_cycles = model round-trips")
        lines.append("(a tool loop costs more than one cycle per call);")
        lines.append("tool_calls = tool executions triggered by the model.")
        lines.append("")
    lines.append("Only metrics actually executed are reported.")
    return "\n".join(lines) + "\n"


def compare_baseline(baseline_path: Path, latest: dict) -> str:
    if not baseline_path.exists():
        return "No previous baseline found — nothing to compare against.\n"
    previous = json.loads(baseline_path.read_text(encoding="utf-8"))
    lines = ["Baseline comparison (previous -> latest, ms):", ""]
    lines.append(f"{'metric':<26}{'prev p50':>10}{'now p50':>10}{'delta':>10}")
    for key in sorted(previous.get("metrics", {})):
        prev = previous["metrics"][key].get("p50_ms")
        now = latest["metrics"].get(key, {}).get("p50_ms")
        if prev is None or now is None:
            continue
        delta = round(now - prev, 2)
        lines.append(f"{key:<26}{prev:>10}{now:>10}{delta:>+10}")
    return "\n".join(lines) + "\n"


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Benchmark CareerAgent evaluation latency.")
    parser.add_argument("--count", type=int, default=5, help="evaluations to run (default: 5)")
    parser.add_argument(
        "--mock",
        action="store_true",
        help="use a canned agent (no LLM calls); measures the deterministic pipeline floor",
    )
    parser.add_argument(
        "--resume",
        type=Path,
        default=DEFAULT_RESUME,
        help="resume text file (default: examples/demo_resume.txt)",
    )
    parser.add_argument(
        "--job",
        type=Path,
        default=DEFAULT_JOB,
        help="job description text file (default: examples/demo_job.txt)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT,
        help="report path (default: dist/benchmark/report.md)",
    )
    parser.add_argument(
        "--baseline",
        type=Path,
        default=DEFAULT_BASELINE,
        help="baseline json path (default: dist/benchmark/baseline.json)",
    )
    parser.add_argument("--compare", action="store_true", help="print delta vs previous baseline")
    return parser


def aws_credentials_available() -> tuple[bool, str]:
    """Probe the AWS credential chain without leaking what it found."""
    try:
        import boto3

        session = boto3.Session(profile_name=os.getenv("AWS_PROFILE"))
        session.client("sts", region_name=os.getenv("AWS_REGION", "us-east-1")).get_caller_identity()
        return True, ""
    except Exception as exc:  # noqa: BLE001 - probe must report any credential-chain failure
        return False, f"{type(exc).__name__}: {exc}"


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    if args.count < 1:
        print("ERROR: --count must be >= 1", file=sys.stderr)
        return 1
    if not args.resume.exists() or not args.job.exists():
        print(f"ERROR: input files not found: {args.resume} / {args.job}", file=sys.stderr)
        return 1

    if not args.mock:
        available, reason = aws_credentials_available()
        if not available:
            print(
                f"ERROR: real mode needs AWS credentials (use --mock for the "
                f"pipeline-only baseline): {reason}",
                file=sys.stderr,
            )
            return 1

    resume = args.resume.read_text(encoding="utf-8")
    job = args.job.read_text(encoding="utf-8")

    print(f"Running {args.count} evaluation(s) — mode: {'mock' if args.mock else 'real'}")
    per_run, summary = run_benchmark(resume, job, args.count, args.mock, str(args.resume), str(args.job))

    report = build_report(summary)
    print()
    print(report, end="")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    payload = {
        "generated_at": summary["generated_at"],
        "mode": summary["mode"],
        "model": summary["model"],
        "region": summary["region"],
        "count": summary["count"],
        "recommendations": summary["recommendations"],
        "metrics": summary["metrics"],
        "counters": summary["counters"],
    }
    args.baseline.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Report written to {args.output}")
    print(f"Baseline written to {args.baseline}")

    if args.compare:
        print()
        print(compare_baseline(args.baseline, payload))

    if not args.mock and per_run and any(
        not m.get("profile_extraction_ms") for m in per_run
    ):
        print("WARN: unexpected missing per-stage data in real mode", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())