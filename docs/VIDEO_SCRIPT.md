# CareerAgent — Video Script (hackathon)

Target duration: 3-4 minutes. Most of it should show the product
working; setup is not explained in the video.

## 1. Intro — the problem (0:00-0:30)

> "Job descriptions are noisy. When you read a job posting, it's hard
> to know whether you're really underqualified or just missing one
> non-critical skill. Generic CV chatbots don't solve this: they
> invent advice, they don't work with evidence.
>
> CareerAgent evaluates a candidate against a job posting using
> literal evidence from the CV — and nothing but that evidence."

## 2. Product demo (0:30-2:00)

Follow `docs/DEMO.md` (UI at http://127.0.0.1:8000/):

1. Load example → Analyze.
2. Show the result while it loads: narrate what happens behind the
   scenes (LLM extraction → deterministic matching).
3. Result: **APPLY, 80** — walk through on screen:
   - matched skills with verbatim evidence;
   - missing required: **aws** — "the system doesn't tell you 'apply
     to everything', it tells you exactly what you're missing";
   - preparation plan to close the gap;
   - interview topics.

Key line: "every claim in the response is anchored to a quote from the
CV. If there is no evidence, the system says *unknown* — it never
invents anything."

## 3. Technical architecture (2:00-2:45)

Diagram on a slide (the same one as in the README):

> "The design principle: **the LLM interprets, the code decides, the
> evals verify.**
>
> The LLM (Amazon Nova Micro via Bedrock, with the Strands Agents SDK)
> only does what an LLM should do: extract structure from ambiguous
> text and write the explanation. The score, the thresholds, the gap
> severity and the APPLY/MAYBE/SKIP recommendation are 100%
> deterministic — a centralized policy module, not the model's
> opinion."

Mention the agent's 5 tools (analyze_job, normalize_skills,
calculate_match, identify_skill_gaps, generate_interview_plan) and the
separation between FastAPI/UI/local PostgreSQL and the reusable core.

## 4. Reliability — evals (2:45-3:15)

> "How do we know it doesn't hallucinate? We run an eval suite of 25
> cases across 8 categories: fabricated evidence retained — zero, in
> every case. Correct recommendation: 92% with the cheapest Bedrock
> model. And the deterministic tier is 100% reproducible and runs for
> free in CI."

Show `dist/evals/report.md` or the results block from the README.

## 5. Impact and closing (3:15-3:40)

> "For a junior looking for their first job, this turns an anxious,
> opaque decision into an evidence-based evaluation: where you're
> strong, exactly what you're missing, and how to prepare it before
> the interview."

Closing: repo + stack on screen.

---

## Recording checklist

- [ ] Terminal/HTTP with the app already running (don't install on video)
- [ ] `make eval` run beforehand so the report is fresh
- [ ] Browser in a clean window, readable zoom
- [ ] Don't show credentials or `.env`
- [ ] Capture at 1080p+; the score ring and the evidence list must be readable
