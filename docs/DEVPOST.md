# Devpost submission draft — CareerAgent

> Paste-ready copy for the Devpost form. Replace the VIDEO link once the
> recording is uploaded. Screenshots are already in `docs/screenshots/`.

## Project name

CareerAgent — know if the job is worth your hour, before you apply

## Tagline (one line)

An agentic career copilot that reads your resume and a job posting, then
tells you APPLY / MAYBE / SKIP — with verbatim evidence, skill gaps and a
preparation plan. It never claims skills your resume doesn't prove.

## Description

### The problem

Job postings are noisy. Requirements mix mandatory, preferred and
wish-list items; candidates guess whether a missing bullet is fatal or
irrelevant. Applying to a bad-fit job costs an hour of tailoring and an
interview slot; skipping a good-fit job costs an opportunity.

### The solution

CareerAgent evaluates a resume against a job description and returns a
structured verdict:

- recommendation `APPLY` / `MAYBE` / `SKIP` with a 0-100 match score,
- matched, missing-required and missing-preferred skills,
- **evidence**: verbatim quotes from the resume for every claimed match,
- skill gaps ranked by severity, each with a preparation plan,
- interview topics and a study plan for the gaps.

The anti-hallucination contract: every matched skill must be grounded in
a quote from the resume. A validator drops any model claim it cannot
ground — fabricated experience is measured as 0 in the eval suite.

### How it works

```text
Resume + Job
      ↓
Strands agent (Amazon Bedrock, Nova Micro)
 ├── analyze_job             classify + normalize requirements
 ├── normalize_skills        canonical names on both sides
 ├── calculate_match         deterministic score + policy verdict
 ├── identify_skill_gaps     severity: critical > required > preferred
 └── generate_interview_plan validated preparation steps
      ↓
Structured EvaluationResult (Pydantic) → CLI / FastAPI + web UI / AgentCore
```

Design rule: **the LLM interprets, the code decides.** Percentages,
thresholds, alias normalization and the APPLY/MAYBE/SKIP policy are
deterministic Python; the model only extracts, classifies and explains.

### Built with

Python · Strands Agents SDK · Amazon Bedrock (Nova Micro) · FastAPI ·
PostgreSQL/SQLite + Alembic · Docker · pytest · a hand-drawn Y2K desktop UI

### Demo

See `docs/DEMO.md`: load the example, click Analyze, watch the live
stage progress, read the evidence. Core flow < 3 minutes.
VIDEO: <link>

### Evaluation

32-case eval suite (`make eval`, deterministic, reproducible): 100%
recommendation correctness, 100% evidence grounding, 0 fabricated
evidence. The LLM tier runs explicitly (`make eval-llm`) and is reported
only when actually executed.

### Limitations (honest)

- Model run-to-run variance at temperature 0.2.
- Job URL loading is best-effort: JS-rendered pages, login walls and
  anti-bot systems fall back to manual paste.
- Bedrock transient degradation windows increase latency (documented,
  with a 504 and a clear UI message instead of a dead spinner).

### Future work

Multi-CV profiles, ATS-friendly export, longitudinal tracking of gap
closure, richer company research.
