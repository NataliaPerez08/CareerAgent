# Devpost Submission Draft

Borrador para la submission. **No contiene premios, usuarios, métricas
de negocio ni deployments inventados** — sólo lo efectivamente
construido y verificado.

## Project name

CareerAgent

## Tagline

Should you apply? Get an evidence-based answer, not generic advice.

## Inspiration

Job descriptions are noisy. Junior candidates in particular struggle
to tell whether they are genuinely underqualified or just missing one
or two non-critical requirements. Generic career chatbots make this
worse: they produce plausible-sounding advice that isn't anchored to
the actual resume, so candidates still can't tell what they're really
missing. We wanted an evaluator that only says what the resume can
prove.

## What it does

CareerAgent takes a resume (text or PDF) and a job description, and
returns a structured evaluation:

- an APPLY / MAYBE / SKIP recommendation with a match score;
- matched skills, each backed by verbatim evidence quoted from the
  resume (validated by code — invented evidence is dropped);
- missing requirements split by severity (critical / required /
  preferred) and requirements whose status the job description leaves
  ambiguous (kept as *unknown*, never guessed);
- a skill-gap preparation plan and concrete interview topics.

It is exposed as a CLI, a FastAPI service with a web UI, and an
evaluation history persisted in PostgreSQL. The same evaluation core
can run on AWS Bedrock AgentCore Runtime.

## How we built it

- **Strands Agents SDK** agent on **Amazon Bedrock** with **Amazon
  Nova Micro** (the cheapest Bedrock model) for extraction and
  explanation.
- A strictly deterministic core: skill normalization with an alias
  map, requirement classification rules, match scoring, and a
  centralized APPLY/MAYBE/SKIP policy — all in plain Python, never in
  the LLM.
- The agent works through five tools (job analysis, skill
  normalization, match calculation, gap analysis, interview planning)
  so the workflow is inspectable and each step is testable.
- Pydantic schemas as the single evaluation contract end to end.
- FastAPI + vanilla-JS UI + SQLAlchemy/Alembic + PostgreSQL (SQLite
  locally by default); Docker Compose for the full stack.
- A two-tier evaluation suite: a deterministic tier (25 gold-labeled
  cases, runs free in CI) and an LLM tier (real Bedrock extraction,
  run explicitly).

**LLM interprets. Code decides. Evals verify.**

## Challenges we ran into

- Nova Micro attached context words to skills ("AWS experience" ≠ a
  new skill) and emitted variants like `cicd`/`cpp` — we fixed this in
  a deterministic alias layer instead of upgrading the model.
- Getting the model to stop inventing requirement statuses: the fix
  was prompt rules ("when in doubt, unknown") plus a code-level
  requirement classifier, not a bigger model.
- A prompt example we added leaked into model outputs as a fake
  requirement — the eval suite caught it and we removed it.
- Measuring ourselves honestly: we built the eval suite *before*
  claiming reliability numbers.

## Accomplishments that we're proud of

- **Zero fabricated evidence** in the final eval run: every evidence
  item returned is verbatim-validated against the resume in code.
- 25-case / 8-category eval suite with a fully reproducible
  deterministic tier (100% on all four metrics) and a real LLM tier:
  92% recommendation correctness with the cheapest Nova model.
- The whole recommendation, score and severity logic is deterministic
  and centralized — the model can't quietly change the business rules.

## What we learned

- Small models + deterministic guardrails beat big models + trust.
- Evals change how you prompt: once hallucination is measured, every
  prompt edit becomes a hypothesis test.
- Prompt examples can leak into outputs — show, don't quote.

## What's next

- Post-hackathon ideas are tracked in `docs/ROADMAP.md`: job-search
  and job-ranking agents upstream of CareerAgent, resume adaptation,
  application tracking with human approval. None of it is claimed as
  built.

## Built with

Python, Strands Agents SDK, Amazon Bedrock, Amazon Nova, FastAPI,
PostgreSQL, SQLAlchemy, Alembic, Docker, Nix, pytest.

(AgentCore runtime support is implemented and documented; a live runtime is
deployed and READY (v4), and remote invocation works — see
`docs/deploy/agentcore.md`.)
