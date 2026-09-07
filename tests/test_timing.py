import json
import logging
import time

from app.timing import EVALUATION_STAGES, EvaluationTimings


def test_records_stage_durations_in_ms():
    timings = EvaluationTimings()
    timings.start("resume_parse")
    time.sleep(0.01)
    timings.stop("resume_parse")

    ms = timings.as_ms()
    assert set(ms) == {"resume_parse_ms"}
    assert 5 <= ms["resume_parse_ms"] <= 100


def test_nested_spans_are_both_recorded():
    timings = EvaluationTimings()
    timings.start("deterministic_matching")
    timings.start("recommendation")
    time.sleep(0.005)
    timings.stop("recommendation")
    time.sleep(0.005)
    timings.stop("deterministic_matching")

    assert timings.get_ms("recommendation") <= timings.get_ms("deterministic_matching")
    assert timings.get_ms("deterministic_matching") > 0
    assert timings.get_ms("recommendation") > 0


def test_elapsed_measures_from_creation():
    timings = EvaluationTimings()
    time.sleep(0.01)
    assert timings.elapsed() >= 0.01


def test_aggregate_ms_computes_llm_and_tools():
    timings = EvaluationTimings()
    timings.start("profile_extraction")
    timings.stop("profile_extraction")
    timings.start("requirements_extraction")
    timings.stop("requirements_extraction")
    timings.start("plan_and_explanation")
    timings.stop("plan_and_explanation")
    timings.start("deterministic_matching")
    timings.stop("deterministic_matching")

    agg = timings.aggregate_ms()
    expected_llm = (
        agg["profile_extraction_ms"]
        + agg["requirements_extraction_ms"]
        + agg["plan_and_explanation_ms"]
    )
    assert agg["llm_ms"] == round(expected_llm, 2)
    assert agg["tools_ms"] == agg["deterministic_matching_ms"]


def test_counters_accumulate_model_and_tool_calls():
    timings = EvaluationTimings()
    timings.count("llm_calls")
    timings.count("llm_calls")
    timings.count("tool_calls", 3)
    timings.count("input_tokens", 1200)

    counters = timings.counters()
    assert counters == {
        "input_tokens": 1200,
        "llm_calls": 2,
        "tool_calls": 3,
    }


def test_log_includes_counters_alongside_durations(caplog):
    timings = EvaluationTimings()
    timings.start("profile_extraction")
    timings.stop("profile_extraction")
    timings.count("llm_calls")
    timings.count("llm_cycles")
    timings.count("tool_calls", 0)

    with caplog.at_level(logging.INFO, logger="app.timing"):
        timings.log(event="evaluation_pipeline_timings")

    payload = json.loads(caplog.records[-1].getMessage())
    assert payload["llm_calls"] == 1
    assert payload["llm_cycles"] == 1
    assert payload["tool_calls"] == 0
    assert payload["profile_extraction_ms"] >= 0


def test_start_twice_raises_and_stop_unstarted_raises():
    timings = EvaluationTimings()
    timings.start("persistence")
    try:
        timings.start("persistence")
    except ValueError as exc:
        assert "already recorded" in str(exc)
    else:
        raise AssertionError("expected double-start to raise")

    try:
        timings.stop("not_started")
    except ValueError as exc:
        assert "not started" in str(exc)
    else:
        raise AssertionError("expected stopping an unknown stage to raise")


def test_stop_if_started_is_a_safe_noop():
    timings = EvaluationTimings()
    timings.stop_if_started("persistence")  # never started: no-op
    timings.start("persistence")
    timings.stop_if_started("persistence")
    assert "persistence_ms" in timings.as_ms()


def test_log_emits_structured_json_without_content(caplog):
    timings = EvaluationTimings()
    timings.start("profile_extraction")
    timings.stop("profile_extraction")

    with caplog.at_level(logging.INFO, logger="app.timing"):
        timings.log(event="evaluation_pipeline_timings", recommendation="APPLY")

    payload = json.loads(caplog.records[-1].getMessage())
    assert payload["event"] == "evaluation_pipeline_timings"
    assert payload["profile_extraction_ms"] >= 0
    assert payload["llm_ms"] >= 0
    assert payload["tools_ms"] == 0.0
    assert payload["recommendation"] == "APPLY"
    # No resume/job content is ever logged; only durations and tiny metadata.
    assert set(payload) - {"event", "profile_extraction_ms", "llm_ms", "tools_ms", "recommendation"} == set()


def test_canonical_stages_are_defined():
    # The benchmark contract: these stage names are shared across layers.
    for stage in ("request_total", "resume_parse", "profile_extraction",
                  "requirements_extraction", "deterministic_matching",
                  "recommendation", "plan_and_explanation",
                  "persistence", "agentcore_overhead"):
        assert stage in EVALUATION_STAGES