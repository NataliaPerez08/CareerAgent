import pytest

from app.matching import validate_evidence
from tests.evals.runner import (
    CATEGORIES,
    build_report,
    check_case_deterministic,
    create_parser,
    load_cases,
    run_deterministic,
)

CASES = load_cases()
CASE_IDS = [case["case_id"] for case in CASES]


def test_dataset_covers_all_categories_with_25_cases():
    assert len(CASES) == 25
    assert {case["category"] for case in CASES} == set(CATEGORIES)
    per_category: dict[str, int] = {}
    for case in CASES:
        per_category[case["category"]] = per_category.get(case["category"], 0) + 1
    assert all(count >= 3 for count in per_category.values())


def test_case_ids_are_unique():
    assert len(CASE_IDS) == len(set(CASE_IDS))


def test_expected_recommendations_are_valid():
    for case in CASES:
        assert case["gold"]["expected"]["recommendation"] in ("APPLY", "MAYBE", "SKIP")


def test_every_case_declares_evidence_and_probes():
    for case in CASES:
        gold = case["gold"]
        assert gold["profile"]["evidence"], case["case_id"]
        assert gold["hallucination_probes"], case["case_id"]


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_gold_evidence_is_verbatim_in_resume(case):
    evidence = case["gold"]["profile"]["evidence"]
    assert validate_evidence(evidence, case["resume"]) == evidence


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_hallucination_probes_are_absent_from_resume(case):
    for probe in case["gold"]["hallucination_probes"]:
        assert validate_evidence([probe], case["resume"]) == []


@pytest.mark.parametrize("case", CASES, ids=CASE_IDS)
def test_deterministic_pipeline_matches_gold(case):
    check = check_case_deterministic(case)
    assert not check.failures, f"{case['case_id']}: {check.failures}"


def test_deterministic_tier_meets_targets():
    metrics = run_deterministic()
    assert metrics["cases"] == 25
    assert metrics["recommendation_correct"] == 25
    assert metrics["match_exact"] == 25
    assert metrics["classification_exact"] == 25
    assert metrics["evidence_grounded"] == 25
    assert metrics["hallucinated_evidence_kept"] == 0


def test_report_marks_unexecuted_llm_tier_as_not_run():
    det = run_deterministic()
    report = build_report(det, None, "no AWS credentials available (test)")
    assert "Cases: 25" in report
    assert "NOT RUN" in report
    assert "Evidence hallucination" in report


def test_default_tier_is_deterministic():
    args = create_parser().parse_args([])
    assert args.tier == "deterministic"
