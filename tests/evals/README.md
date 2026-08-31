# CareerAgent Eval Suite

Medición objetiva del comportamiento de CareerAgent (v0.9). Dos tiers
separados por diseño, siguiendo la política de costos del proyecto:

## Tiers

### Deterministic (`make eval`)

Sin llamadas al LLM, gratuito y 100% reproducible. Verifica que el
pipeline determinista (`normalize_requirements` → `build_match_result`
→ `decide_recommendation` → `validate_evidence`) produce exactamente el
resultado dorado (`gold.expected`) de cada caso:

- **Correct recommendation**: `decide_recommendation` == esperado.
- **Match exactness**: score, matched/missing skills (los 5 conjuntos)
  y `experience_match` exactos.
- **Requirement classification**: `critical_skills` y
  `unknown_requirements` normalizados exactos.
- **Evidence grounding**: toda la evidencia dorada se conserva y todos
  los `hallucination_probes` (citas plausibles pero ausentes del CV)
  se descartan. `Evidence hallucination = 0` es el target crítico.

### LLM (`make eval-llm`, requiere credenciales AWS)

Ejecuta la extracción real contra Amazon Bedrock (Nova Micro) y mide
el comportamiento del modelo:

- **Skill extraction**: recall y precision contra las skills doradas
  (normalizadas).
- **Years extraction**: años extraídos == años dorados (incluye null).
- **Requirement classification**: los 4 buckets exactos; cuenta
  statuses inventados (gold unknown/ausente clasificado como
  required/preferred/critical) y demoted (gold required clasificado
  como unknown).
- **Recommendation correctness**: end-to-end (extracción → matching →
  política) vs esperado.
- **Evidence hallucination**: items de evidencia en el output que no
  aparecen verbatim en el CV. Target crítico: 0.
- **Tool invocation**: runs del agent loop completo
  (`AGENT_WORKFLOW_PROMPT`) verificando que las 5 tools del workflow
  se invocan. Sampleo de N casos (default 3) por costo.

El runner sólo reporta métricas efectivamente ejecutadas. Si no hay
credenciales, el tier LLM se reporta como `NOT RUN` (exit 1 si se pidió
explícitamente).

## Dataset

`dataset.json` — 25 casos, 8 categorías (3-4 casos cada una):

| Categoría | Casos | Qué verifica |
|---|---|---|
| `strong_match` | 4 | APPLY 100 con aliases, preferred matcheado, sin gate de experiencia |
| `weak_match` | 3 | MAYBE por cobertura parcial (50-60%), gate cumplido o ausente |
| `missing_required` | 3 | 1 missing → aún APPLY (75); 2+ missing → MAYBE |
| `missing_preferred` | 3 | preferred faltantes nunca bloquean APPLY |
| `junior_vs_senior` | 3 | gate de años: False degrada a MAYBE; null NO degrada |
| `ambiguous_requirement` | 3 | menciones de stack sin lenguaje explícito → unknown, no diluyen score |
| `skill_alias` | 3 | `postgres/postgresql`, `rest api development/design and integration/apis`, context words |
| `irrelevant_experience` | 3 | experiencia profunda pero sin solape → SKIP 0 |

### Schema por caso

```text
case_id, category, resume, job_description, notes
gold.profile            skills (formas superficie), years_of_experience, evidence (verbatim)
gold.requirements       RAW como lo extraería el LLM (variantes, duplicados, context words)
gold.expected           recommendation, score, 5 conjuntos de skills, critical_skills,
                        unknown_requirements, experience_match
gold.hallucination_probes  citas plausibles que NO están en el CV
```

Cada caso es auto-contenido: el resume/job se redactaron para que la
evidencia dorada sea verbatim y los probes estén ausentes (verificado
por `tests/test_evals.py`).

## Uso

```bash
make eval                    # deterministic, gratis, reproducible
make eval-llm                # LLM tier completo (50+ llamadas Bedrock)
python scripts/run_evals.py --tier llm --cases 5 --tools-sample 1   # subset barato
python scripts/run_evals.py --tier all
```

El reporte se imprime y se escribe en `dist/evals/report.md` (ignorado
por git). Exit code 1 si el tier ejecutado no cumple sus targets.

`make test` **nunca** ejecuta el tier LLM (el default del runner es
`--tier deterministic`; el tier determinista corre dentro de
`tests/test_evals.py` como tests normales).
