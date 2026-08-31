from app.career import (
    attach_preparation_steps,
    build_preparation_plan,
    build_skill_gaps,
    build_strengths,
    clean_steps,
    normalize_interview_topics,
)
from app.schemas import CandidateProfile, GapPreparation, JobRequirements, MatchResult


def make_match(**overrides) -> MatchResult:
    defaults = {
        "score": 75,
        "matched_skills": ["docker", "postgresql", "python"],
        "matched_preferred_skills": [],
        "missing_required_skills": ["aws", "terraform"],
        "missing_preferred_skills": ["kubernetes"],
        "missing_critical_skills": ["aws"],
        "experience_match": True,
    }
    return MatchResult(**{**defaults, **overrides})


def test_build_skill_gaps_orders_by_severity_without_duplicates():
    gaps = build_skill_gaps(make_match())

    assert [(gap.skill, gap.severity) for gap in gaps] == [
        ("aws", "critical"),
        ("terraform", "required"),
        ("kubernetes", "preferred"),
    ]
    # aws is critical AND required-missing: reported once, highest severity.
    assert [gap.skill for gap in gaps].count("aws") == 1


def test_build_skill_gaps_empty_when_nothing_missing():
    gaps = build_skill_gaps(
        make_match(
            missing_required_skills=[], missing_preferred_skills=[], missing_critical_skills=[]
        )
    )

    assert gaps == []


def test_build_strengths_states_match_facts_only():
    profile = CandidateProfile(skills=["python"], years_of_experience=2)
    requirements = JobRequirements(required_skills=["python"], critical_skills=["aws"])

    strengths = build_strengths(make_match(), profile, requirements)

    assert strengths == [
        "Meets 3 of 5 required skills: docker, postgresql, python",
        "Experience requirement met: 2 years",
    ]


def test_build_strengths_includes_critical_coverage_and_preferred():
    profile = CandidateProfile(skills=["python"], years_of_experience=2)
    requirements = JobRequirements(critical_skills=["docker"], preferred_skills=["go"])

    strengths = build_strengths(
        make_match(
            missing_critical_skills=[],
            matched_preferred_skills=["go"],
        ),
        profile,
        requirements,
    )

    assert "Also brings preferred skills: go" in strengths
    assert "All explicitly mandatory skills are covered" in strengths


def test_build_strengths_empty_when_nothing_matched():
    profile = CandidateProfile(skills=[])
    requirements = JobRequirements()

    strengths = build_strengths(
        make_match(
            matched_skills=[],
            matched_preferred_skills=[],
            missing_required_skills=["aws"],
            missing_critical_skills=[],
            experience_match=None,
        ),
        profile,
        requirements,
    )

    assert strengths == []


def test_clean_steps_strips_dedupes_and_caps():
    steps = clean_steps(
        [
            "  IAM   fundamentals ",
            "IAM Fundamentals",
            "",
            "S3",
            "Lambda",
            "EC2",
            "EBS",
            "VPC",
            "CloudTrail",
            "KMS",
        ],
        limit=8,
    )

    assert steps == ["IAM fundamentals", "S3", "Lambda", "EC2", "EBS", "VPC", "CloudTrail", "KMS"]


def test_normalize_interview_topics_dedupes_case_insensitive():
    topics = normalize_interview_topics(
        ["PostgreSQL indexes", "postgresql indexes", " REST design ", "", "Docker networking"]
    )

    assert topics == ["PostgreSQL indexes", "REST design", "Docker networking"]


def test_attach_preparation_steps_only_accepts_real_gaps():
    gaps = build_skill_gaps(make_match())
    preparation = [
        GapPreparation(
            skill="AWS", preparation_steps=["IAM fundamentals", "S3", "IAM fundamentals"]
        ),
        # Not a gap: the candidate already evidences it, preparation must be dropped.
        GapPreparation(skill="Python", preparation_steps=["Advanced typing"]),
        # Not asked by the job at all, must be dropped too.
        GapPreparation(skill="Kafka", preparation_steps=["Event streaming basics"]),
    ]

    enriched = attach_preparation_steps(gaps, preparation)

    assert [(gap.skill, gap.severity) for gap in enriched] == [
        ("aws", "critical"),
        ("terraform", "required"),
        ("kubernetes", "preferred"),
    ]
    assert enriched[0].preparation_steps == ["IAM fundamentals", "S3"]
    assert enriched[1].preparation_steps == []
    assert enriched[2].preparation_steps == []


def test_build_preparation_plan_orders_critical_first():
    gaps = attach_preparation_steps(
        build_skill_gaps(make_match()),
        [
            GapPreparation(skill="aws", preparation_steps=["IAM fundamentals", "S3"]),
            GapPreparation(skill="terraform", preparation_steps=["Basics"]),
        ],
    )

    assert build_preparation_plan(gaps) == [
        "aws: IAM fundamentals",
        "aws: S3",
        "terraform: Basics",
    ]
