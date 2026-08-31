# CareerAgent

CareerAgent is an early prototype for the **Agents for Humans Hackathon**. It helps early-career software engineers evaluate whether a job is worth pursuing by comparing evidence in a resume against a job description, and tells them how to prepare for it.

## Architecture

```text
Resume ──> LLM extraction ──> CandidateProfile (Pydantic)
Job    ──> LLM extraction ──> JobRequirements (Pydantic)
                   |
                   v
       Job analysis (analyze_job core: normalize, classify, dedupe)
                   |
                   v
       Deterministic matching (calculate_match core)
       skill aliases, score, evidence validation
                   |
                   v
       APPLY / MAYBE / SKIP policy (centralized thresholds)
                   |
                   v
       Gap analysis (identify_skill_gaps core: severity ranking)
                   |
                   v
       LLM career plan draft ──> code validation (generate_interview_plan core)
                   |
                   v
       LLM explanation ──> EvaluationResult (JSON)
```

The LLM only extracts, drafts preparation content, and explains. Scores, thresholds, recommendations, gap severity, strengths, and the final validation of every drafted step are always computed by deterministic code. Any "evidence" quote that does not appear verbatim in the resume is dropped, and preparation steps are only accepted for skills that are actually missing.

The same cores power the Strands agent tool workflow:

```text
Agent
 ├── analyze_job
 ├── normalize_skills
 ├── calculate_match
 ├── identify_skill_gaps
 └── generate_interview_plan
```

## Stack

- Python 3.11+
- Strands Agents SDK
- Amazon Bedrock (default Strands model provider)
- FastAPI
- SQLAlchemy 2.0 + Alembic (SQLite for local dev, PostgreSQL for docker compose)
- pytest
- Ruff
- Docker
- Nix Flake

## Requirements

You need Python 3.11+ and, to invoke the agent through the default model provider, AWS credentials with access to Amazon Bedrock.

Configure AWS with your preferred secure mechanism, for example:

```bash
aws configure
```

Do **not** commit AWS keys to this repository.

## Local setup

### With Nix

```bash
nix develop
python -m venv .venv
source .venv/bin/activate
make dev
```

### Without Nix

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
make dev
```

## Verify the deterministic layer first

The matching tool and API health endpoint do not require an LLM call:

```bash
make test
```

## Run the CLI agent

After AWS/Bedrock is configured:

```bash
make cli
```

The CLI loads `examples/resume.txt` and `examples/job.txt` by default. It also accepts real resume files (PDF or TXT):

```bash
python -m app.cli path/to/resume.pdf path/to/job.txt
```

To demo the Strands agent running the five-tool workflow in its free loop (opt-in; the structured pipeline above remains the main contract):

```bash
python -m app.cli --chat
```

Resume files are validated before parsing: supported formats (`.pdf`, `.txt`), maximum size (`RESUME_MAX_SIZE_MB`, default 5 MB), empty and corrupt files are rejected, and image-only/scanned PDFs are reported instead of silently producing garbage.

## Run the web UI

The fastest way to use CareerAgent — no CLI needed:

```bash
make run
```

Then open:

```text
http://127.0.0.1:8000/
```

The flow is four steps: paste your resume (or upload a PDF/TXT), paste the job description, press **Analyze**, and read the result. A **Load example** button fills both inputs for an instant demo (the full evaluation takes ~30–60 seconds). The result shows the recommendation (`APPLY` / `MAYBE` / `SKIP`), match score, matched and missing skills grouped by severity, resume evidence, skill gaps with concrete preparation steps, interview topics, and the reasoning behind the verdict.

## Run the API

```bash
make run
```

Then open the generated FastAPI docs at:

```text
http://127.0.0.1:8000/docs
```

The stable API lives under `/api/v1`. Text request (`POST /api/v1/evaluations`):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evaluations \
  -H 'content-type: application/json' \
  -d '{
    "resume_text": "Backend developer with 2 years of Python, REST APIs, PostgreSQL and Docker experience.",
    "job_description": "Junior backend engineer. Requires Python, REST APIs, PostgreSQL and Docker. AWS preferred."
  }'
```

Or upload a resume file directly (PDF/TXT, multipart, `POST /api/v1/evaluations/upload`):

```bash
curl -X POST http://127.0.0.1:8000/api/v1/evaluations/upload \
  -F 'resume=@cv.pdf' \
  -F 'job_description=Junior backend engineer. Requires Python, REST APIs, PostgreSQL and Docker.'
```

Errors are explicit and logged: `422` invalid payload, empty resume/job, or unreadable text, `413` too large, `415` unsupported format, `502` model/agent failure.

Every evaluation is persisted. The response is a structured `EvaluationResult` plus the storage metadata (`id`, `created_at`, `job_title`):

```json
{
  "recommendation": "APPLY",
  "score": 100,
  "matched_skills": ["docker", "postgresql", "python", "rest api"],
  "matched_preferred_skills": [],
  "missing_required_skills": [],
  "missing_preferred_skills": ["aws"],
  "missing_critical_skills": [],
  "unknown_requirements": [],
  "experience_match": true,
  "evidence": ["2 years of Python, REST APIs, PostgreSQL and Docker experience."],
  "strengths": [
    "Meets 4 of 4 required skills: docker, postgresql, python, rest api",
    "Experience requirement met: 2 years"
  ],
  "skill_gaps": [
    {
      "skill": "aws",
      "severity": "preferred",
      "preparation_steps": ["IAM fundamentals", "S3", "Lambda", "API Gateway"]
    }
  ],
  "interview_topics": ["PostgreSQL indexes", "REST design", "Docker networking"],
  "preparation_plan": ["aws: IAM fundamentals", "aws: S3", "aws: Lambda", "aws: API Gateway"],
  "reasoning": "..."
}
```

Strengths and gap severity are always computed by deterministic code; the LLM only drafts the preparation content, which code then validates (steps for skills that are not actually missing are dropped).

## Persistence

Every evaluation is stored with its candidate, resume and job (`Candidate → Resume`, `Resume + Job → Evaluation`), including score, recommendation, skill lists, evidence, gaps and timestamps. Internal prompts are never stored.

Storage is selected with `DATABASE_URL` (`app/db.py`):

```env
DATABASE_URL=sqlite:///./careeragent.db                                  # default, zero-config
DATABASE_URL=postgresql+psycopg://careeragent:careeragent@localhost:5432/careeragent
```

The schema is owned by Alembic (`app/migrations/`). Pending migrations are applied automatically on API startup, or explicitly:

```bash
make migrate
```

Past evaluations are recoverable through the API:

```bash
curl http://127.0.0.1:8000/api/v1/evaluations          # recent history (newest first)
curl http://127.0.0.1:8000/api/v1/evaluations/1        # full stored evaluation
```

Persistence is best-effort per request: if storing fails after an evaluation succeeded, the result is still returned (without an `id`) and the failure is logged.

## Docker

```bash
make docker-build
make docker-run
```

For actual Bedrock calls from Docker, pass AWS credentials using an appropriate mechanism for your environment rather than baking them into the image.

Full stack with PostgreSQL (migrations run on boot, data survives restarts via the `pgdata` volume):

```bash
make compose-up     # API on http://127.0.0.1:8000, Postgres on localhost:5432
make compose-down
```

## Roadmap

The versioned roadmap (v0.1 → v1.0) lives in [docs/ROADMAP.md](docs/ROADMAP.md).
Progress is tracked there; only one version is `IN PROGRESS` at a time.

## Design principle

The LLM interprets ambiguous language; deterministic code handles calculations and facts whenever possible. CareerAgent must never invent skills or experience that are absent from the resume.

Skill names are normalized deterministically before comparison: lowercased, whitespace-collapsed, unified through a small alias map (`postgres` → `postgresql`, and `rest apis`, `rest api development`, `rest api design and integration` → `rest api`), and stripped of context words models tend to attach (`AWS experience` → `aws`, `Familiarity with CI/CD` → `ci/cd`), so equivalent variants from the resume and the job description are treated as the same skill.

## License

Apache-2.0. Add the full license text before publishing the hackathon submission.
