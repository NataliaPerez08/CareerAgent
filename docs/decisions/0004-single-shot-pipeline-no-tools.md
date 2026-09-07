# ADR-0004: Una evaluación = 3 llamadas al modelo, sin tools en el pipeline (Día 2 del sprint)

## Estado

Accepted

## Contexto

El benchmark del Día 1 midió 4 invocaciones al modelo por evaluación
(perfil, requirements, career plan y explicación), cada una con las 5
tools del agente Strands adjuntas. Las tools (destinadas a demo de
workflow) no hacen nada en el pipeline estructurado: todo el cálculo
es determinista en Python. Cada adjunto engrosa prompts y contexto, y
con tools presentes el runtime del agente no garantiza un solo ciclo —
un modelo podría entrar en un loop de herramientas.

## Decisión

- **Fusionar plan y explicación en una sola llamada** `draft_career_plan`
  (etapa `plan_and_explanation`, salida Pydantic `CareerPlan` con
  `reasoning`). La explicación ya era un texto derivado del resultado
  determinista; fusionarla elimina una invocación sin perder contenido.
  `EXPLANATION_PROMPT` y `explain_evaluation` se eliminan.
- **El pipeline usa un agente sin tools** (`build_pipeline_agent`,
  `PIPELINE_SYSTEM_PROMPT`): extracción estructurada single-shot con
  tolerancia de parseo y sin instrucción de workflow. Sin tools, no
  puede haber loop de herramientas. La fallback de RawOutput se
  conserva para el parseo estructurado.
- **`build_agent()` no cambia**: 5 tools registradas para el modo
  `--chat` (demo) y para la métrica de invocación de tools de los evals
  LLM. Las superficies distintas comparten `_build_model()` (misma
  configuración de Bedrock) y los mismos cores deterministas.
- **Contadores de loop** en `EvaluationTimings`: `llm_calls`,
  `llm_cycles` (round-trips reales del modelo, leídos de
  `result.metrics.cycle_count`), `tool_calls` (suma de
  `tool_metrics[*].call_count` **excluyendo la pseudo-tool del schema
  estructurado** — Strands la registra con el nombre de la clase, p. ej.
  `CandidateProfile`, y no es una tool del agente), `input_tokens`/
  `output_tokens` (`accumulated_usage`). Solo se reportan si existen
  métricas; nunca se inventan números mock. Verificado en vivo: 3 calls,
  3 cycles, 0 tool_calls con Nova Micro y Lite.

## Resultado medido

| | Día 1 | Día 2 |
|---|---|---|
| Llamadas al modelo | 4 | 3 |
| Tools adjuntas por llamada | 5 | 0 |
| Ciclos de modelo | ≥4 (no acotados) | 3 (garantizado) |
| Evals deterministas (25 casos) | 100% | 100%, 0 evidencia fabricada |

## Consecuencias

- Presupuesto de tokens por evaluación baja (una extracción menos +
  prompts sin catálogo de tools).
- El fallback libre (RawOutput) en el pipeline es ahora un error: los
  tests de `FakeAgent` lanzan `AssertionError` ante una llamada no
  estructurada (guard estructural).
- La demo de tools queda limitada a `--chat`; el flujo principal
  (CLI/API/UI) no enseña el workflow de 5 tools — compensado por la
  sección "Arquitectura" y el modo chat.