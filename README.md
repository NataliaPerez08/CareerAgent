# CareerAgent

CareerAgent is an early prototype for the **Agents for Humans Hackathon**. It helps early-career software engineers evaluate whether a job is worth pursuing by comparing evidence in a resume against a job description.

The first version deliberately stays small: one Strands agent, one deterministic matching core, a CLI example, and a FastAPI endpoint.

## Architecture

```text
Resume ──> LLM extraction ──> CandidateProfile (Pydantic)
Job    ──> LLM extraction ──> JobRequirements (Pydantic)
                  |
                  v
      Deterministic matching (pure code)
      skill aliases, score, evidence validation
                  |
                  v
      APPLY / MAYBE / SKIP policy (centralized thresholds)
                  |
                  v
      LLM explanation ──> EvaluationResult (JSON)
```

The LLM only extracts and explains. Scores, thresholds, and the recommendation are always computed by deterministic code, and any "evidence" quote that does not appear verbatim in the resume is dropped.

## Stack

- Python 3.11+
- Strands Agents SDK
- Amazon Bedrock (default Strands model provider)
- FastAPI
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

Resume files are validated before parsing: supported formats (`.pdf`, `.txt`), maximum size (`RESUME_MAX_SIZE_MB`, default 5 MB), empty and corrupt files are rejected, and image-only/scanned PDFs are reported instead of silently producing garbage.

## Run the API

```bash
make run
```

Then open the generated FastAPI docs at:

```text
http://127.0.0.1:8000/docs
```

Text request:

```bash
curl -X POST http://127.0.0.1:8000/evaluate \
  -H 'content-type: application/json' \
  -d '{
    "resume": "Backend developer with 2 years of Python, REST APIs, PostgreSQL and Docker experience.",
    "job_description": "Junior backend engineer. Requires Python, REST APIs, PostgreSQL and Docker. AWS preferred."
  }'
```

Or upload a resume file directly (PDF/TXT, multipart):

```bash
curl -X POST http://127.0.0.1:8000/evaluate/upload \
  -F 'resume=@cv.pdf' \
  -F 'job_description=Junior backend engineer. Requires Python, REST APIs, PostgreSQL and Docker.'
```

Upload errors are explicit: `413` too large, `415` unsupported format, `422` empty/corrupt/unreadable text.

The response is a structured `EvaluationResult`:

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
  "reasoning": "..."
}
```

## Docker

```bash
make docker-build
make docker-run
```

For actual Bedrock calls from Docker, pass AWS credentials using an appropriate mechanism for your environment rather than baking them into the image.

## Roadmap

The versioned roadmap (v0.1 → v1.0) lives in [docs/ROADMAP.md](docs/ROADMAP.md).
Progress is tracked there; only one version is `IN PROGRESS` at a time.

## Design principle

The LLM interprets ambiguous language; deterministic code handles calculations and facts whenever possible. CareerAgent must never invent skills or experience that are absent from the resume.

Skill names are normalized deterministically before comparison: lowercased, whitespace-collapsed, and unified through a small alias map (`postgres` → `postgresql`, and `rest apis`, `rest api development`, `rest api design and integration` → `rest api`), so equivalent variants from the resume and the job description are treated as the same skill.

## License

Apache-2.0. Add the full license text before publishing the hackathon submission.
