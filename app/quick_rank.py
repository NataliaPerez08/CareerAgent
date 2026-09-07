"""Deterministic quick batch ranking (sprint Day 8).

Ranking is intentionally shallow: for each job we check which of the
candidate's skills are mentioned in the job text (alias-aware, word
boundary matching) and rank by the share of matched skills. No LLM call
per job — the only model call is the candidate profile extraction that
the caller performs. The user then selects one job for the full deep
analysis (the normal evaluation pipeline).

Recommendations reuse the centralized policy: this module builds the
same kind of ``MatchResult`` the deep pipeline uses and lets
``decide_recommendation`` apply the shared APPLY/MAYBE/SKIP thresholds,
so quick ranking and deep analysis never disagree on thresholds.
"""

import re

from app import job_ingestion
from app.matching import SKILL_ALIASES, normalize_skill
from app.policy import DEFAULT_POLICY, RecommendationPolicy, decide_recommendation
from app.schemas import CandidateProfile, MatchResult, QuickRankingJob, QuickRankingResult

MAX_QUICK_JOBS = 10

QUICK_RANKING_NOTE = (
    "Quick ranking is a cheap heuristic: it counts which of your skills are "
    "mentioned in each job text (alias-aware). Select one job for deep analysis."
)


def _search_terms(normalized_skill: str) -> set[str]:
    """The skill name plus every alias that normalizes to it."""
    terms = {normalized_skill}
    for alias, canonical in SKILL_ALIASES.items():
        if canonical == normalized_skill:
            terms.add(alias)
    return terms


def _mentioned(text: str, term: str) -> bool:
    if not term:
        return False
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", text) is not None


def _skills(profile: CandidateProfile) -> list[str]:
    return sorted(
        {normalize_skill(skill) for skill in profile.skills if skill and skill.strip()}
    )


def rank_jobs(
    profile: CandidateProfile,
    jobs: list[dict],
    policy: RecommendationPolicy = DEFAULT_POLICY,
) -> QuickRankingResult:
    """Rank already-fetched job descriptions deterministically.

    ``jobs`` entries carry url/title/company/description keys and an
    optional ``error``; entries without a usable description become an
    error row instead of failing the whole batch.
    """
    candidate = _skills(profile)
    rows: list[QuickRankingJob] = []
    for entry in jobs:
        url = entry.get("url", "")
        title = entry.get("title") or "Job"
        company = entry.get("company") or ""
        error = entry.get("error")
        if error or not entry.get("description"):
            rows.append(
                QuickRankingJob(
                    url=url,
                    title=title,
                    company=company,
                    error=error or "No job description available.",
                )
            )
            continue

        text = " ".join(entry["description"].lower().split())
        matched = sorted(
            skill
            for skill in candidate
            if any(
                _mentioned(text, term)
                for term in _search_terms(normalize_skill(skill))
            )
        )
        missing = sorted(set(candidate) - set(matched))
        score = round(len(matched) / len(candidate) * 100) if candidate else 0
        match = MatchResult(
            score=score,
            matched_skills=matched,
            matched_preferred_skills=[],
            missing_required_skills=missing,
            missing_preferred_skills=[],
            missing_critical_skills=[],
            experience_match=None,
        )
        rows.append(
            QuickRankingJob(
                url=url,
                title=title,
                company=company,
                score=score,
                recommendation=decide_recommendation(match, policy),
                matched_skills=matched,
                missing_skills=missing,
            )
        )

    rows.sort(key=lambda row: (row.score, row.title), reverse=True)
    return QuickRankingResult(
        candidate_skills=candidate,
        jobs=rows,
        note=QUICK_RANKING_NOTE,
    )


def fetch_and_rank(
    profile: CandidateProfile,
    urls: list[str],
    *,
    fetch=None,
    policy: RecommendationPolicy = DEFAULT_POLICY,
) -> QuickRankingResult:
    """Fetch each job URL and rank the batch.

    ``fetch`` is resolved at call time (and therefore monkeypatchable in
    tests); a failing URL becomes an error row, never a failed batch.
    """
    fetch = fetch or job_ingestion.fetch_job
    jobs = []
    for url in urls:
        try:
            posting = fetch(url)
        except job_ingestion.JobFetchError as exc:
            jobs.append({"url": url, "error": str(exc)})
            continue
        jobs.append(
            {
                "url": url,
                "title": posting.title,
                "company": posting.company,
                "description": posting.description,
            }
        )
    return rank_jobs(profile, jobs, policy)