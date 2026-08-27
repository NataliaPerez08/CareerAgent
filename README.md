# CareerAgent

CareerAgent is an early prototype for the **Agents for Humans Hackathon**. It helps early-career software engineers evaluate whether a job is worth pursuing by comparing evidence in a resume against a job description.

The first version deliberately stays small: one Strands agent, one deterministic matching tool, a CLI example, and a FastAPI endpoint.

## Architecture

```text
Resume + Job Description
          |
          v
   Strands CareerAgent
          |
          +----> calculate_match tool
          |
          v
 APPLY / MAYBE / SKIP
   + explanation
```

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

The CLI loads `examples/resume.txt` and `examples/job.txt` and asks the Strands agent to evaluate the match.

## Run the API

```bash
make run
```

Then open the generated FastAPI docs at:

```text
http://127.0.0.1:8000/docs
```

Example request:

```bash
curl -X POST http://127.0.0.1:8000/evaluate \
  -H 'content-type: application/json' \
  -d '{
    "resume": "Backend developer with 2 years of Python, REST APIs, PostgreSQL and Docker experience.",
    "job_description": "Junior backend engineer. Requires Python, REST APIs, PostgreSQL and Docker. AWS preferred."
  }'
```

## Docker

```bash
make docker-build
make docker-run
```

For actual Bedrock calls from Docker, pass AWS credentials using an appropriate mechanism for your environment rather than baking them into the image.

## Roadmap

### v0.1 — vertical slice
- [x] Strands agent
- [x] Deterministic skill matching tool
- [x] CLI
- [x] FastAPI endpoint
- [x] Tests

### v0.2 — structured evidence
- [ ] Structured extraction of required vs preferred skills
- [ ] Experience requirement matching
- [ ] JSON/structured agent output
- [ ] Better skill normalization and aliases

### v0.3 — real inputs
- [ ] PDF resume parser
- [ ] Job URL ingestion
- [ ] Evidence-backed gap analysis

### v0.4 — product
- [ ] Minimal web UI
- [ ] Interview preparation tool
- [ ] Company research tool

### v0.5 — hackathon deployment
- [ ] Bedrock AgentCore deployment
- [ ] Observability/tracing
- [ ] Evaluation suite
- [ ] Architecture diagram
- [ ] Public demo
- [ ] Devpost submission material

## Design principle

The LLM interprets ambiguous language; deterministic code handles calculations and facts whenever possible. CareerAgent must never invent skills or experience that are absent from the resume.

## License

Apache-2.0. Add the full license text before publishing the hackathon submission.
