# CareerAgent

**Should you apply? Get an evidence-based answer, not generic advice.**

CareerAgent evaluates a resume against a job description and returns a
structured verdict — matched skills backed by verbatim resume evidence,
missing skills by severity, and a concrete preparation plan — with a
strict no-hallucination contract: nothing is ever claimed that the
resume cannot prove.

Built for the **Agents for Humans Hackathon**.

## Problem

Job descriptions are noisy. Candidates — especially early-career ones —
struggle to tell whether they are actually underqualified or simply
missing a small number of non-critical requirements. Generic career
chatbots make this worse: they produce plausible advice that isn't
anchored to the actual resume, so you still don't know what you're
really missing.

CareerAgent evaluates the candidate using **evidence from the resume**,
and nothing else. If the resume provides no evidence for something, the
system says *unknown* — it never guesses.

## Solution

Paste (or upload) a resume, paste a job description, press **Analyze**:

- a deterministic **APPLY / MAYBE / SKIP** recommendation with a match score;
- matched skills, each backed by **verbatim evidence quoted from the resume**
  (validated by code — invented evidence is dropped);
- missing requirements split by severity (critical / required / preferred),
  and requirements whose status the description leaves ambiguous kept as
  *unknown* (never guessed, never counted against the score);
- a **skill-gap preparation plan** and concrete **interview topics**;
- everything persisted so you can revisit past evaluations.

## Demo

The reproducible demo scenario lives in
[`docs/DEMO.md`](docs/DEMO.md) (< 3 minutes, one click via **Load
example**). Verified outcome of the demo inputs
(`examples/demo_resume.txt` + `examples/demo_job.txt`):

```text
Recommendation:   APPLY
Score:            80   (4 of 5 required skills)
Matched:          python, rest api, postgresql, docker
Missing required: aws            ← the gap, with a preparation plan
Missing preferred: ci/cd, kubernetes
Evidence:         5 verbatim quotes from the resume
```

Deliberately not a 100% match: the point of the product is showing
*exactly* what you're missing and how to close it — not cheerleading.

## How it works

**LLM interprets. Code decides. Evals verify.**

```text
Resume ──> LLM extraction ──> CandidateProfile   (Pydantic)
Job    ──> LLM extraction ──> JobRequirements    (Pydantic)
                    ↓
        Normalization (aliases, context words)
                    ↓
        Deterministic matching (score, evidence validation)
                    ↓
        Recommendation policy (centralized thresholds)
                    ↓
        Gap analysis (severity from code, content from LLM)
                    ↓
        Plan + explanation (single LLM call, from the computed result)
```

The LLM (Amazon Nova Micro) only does what a model should do: extract
structure from ambiguous text and draft plan/explanation content. The
score, thresholds, severity ranking, and the APPLY/MAYBE/SKIP verdict
are 100% deterministic Python — the model cannot quietly change the
business rules. The whole evaluation is **three single-shot model calls
with no tools attached** — no tool loops, one answer per task.

## Architecture

```mermaid
flowchart TB
    U(("User")) --> IO["Web UI / CLI"]
    IO --> API["FastAPI /api/v1"]
    API --> PIPE["Evaluation pipeline (app.service)"]
    API --> DB[("PostgreSQL (SQLite locally)")]

    subgraph BED ["Strands Agent — Amazon Bedrock, Amazon Nova Micro (3 single-shot calls, no tools)"]
        PEX["Resume → CandidateProfile (LLM extraction)"]
        REX["Job → JobRequirements (LLM extraction)"]
        PLAN["Plan + explanation (LLM draft + reasoning, grounded)"]
    end

    subgraph CORE ["Deterministic core — plain Python (agent tools)"]
        NORM["normalize_skills"]
        MATCH["calculate_match"]
        POLICY["decide_recommendation"]
        GAPS["identify_skill_gaps"]
    end

    PIPE --> PEX & REX
    PEX --> NORM
    REX --> NORM
    NORM --> MATCH --> POLICY --> GAPS --> PLAN
```

The same evaluation core runs behind three runtimes — CLI, FastAPI +
web UI, and an Amazon Bedrock AgentCore Runtime adapter — without the
core ever depending on any of them.

**AgentCore status:** a live runtime (`career_agent`) is deployed and
**READY** (v4, `PYTHON_3_11`) with the core and ARM64-vendored dependencies,
and **remote invocation works** — the demo evaluates to `APPLY` (score 80) in
~9 s with stage/timing logs in CloudWatch. Two non-obvious deployment facts
(Arm64-only runtime that does not pip-install `requirements.txt`; strands-agents
tool serialization breaking on Python 3.13) are documented in
[`docs/deploy/agentcore.md`](docs/deploy/agentcore.md).

## Why agentic?

The Strands agent works through **five tools** — an inspectable
workflow, not a single mega-prompt:

```text
Agent
 ├── analyze_job            (classify + normalize requirements)
 ├── normalize_skills       (canonical names for both sides)
 ├── calculate_match        (deterministic score + recommendation)
 ├── identify_skill_gaps    (severity: critical > required > preferred)
 └── generate_interview_plan (validate + assemble preparation)
```

Each step is deterministic where determinism is possible, individually
tested, and demoable. The agent's freedom is confined to interpretation
and drafting — never to the verdict.

## Tech stack

Python 3.11+ · Strands Agents SDK · Amazon Bedrock (Amazon Nova Micro)
· FastAPI · Pydantic · SQLAlchemy 2.0 + Alembic (SQLite/PostgreSQL)
· Docker · Nix flake · pytest · Ruff

## Features

- Resume input as pasted text, TXT, or **PDF** (validated: format,
  size, corrupt and scanned/image-only files rejected explicitly)
- Job input as pasted text **or loaded from a public URL**
  (`POST /api/v1/jobs/fetch`): best-effort extraction of title, company
  and description from page metadata, with graceful fallback to manual
  paste when a page blocks automated reads
- **Live progress while analyzing** (`POST /api/v1/evaluations/stream`,
  SSE): the UI shows each real pipeline stage as it happens — reading
  resume, extracting requirements, matching skills, preparing the
  recommendation, saving — instead of a dead spinner; model timeouts
  are reported explicitly as 504
- **Recent evaluations**: the UI lists past runs (title, score,
  recommendation, age) from the existing persistence layer and reopens
  any stored evaluation with one click — no auth added
- **Batch ranking** (`POST /api/v1/batch/quick-ranking`): paste up to 10
  job URLs and get a cheap, deterministic ranking against your resume
  (one model call for the profile, no per-job LLM analysis). Click a row
  in the UI to run the full deep analysis on that job
- Structured `EvaluationResult` contract across CLI, API and UI
- Skill **normalization**: aliases (`postgres` → `postgresql`,
  `cicd` → `ci/cd`, `cpp` → `c++`, `rest api development` →
  `rest api`) and context-word stripping (`AWS experience` → `aws`)
- Ambiguous requirements kept as `unknown` — never counted in the score
- Centralized recommendation policy (APPLY ≥ 70 with no critical miss
  and no experience mismatch; SKIP < 45 or critical miss; else MAYBE)
- Evaluation history in PostgreSQL/SQLite, migrations on boot
- OpenAPI docs, request validation, explicit error mapping
  (413/415/422/502), structured logging
- Two-tier eval suite (see below)

## Evaluation

Deterministic tier results from a concrete execution — **2026-09-07, 33
cases (25 original + 8 regression cases added on sprint Day 9)** — not
eternally hardcoded numbers. Re-run with `make eval` /
`make eval-llm`:

```text
Deterministic tier (no LLM, reproducible)
Correct recommendation:      100% (33/33)
Match exactness:             100% (33/33)
Requirement classification:  100% (33/33)
Evidence grounding:          100% (33/33)
Batch ranking order:         100% (1/1)
Evidence hallucination:        0 fabricated items kept
```

The eval suite ([`tests/evals/`](tests/evals/)) covers 33 cases: the 8
original categories (strong/weak match, missing required/preferred
skills, junior-vs-senior experience gates, ambiguous requirements,
skill aliases, irrelevant experience) plus regression cases for URL
ingestion, alias coverage (`cicd`/`cpp`), the optimized single-shot
pipeline, a model-switch guard, fabricated evidence and batch ranking.
Cases include **hallucination probes** — plausible-but-absent resume
claims that the evidence validator must drop.

Two tiers, deliberately separated for cost:

- `make test` and `make eval` **never call Bedrock** — the
  deterministic tier runs free in CI, and the dataset integrity plus
  the full deterministic tier are part of the normal test suite.
- `make eval-llm` makes real model calls (~70 on Nova Micro) and must
  be run explicitly.

Only metrics actually executed are reported (`dist/evals/report.md`,
timestamped). The LLM tier last executed on the 25-case dataset at
temperature 0.2 measured 100% recall/precision, 96% requirement
classification, 100% recommendations, 0 entity fabrications and 100%
tool invocation (see [docs/MODEL_BENCHMARK.md](docs/MODEL_BENCHMARK.md)).
The Day 9 re-run of the LLM tier against the expanded 33-case dataset
was attempted but could not complete: Amazon Bedrock was degraded that
window (per-call responses of 60+s, the documented transient service
variance), so those metrics are **NOT RUN rather than fabricated**. The
deterministic assertions for the 8 new regression cases are green.
Registry and category coverage are continuously enforced by
`tests/test_evals.py`.

A model comparison (Nova Micro vs Nova Lite — latency, quality, cost)
with the measured data and the decision to keep Micro lives in
[`docs/MODEL_BENCHMARK.md`](docs/MODEL_BENCHMARK.md).

## Quick start

```bash
python3.11 -m venv .venv && source .venv/bin/activate
make dev          # install with dev extras
aws configure     # credentials with Bedrock access (Nova Micro)
make run          # http://127.0.0.1:8000/  → Load example → Analyze
```

## AWS setup

CareerAgent talks to Amazon Bedrock through the Strands SDK using the
default AWS credential chain — no keys in the repo, no keys in `.env`
(see `.env.example`). Configure any standard mechanism:

```bash
aws configure     # or SSO, or environment variables in your shell
```

Optional environment variables (defaults in parentheses):
`AWS_REGION` (`us-east-1`), `BEDROCK_MODEL_ID`
(`amazon.nova-micro-v1:0`), `BEDROCK_TEMPERATURE` (`0.2`).

We deliberately develop and demo on **Nova Micro, the cheapest Bedrock
model**, and fixed extraction quirks in a deterministic normalization
layer instead of upgrading the model.

## Running locally

With Nix:

```bash
nix develop
python -m venv .venv && source .venv/bin/activate
make dev
```

Without Nix (Python 3.11+ required — use the `python3.11` binary
explicitly if your default `python3` is older):

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
make dev
```

The deterministic layer needs no LLM and is the fastest smoke check:

```bash
make test
```

### CLI

```bash
make cli                                  # demo pair: examples/demo_*.txt
python -m app.cli cv.pdf job.txt          # real files (PDF or TXT)
python -m app.cli --chat                  # Strands agent, 5-tool free loop
```

### Web UI / API

```bash
make run                                  # UI on :8000, docs on /docs
```

Text and upload endpoints (stable `/api/v1` contract):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evaluations \
  -H 'content-type: application/json' \
  -d '{"resume_text": "...", "job_description": "..."}'

curl -X POST http://127.0.0.1:8000/api/v1/evaluations/upload \
  -F 'resume=@cv.pdf' \
  -F 'job_description=Junior backend engineer. Requires Python.'
```

Responses are structured `EvaluationResult` JSON — recommendation,
score, matched/missing skills by severity, verbatim evidence,
strengths, skill gaps with preparation steps, interview topics, and
reasoning. Errors are explicit: `422` invalid payload/empty or
unreadable inputs, `413` too large, `415` unsupported format, `502`
model failure.

### Persistence

Every evaluation is stored (`Candidate → Resume`, `Resume + Job →
Evaluation`): score, recommendation, skill lists, evidence, gaps,
timestamps — never internal prompts. Selected by `DATABASE_URL`
(default zero-config SQLite; PostgreSQL via docker compose). Alembic
owns the schema and migrations run automatically on API startup, or:

```bash
make migrate
curl http://127.0.0.1:8000/api/v1/evaluations        # history
curl http://127.0.0.1:8000/api/v1/evaluations/1      # stored evaluation
```

## Docker

```bash
make docker-build && make docker-run      # single container (SQLite)
make compose-up                           # API + PostgreSQL
make compose-down
```

`docker compose` starts PostgreSQL and the API (migrations on boot,
data persists in the `pgdata` volume) and mounts your `~/.aws`
credentials read-only for Bedrock access. Verified end-to-end from a
clean build: health check, UI, a real Bedrock evaluation, persistence
and history.

## Tests

```bash
make test      # 255 tests, no LLM calls (models mocked where relevant)
make lint      # ruff
```

## Latency & benchmarking

Every evaluation records a structured, per-stage latency breakdown
(one JSON log line) through `app/timing.py`, together with counters
that pin the agent-loop cost (`llm_calls`, `llm_cycles`, `tool_calls`,
`input_tokens`, `output_tokens`):

```json
{"event": "api_evaluation_timings", "request_total_ms": 34200,
 "resume_parse_ms": 120, "profile_extraction_ms": 8120,
 "requirements_extraction_ms": 4100, "deterministic_matching_ms": 85,
 "recommendation_ms": 1, "plan_and_explanation_ms": 15500,
 "persistence_ms": 18, "llm_ms": 27720, "tools_ms": 85,
 "llm_calls": 3, "llm_cycles": 3, "tool_calls": 0,
 "input_tokens": 4250, "output_tokens": 1180}
```

One evaluation costs exactly three model calls — single-shot
structured extractions for candidate profile, job requirements and the
final plan — all with no tools attached. Deterministic matching
(skill normalization, set comparison, policy thresholds, strengths and
gaps) happens in Python between the extraction and the final plan, so
the model never calculates and never loops on tool calls.

Stage names are shared across the API (`api_evaluation_timings`),
the AgentCore runtime (`agentcore_evaluation_timings`) and the
benchmark tool. Only durations and tiny metadata are logged — never
resume/job content or prompts.

A reproducible latency baseline can be produced with:

```bash
make benchmark        # 5 real Bedrock runs (needs AWS credentials)
python scripts/benchmark.py --count 20   # more runs for tighter percentiles
make benchmark-mock   # no LLM: deterministic pipeline floor, safe for CI
```

The report (`dist/benchmark/report.md`) and machine-readable
`dist/benchmark/baseline.json` hold p50/p95/mean/min/max per stage,
plus the model, region and input files used. `--compare` prints the
delta against the previous baseline. Run-to-run measurements of
pipeline stages are recorded per evaluation in the JSON logs for
before/after comparisons of any optimization.

## Security / privacy

- Resumes contain **PII**. CareerAgent is a hackathon project, **not a
  production service** — production use would need access controls,
  retention limits and encryption decisions we have not built.
- Logs record input sizes and stage timings, **never full resumes or
  full prompts**; the database stores resume/job text but no internal
  prompts.
- No secrets in the repo: AWS credentials come from the standard
  credential chain (never committed, never in `.env`); `.env.example`
  documents variables without real values.
- All dynamic content in the web UI is rendered XSS-safe via
  `textContent`/`createElement`.

## Limitations

Honest ones:

- **LLM run-to-run variance** at temperature 0.2 — recommendation
  correctness ranged 84–92% across our executions.
- **Job URL loading is best-effort**: dynamic/JavaScript-rendered pages,
  login walls and anti-bot systems often yield no usable description —
  the UI then falls back to manual paste. Timeout, payload cap and an
  SSRF guard (no private/loopback/link-local targets) keep fetching
  polite and safe; no anti-bot bypass is attempted.
- **Nova Micro struggles with ambiguous requirements**: prose mentions
  ("you will work with Kubernetes") are sometimes classified as
  required instead of unknown, and items are occasionally dropped from
  explicit requirements lists. This is the dominant residual error mode.
- The alias map covers observed high-frequency variants only — it is
  not a complete skills ontology.
- Requirement classification is not perfect (68–88% strict
  all-buckets-exact across runs); the *recommendation* is more stable
  than the *classification* because normalization and policy absorb
  part of the noise.
- A recommendation is decision support, not a decision — candidates
  should still read the job posting.
- PDF parsing works for text-based PDFs; scanned/image-only PDFs are
  detected and rejected, not OCR'd.
- The AgentCore runtime is deployed and READY (v4) and remote invocation
  works (documented in `docs/deploy/agentcore.md`); the local CLI/API/UI
  remain the primary demo path.

## Roadmap

Versioned progress v0.1 → v1.0 lives in
[`docs/ROADMAP.md`](docs/ROADMAP.md). Post-hackathon ideas (job search,
ranking, resume adaptation, application tracking) are explicitly listed
there as *not built*.

## Hackathon

- Demo scenario & script: [`docs/DEMO.md`](docs/DEMO.md)
- Video script: [`docs/VIDEO_SCRIPT.md`](docs/VIDEO_SCRIPT.md)
- Devpost draft: [`docs/DEVPOST.md`](docs/DEVPOST.md)
- Required screenshots: [`docs/screenshots/`](docs/screenshots/) — to be
  captured from the running app (none are fabricated)

## License

Apache-2.0 — see [LICENSE](LICENSE).
