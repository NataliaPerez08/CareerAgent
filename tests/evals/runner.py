"""CareerAgent evaluation suite.

Two explicitly separated tiers:

- deterministic: runs the gold profiles and requirements through the
  deterministic pipeline (normalize_requirements, build_match_result,
  decide_recommendation, validate_evidence). No LLM calls, free,
  fully reproducible, safe for `make test`.
- llm: runs resume/job extraction through Amazon Bedrock and measures
  extraction accuracy, requirement classification, recommendation
  correctness, evidence hallucination, and tool invocation. Costs
  money and requires AWS credentials: `make eval-llm`, never `make test`.

The runner only reports metrics that were actually executed. Metrics
that were not executed are reported as NOT RUN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.matching import (
    build_match_result,
    normalize_requirements,
    normalize_skill,
    validate_evidence,
)
from app.policy import decide_recommendation
from app.schemas import CandidateProfile, JobRequirements

EVALS_DIR = Path(__file__).resolve().parent
DATASET_PATH = EVALS_DIR / "dataset.json"
ROOT = EVALS_DIR.parents[1]
DEFAULT_REPORT_PATH = ROOT / "dist" / "evals" / "report.md"

CATEGORIES = (
    "strong_match",
    "weak_match",
    "missing_required",
    "missing_preferred",
    "junior_vs_senior",
    "ambiguous_requirement",
    "skill_alias",
    "irrelevant_experience",
    "url_ingestion",
    "pipeline_regression",
    "model_switch",
    "fabricated_evidence",
)

EXPECTED_TOOLS = (
    "analyze_job",
    "calculate_match",
    "generate_interview_plan",
    "identify_skill_gaps",
    "normalize_skills",
)

MATCH_FIELDS = (
    "score",
    "matched_skills",
    "matched_preferred_skills",
    "missing_required_skills",
    "missing_preferred_skills",
    "missing_critical_skills",
    "experience_match",
)


def load_cases() -> list[dict]:
    with open(DATASET_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    cases = data.get("cases", [])
    if not cases:
        raise ValueError(f"Eval dataset is empty: {DATASET_PATH}")
    return cases


@dataclass
class DeterministicCheck:
    case_id: str
    category: str
    recommendation_correct: bool
    match_exact: bool
    classification_exact: bool
    evidence_grounded: bool
    probes_kept: int = 0
    failures: list[str] = field(default_factory=list)


def check_case_deterministic(case: dict) -> DeterministicCheck:
    gold = case["gold"]
    expected = gold["expected"]
    profile = CandidateProfile(**gold["profile"])
    requirements = JobRequirements(**gold["requirements"])

    normalized = normalize_requirements(requirements)
    match = build_match_result(profile, requirements)
    recommendation = decide_recommendation(match)

    failures: list[str] = []

    recommendation_correct = recommendation == expected["recommendation"]
    if not recommendation_correct:
        failures.append(f"recommendation: {recommendation} != {expected['recommendation']}")

    match_exact = True
    for name in MATCH_FIELDS:
        actual = getattr(match, name)
        if actual != expected[name]:
            match_exact = False
            failures.append(f"{name}: {actual!r} != {expected[name]!r}")

    classification_exact = True
    for name, actual in (
        ("critical_skills", normalized.critical_skills),
        ("unknown_requirements", normalized.unknown_requirements),
    ):
        if actual != expected[name]:
            classification_exact = False
            failures.append(f"classification {name}: {actual!r} != {expected[name]!r}")

    gold_evidence = gold["profile"]["evidence"]
    kept = validate_evidence(gold_evidence + gold["hallucination_probes"], case["resume"])
    probes_kept = sum(
        1 for probe in gold["hallucination_probes"] if validate_evidence([probe], case["resume"])
    )
    evidence_grounded = kept == gold_evidence and probes_kept == 0
    if not evidence_grounded:
        failures.append(f"evidence grounding: kept {kept!r}, expected {gold_evidence!r}")

    return DeterministicCheck(
        case_id=case["case_id"],
        category=case["category"],
        recommendation_correct=recommendation_correct,
        match_exact=match_exact,
        classification_exact=classification_exact,
        evidence_grounded=evidence_grounded,
        probes_kept=probes_kept,
        failures=failures,
    )


def _pct(passed: int, total: int) -> float:
    return round(100.0 * passed / total, 1) if total else 0.0


def run_deterministic(cases: list[dict] | None = None) -> dict:
    cases = cases if cases is not None else load_cases()
    checks = [check_case_deterministic(case) for case in cases]
    total = len(checks)

    by_category: dict[str, dict[str, int]] = {}
    for check in checks:
        bucket = by_category.setdefault(
            check.category,
            {"cases": 0, "recommendation_correct": 0, "match_exact": 0},
        )
        bucket["cases"] += 1
        bucket["recommendation_correct"] += int(check.recommendation_correct)
        bucket["match_exact"] += int(check.match_exact)

    return {
        "tier": "deterministic",
        "cases": total,
        "recommendation_correct": sum(c.recommendation_correct for c in checks),
        "match_exact": sum(c.match_exact for c in checks),
        "classification_exact": sum(c.classification_exact for c in checks),
        "evidence_grounded": sum(c.evidence_grounded for c in checks),
        "hallucinated_evidence_kept": sum(c.probes_kept for c in checks),
        "by_category": by_category,
        "checks": checks,
    }


def bedrock_credentials_available() -> tuple[bool, str]:
    try:
        import boto3

        session = boto3.Session(profile_name=os.getenv("AWS_PROFILE"))
        sts = session.client("sts", region_name=os.getenv("AWS_REGION", "us-east-1"))
        sts.get_caller_identity()
        return True, ""
    except Exception as exc:  # noqa: BLE001 - probe must report any credential-chain failure
        return False, f"{type(exc).__name__}: {exc}"


@dataclass
class LlmCheck:
    case_id: str
    category: str
    error: str = ""
    recall: float = 0.0
    precision: float = 0.0
    years_exact: bool = False
    classification_exact: bool = False
    invented_statuses: list[str] = field(default_factory=list)
    demoted_statuses: list[str] = field(default_factory=list)
    recommendation_correct: bool = False
    ungrounded_evidence: int = 0
    failures: list[str] = field(default_factory=list)


def check_case_llm(case: dict) -> LlmCheck:
    from app.service import extract_candidate_profile, extract_job_requirements

    gold = case["gold"]
    expected = gold["expected"]
    check = LlmCheck(case_id=case["case_id"], category=case["category"])

    try:
        profile = extract_candidate_profile(case["resume"])
        requirements = extract_job_requirements(case["job_description"])
    except Exception as exc:  # noqa: BLE001 - harness records case errors in the report
        check.error = f"{type(exc).__name__}: {exc}"
        check.failures.append(check.error)
        return check

    gold_skills = {normalize_skill(s) for s in gold["profile"]["skills"] if s.strip()}
    extracted_skills = {normalize_skill(s) for s in profile.skills if s.strip()}
    common = gold_skills & extracted_skills
    check.recall = round(len(common) / len(gold_skills), 3) if gold_skills else 1.0
    if extracted_skills:
        check.precision = round(len(common) / len(extracted_skills), 3)
    else:
        check.precision = 1.0 if not gold_skills else 0.0

    check.years_exact = profile.years_of_experience == gold["profile"]["years_of_experience"]

    normalized = normalize_requirements(requirements)
    exp_required = set(expected["matched_skills"]) | set(expected["missing_required_skills"])
    exp_preferred = set(expected["matched_preferred_skills"]) | set(
        expected["missing_preferred_skills"]
    )
    exp_critical = set(expected["critical_skills"])
    exp_unknown = set(expected["unknown_requirements"])
    got_required = set(normalized.required_skills)
    got_preferred = set(normalized.preferred_skills)
    got_critical = set(normalized.critical_skills)
    got_unknown = set(normalized.unknown_requirements)

    check.classification_exact = (
        got_required == exp_required
        and got_preferred == exp_preferred
        and got_critical == exp_critical
        and got_unknown == exp_unknown
    )
    check.invented_statuses = sorted(
        (got_required | got_preferred | got_critical)
        - (exp_required | exp_preferred | exp_critical)
    )
    check.demoted_statuses = sorted(
        (exp_required | exp_preferred | exp_critical)
        - (got_required | got_preferred | got_critical)
    )

    match = build_match_result(profile, requirements)
    recommendation = decide_recommendation(match)
    check.recommendation_correct = recommendation == expected["recommendation"]

    check.ungrounded_evidence = sum(
        1 for item in profile.evidence if validate_evidence([item], case["resume"]) == []
    )

    if not check.years_exact:
        check.failures.append(
            f"years: {profile.years_of_experience!r} != {gold['profile']['years_of_experience']!r}"
        )
    if not check.classification_exact:
        check.failures.append(
            "classification buckets differ: "
            f"required={sorted(got_required)} preferred={sorted(got_preferred)} "
            f"critical={sorted(got_critical)} unknown={sorted(got_unknown)}"
        )
    if check.invented_statuses:
        check.failures.append(f"invented statuses: {check.invented_statuses}")
    if check.demoted_statuses:
        check.failures.append(f"demoted statuses: {check.demoted_statuses}")
    if not check.recommendation_correct:
        check.failures.append(f"recommendation: {recommendation} != {expected['recommendation']}")
    if check.ungrounded_evidence:
        check.failures.append(f"ungrounded evidence items: {check.ungrounded_evidence}")
    return check


def check_tool_invocation(case: dict) -> tuple[bool, set[str], str]:
    from app.agent import AGENT_WORKFLOW_PROMPT, build_agent

    agent = build_agent()
    prompt = AGENT_WORKFLOW_PROMPT.format(resume=case["resume"], job=case["job_description"])
    result = agent(prompt)

    tool_metrics = getattr(getattr(result, "metrics", None), "tool_metrics", None)
    if tool_metrics is None:
        return False, set(), "agent result exposed no tool metrics to inspect tool usage"

    called = {name for name in tool_metrics if not name.startswith("loop_")}
    missing = sorted(set(EXPECTED_TOOLS) - called)
    error = f"missing tools: {missing}" if missing else ""
    return not missing, called, error


def run_llm(cases: list[dict], tools_sample: int = 3) -> dict:
    checks = [check_case_llm(case) for case in cases]
    completed = [c for c in checks if not c.error]
    total = len(checks)

    sample_cases = cases[:tools_sample] if tools_sample > 0 else []
    tool_runs = []
    for case in sample_cases:
        ok, called, error = check_tool_invocation(case)
        tool_runs.append(
            {"case_id": case["case_id"], "ok": ok, "called": sorted(called), "error": error}
        )

    return {
        "tier": "llm",
        "cases": total,
        "errors": sum(1 for c in checks if c.error),
        "skill_recall_avg": (
            round(sum(c.recall for c in completed) / len(completed), 3) if completed else 0.0
        ),
        "skill_precision_avg": (
            round(sum(c.precision for c in completed) / len(completed), 3) if completed else 0.0
        ),
        "years_exact": sum(c.years_exact for c in completed),
        "classification_exact": sum(c.classification_exact for c in completed),
        "invented_statuses": sum(len(c.invented_statuses) for c in completed),
        "demoted_statuses": sum(len(c.demoted_statuses) for c in completed),
        "recommendation_correct": sum(c.recommendation_correct for c in completed),
        "ungrounded_evidence": sum(c.ungrounded_evidence for c in completed),
        "tool_runs": tool_runs,
        "tool_invocation_ok": sum(1 for r in tool_runs if r["ok"]),
        "model_id": os.getenv("BEDROCK_MODEL_ID", "amazon.nova-micro-v1:0"),
        "region": os.getenv("AWS_REGION", "us-east-1"),
        "checks": checks,
    }


def _line(label: str, passed: int, total: int) -> str:
    return f"{label:<28}{_pct(passed, total):>5}%  ({passed}/{total})"


def build_report(det: dict, llm: dict | None, llm_status: str) -> str:
    lines: list[str] = []
    lines.append("CareerAgent Eval")
    lines.append("===============")
    lines.append("")
    lines.append(f"Cases: {det['cases']}")
    lines.append("")

    lines.append("Deterministic tier (no LLM calls)")
    lines.append("---------------------------------")
    lines.append(_line("Correct recommendation:", det["recommendation_correct"], det["cases"]))
    lines.append(_line("Match exactness:", det["match_exact"], det["cases"]))
    lines.append(_line("Requirement classification:", det["classification_exact"], det["cases"]))
    lines.append(_line("Evidence grounding:", det["evidence_grounded"], det["cases"]))
    lines.append(
        f"{'Evidence hallucination':<28}"
        f"{det['hallucinated_evidence_kept']:>5} kept fabricated items (target: 0)"
    )
    lines.append("")

    lines.append("Per-category (cases / recommendation / exact match)")
    for category in sorted(det["by_category"]):
        bucket = det["by_category"][category]
        lines.append(
            f"  {category:<24}{bucket['cases']:>3}"
            f"  {bucket['recommendation_correct']}/{bucket['cases']}"
            f"  {bucket['match_exact']}/{bucket['cases']}"
        )
    lines.append("")

    failures = [f for check in det["checks"] for f in check.failures]
    lines.append("Deterministic failures: " + ("none" if not failures else str(len(failures))))
    for failure in failures:
        lines.append(f"  - {failure}")
    lines.append("")

    lines.append("LLM tier (Amazon Bedrock)")
    lines.append("-------------------------")
    if llm is None:
        lines.append(f"NOT RUN: {llm_status}")
        lines.append("Only metrics actually executed are reported above.")
    else:
        completed = llm["cases"] - llm["errors"]
        lines.append(f"Model: {llm['model_id']} ({llm['region']})")
        lines.append(f"Cases: {llm['cases']} ({llm['errors']} errored)")
        lines.append(f"{'Skill recall (avg)':<28}{llm['skill_recall_avg'] * 100:>5}%")
        lines.append(f"{'Skill precision (avg)':<28}{llm['skill_precision_avg'] * 100:>5}%")
        lines.append(_line("Years extraction:", llm["years_exact"], completed))
        lines.append(_line("Requirement classification:", llm["classification_exact"], completed))
        lines.append(_line("Recommendation correctness:", llm["recommendation_correct"], completed))
        lines.append(f"{'Invented statuses':<28}{llm['invented_statuses']:>5}")
        lines.append(f"{'Demoted statuses':<28}{llm['demoted_statuses']:>5}")
        lines.append(
            f"{'Evidence hallucination':<28}"
            f"{_pct(llm['ungrounded_evidence'], completed):>5}%  ({llm['ungrounded_evidence']} items)"
        )
        lines.append(
            _line(
                "Tool invocation:",
                llm["tool_invocation_ok"],
                len(llm["tool_runs"]),
            )
            + f"  sampled: {', '.join(r['case_id'] for r in llm['tool_runs'])}"
        )
        for run in llm["tool_runs"]:
            if run["error"]:
                lines.append(f"  - {run['case_id']}: {run['error']}")
        for check in llm["checks"]:
            if check.error:
                lines.append(f"  - {check.case_id}: {check.error}")
            elif check.failures:
                lines.append(f"  - {check.case_id}: {'; '.join(check.failures)}")
    lines.append("")

    lines.append(f"Generated: {datetime.now(UTC).isoformat(timespec='seconds')}")
    return "\n".join(lines) + "\n"


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the CareerAgent eval suite.")
    parser.add_argument(
        "--tier",
        choices=("deterministic", "llm", "all"),
        default="deterministic",
        help="deterministic runs free of LLM calls; llm requires AWS credentials",
    )
    parser.add_argument(
        "--cases",
        type=int,
        default=None,
        help="run only the first N cases (cost control for the LLM tier)",
    )
    parser.add_argument(
        "--tools-sample",
        type=int,
        default=3,
        help="agent-loop runs sampled for the tool invocation metric (0 disables)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="path to also write the report (default: dist/evals/report.md)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = create_parser().parse_args(argv)
    cases = load_cases()
    if args.cases is not None:
        cases = cases[: args.cases]

    det = run_deterministic(cases)
    det_ok = (
        det["recommendation_correct"] == det["cases"]
        and det["match_exact"] == det["cases"]
        and det["classification_exact"] == det["cases"]
        and det["evidence_grounded"] == det["cases"]
        and det["hallucinated_evidence_kept"] == 0
    )

    llm: dict | None = None
    llm_status = "not requested (use --tier llm or make eval-llm)"
    llm_ok = True
    if args.tier in ("llm", "all"):
        available, reason = bedrock_credentials_available()
        if available:
            llm = run_llm(cases, tools_sample=args.tools_sample)
            llm_ok = llm["errors"] == 0 and llm["ungrounded_evidence"] == 0
        else:
            llm_status = f"no AWS credentials available ({reason})"
            if args.tier == "llm":
                print(f"ERROR: cannot run the LLM tier: {llm_status}", file=sys.stderr)
                return 1

    report = build_report(det, llm, llm_status)
    print(report, end="")
    if str(args.output):
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
        print(f"Report written to {args.output}")

    return 0 if det_ok and llm_ok else 1


if __name__ == "__main__":
    sys.exit(main())
