"""Centralized recommendation policy.

APPLY: score >= apply_threshold AND no critical skill missing
       AND no explicit experience mismatch.
MAYBE: score >= maybe_threshold but APPLY conditions not met.
SKIP:  score < maybe_threshold OR any critical skill missing.
"""

from dataclasses import dataclass

from app.schemas import MatchResult, Recommendation


@dataclass(frozen=True)
class RecommendationPolicy:
    apply_threshold: int = 70
    maybe_threshold: int = 45


DEFAULT_POLICY = RecommendationPolicy()


def decide_recommendation(
    match: MatchResult,
    policy: RecommendationPolicy = DEFAULT_POLICY,
) -> Recommendation:
    if match.missing_critical_skills or match.score < policy.maybe_threshold:
        return "SKIP"
    if match.score >= policy.apply_threshold and match.experience_match is not False:
        return "APPLY"
    return "MAYBE"
