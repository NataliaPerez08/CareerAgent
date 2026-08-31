import pytest
from pydantic import ValidationError

from app.policy import DEFAULT_POLICY, RecommendationPolicy, decide_recommendation
from app.schemas import MatchResult


def make_match(score, critical=None, experience=None):
    return MatchResult(
        score=score,
        missing_critical_skills=critical or [],
        experience_match=experience,
    )


def test_apply_on_high_score_without_blockers():
    assert decide_recommendation(make_match(75)) == "APPLY"
    assert decide_recommendation(make_match(70)) == "APPLY"


def test_apply_requires_experience_match():
    assert decide_recommendation(make_match(100, experience=False)) == "MAYBE"
    assert decide_recommendation(make_match(100, experience=True)) == "APPLY"
    assert decide_recommendation(make_match(100, experience=None)) == "APPLY"


def test_maybe_between_thresholds():
    assert decide_recommendation(make_match(69)) == "MAYBE"
    assert decide_recommendation(make_match(45)) == "MAYBE"


def test_skip_below_threshold():
    assert decide_recommendation(make_match(44)) == "SKIP"
    assert decide_recommendation(make_match(0)) == "SKIP"


def test_skip_on_missing_critical_skill_even_with_perfect_score():
    match = make_match(100, critical=["aws"])
    assert decide_recommendation(match) == "SKIP"


def test_thresholds_are_centralized_and_overridable():
    strict = RecommendationPolicy(apply_threshold=90, maybe_threshold=60)

    assert decide_recommendation(make_match(70), policy=strict) == "MAYBE"
    assert decide_recommendation(make_match(59), policy=strict) == "SKIP"
    assert decide_recommendation(make_match(95), policy=strict) == "APPLY"


def test_default_policy_values():
    assert DEFAULT_POLICY.apply_threshold == 70
    assert DEFAULT_POLICY.maybe_threshold == 45


def test_match_result_rejects_out_of_range_score():
    with pytest.raises(ValidationError):
        MatchResult(score=101)
    with pytest.raises(ValidationError):
        MatchResult(score=-1)
