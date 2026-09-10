# CareerAgent Demo

Reproducible demo scenario, target **< 3 minutes** for the core.
Status: **DEMO FREEZE (Day 10 of the sprint)** — this document and the
app are frozen; no new features are added from here on.

## Setup (before recording)

```bash
cp .env.example .env           # adjust AWS_REGION if needed
make dev                       # or: python -m pip install -e '.[dev]'
make run                       # opens http://127.0.0.1:8000/
```

Requirements: AWS credentials with access to Bedrock (Nova Micro).
All the demo material is in:

```text
examples/demo_resume.txt   demo candidate CV
examples/demo_job.txt      demo job posting
```

Both texts are also embedded in the **Load example** button in the UI,
so the demo is one click (no typing or file uploads required).

## Expected result (verified)

```text
Recommendation:  APPLY
Score:           80  (4/5 required skills)
Matched:         python, rest api, postgresql, docker
Missing required: aws          ← the gap with a preparation plan
Missing preferred: ci/cd, kubernetes
Experience:      2 >= 2 years  ✓
Evidence:        5 verbatim quotes from the CV
```

The demo is deliberately **not 100%**: the candidate is a strong fit
with one concrete gap (AWS). That shows the real value of the product —
evidence, gaps and preparation, not an "all good".

## Script (timeline) — core < 3 minutes

```text
00:00  Problem: job postings are noisy; it's hard to know if you're
       a real fit or just missing one non-critical skill.
00:15  Open the UI (http://127.0.0.1:8000/) — two inputs: CV and job.
00:30  Click "Load example" (loads demo CV + job).
00:40  Click "Analyze".
       → the UI shows real stage-by-stage progress (SSE): CV reading,
         requirement extraction, deterministic matching, preparation.
01:20  Result: APPLY badge + score ring 80.
01:40  Evidence: each skill matches a literal quote from the CV
       (nothing invented).
02:00  Skill gaps by severity: aws (required), ci/cd and kubernetes
       (preferred), with preparation steps.
02:20  Interview topics + preparation plan for the gap.
02:40  History: the result was saved and reopens with one click.
02:50  Closing: "the LLM interprets, the code decides, the evals
       verify".
```

### Optional if time remains (30 s more)

```text
Batch ranking: paste 2-3 job URLs → quick deterministic ranking
→ click a row → deep analysis of that job.
```

## Freeze checklist (Day 10)

- [x] No new features: only verification and this document
- [x] Demo inputs verified (`examples/demo_*` + "Load example")
- [x] URL flow: "Load job" from a public URL (no fragile scraping;
      fallback to manual paste documented)
- [x] SSE progress + explicit timeout (504) if the model hangs
- [x] History: listing + reopen saved evaluation
- [x] Fallback plan: if Bedrock returns slow responses (documented
      60 s+ degradation), the demo is narrated anyway: explain the
      architecture while the pipeline runs

## Alternative CLI demo (no UI)

```bash
python -m app.cli                    # uses examples/demo_* by default → structured JSON
python -m app.cli --chat             # Strands agent with the 5-tool workflow
```

## Note on timings

A full evaluation (3 Nova Micro calls, no tools) takes ~15-60 s
depending on the region and service health. Saving is best-effort on
each request. In the demo, narrate the architecture while the pipeline
runs (the UI shows real stage-by-stage progress, not a dead spinner).
