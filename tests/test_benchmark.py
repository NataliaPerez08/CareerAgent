"""Regression tests for the latency benchmark tool (scripts/benchmark.py).

Runs in mock mode only: never invokes the LLM, so it is safe for
`make test`. It exercises the real CLI path so the reproducible-baseline
promise of sprint Day 1 is covered continuously.
"""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "scripts" / "benchmark.py"


def run_benchmark(tmp_path: Path, *extra: str) -> subprocess.CompletedProcess:
    output = tmp_path / "report.md"
    baseline = tmp_path / "baseline.json"
    return subprocess.run(
        [
            sys.executable,
            str(BENCHMARK),
            "--mock",
            "--count",
            "2",
            "--output",
            str(output),
            "--baseline",
            str(baseline),
            *extra,
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_benchmark_mock_writes_report_and_baseline(tmp_path):
    proc = run_benchmark(tmp_path)
    assert proc.returncode == 0, proc.stderr

    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "CareerAgent Latency Benchmark" in report
    assert "mock (no LLM)" in report
    assert "Only metrics actually executed are reported." in report

    baseline = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    assert baseline["count"] == 2
    assert baseline["mode"] == "mock (no LLM)"
    assert baseline["metrics"]["request_total_ms"]["runs"] == 2
    # Every stage the pipeline records is present in the baseline.
    for stage in (
        "request_total",
        "profile_extraction",
        "requirements_extraction",
        "deterministic_matching",
        "recommendation",
        "plan_and_explanation",
        "llm",
        "tools",
    ):
        assert f"{stage}_ms" in baseline["metrics"], f"missing metric: {stage}_ms"
    # The merged pipeline makes exactly three single-shot model calls.
    assert baseline["counters"]["llm_calls"]["max_ms"] == 3
    # Mock mode reports only what it can actually measure: the fake agent
    # exposes no Strands metrics, so tool/token counters are never fabricated.
    assert "tool_calls" not in baseline["counters"]
    assert "input_tokens" not in baseline["counters"]


def test_benchmark_rejects_bad_count(tmp_path):
    proc = run_benchmark(tmp_path, "--count", "0")
    assert proc.returncode == 1
    assert "--count must be >= 1" in proc.stderr


def test_benchmark_rejects_warm_path_in_mock(tmp_path):
    proc = run_benchmark(tmp_path, "--warm-path")
    assert proc.returncode == 1
    assert "use real mode" in proc.stderr


def _load_benchmark():
    import importlib.util

    spec = importlib.util.spec_from_file_location("careeragent_benchmark", BENCHMARK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _warm_summary(**overrides) -> dict:
    summary = {
        "generated_at": "2026-09-07T00:00:00+00:00",
        "mode": "real (Amazon Bedrock)",
        "model": "amazon.nova-micro-v1:0",
        "region": "us-east-1",
        "count": 4,
        "invocations_ms": [5000.0, 4900.0, 4800.0, 4700.0],
        "llm_cycles": [3, 3, 3, 3],
        "degraded_threshold_ms": 20000.0,
        "degraded_invocations": [],
        "healthy_invocations_ms": [5000.0, 4900.0, 4800.0, 4700.0],
        "first_ms": 5000.0,
        "later_p50_ms": 4800.0,
        "later_stats": {},
        "delta_first_to_later_p50_ms": -200.0,
        "healthy_first_ms": 5000.0,
        "healthy_later_p50_ms": 4800.0,
        "healthy_delta_ms": -200.0,
    }
    summary.update(overrides)
    return summary


def test_warm_path_report_says_no_significant_warm_up():
    bm = _load_benchmark()
    report = bm.build_warm_path_report(_warm_summary())
    assert "no significant" in report
    assert "500 ms" in report


def test_warm_path_report_flags_degraded_service_invocations():
    bm = _load_benchmark()
    report = bm.build_warm_path_report(
        _warm_summary(
            invocations_ms=[64549.0, 5979.24, 5589.95, 4174.72],
            degraded_invocations=[1],
            healthy_invocations_ms=[5979.24, 5589.95, 4174.72],
            healthy_first_ms=5979.24,
            healthy_later_p50_ms=4174.72,
            healthy_delta_ms=-1804.52,
        )
    )
    assert "degraded" in report
    assert "transient Bedrock service variance" in report