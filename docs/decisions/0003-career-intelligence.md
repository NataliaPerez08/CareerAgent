# ADR-0003: Career intelligence — tools como workflow, severidad y validación en código (v0.4)

## Estado

Accepted

## Contexto

v0.3 era un matcher: score, skills y recomendación. AGENTS.md v0.4 exige
convertirlo en un career agent con tools independientes
(`analyze_job`, `normalize_skills`, `calculate_match`,
`identify_skill_gaps`, `generate_interview_plan`) usadas como workflow —
no una mega-tool — y ampliar el output con `strengths`, `skill_gaps`,
`interview_topics` y `preparation_plan`. La regla estructural se
mantiene: el LLM interpreta, el código decide.

## Decisión

**Separación estricta de responsabilidades por campo:**

- `strengths`: 100% determinista (`app/career.py::build_strengths`).
  Solo afirma hechos derivados del match (cobertura de requeridos,
  experiencia explícita cumplida, cobertura de mandatorios). El LLM
  nunca redacta strengths: es la superficie más fácil de alucinar.
- `skill_gaps`: qué falta y con qué severidad es 100% determinista
  (`build_skill_gaps`: critical > required > preferred; un skill
  crítico faltante se reporta una sola vez con la severidad mayor).
- `interview_topics` y `preparation_steps`: contenido de dominio → el
  LLM los redacta (paso `generate_career_plan`, salida Pydantic
  `CareerPlan`), pero el código valida: solo se aceptan steps para
  skills que son gaps reales (`attach_preparation_steps`), dedupe
  case-insensitive, límites de tamaño (10 temas, 8 steps por skill).
- `preparation_plan`: aplanado determinista de los gaps ya validados,
  ordenado por severidad.

**Dos superficies, un mismo core:**

1. Agente Strands (`build_agent`): 5 tools registradas; el system
   prompt prescribe el orden del workflow. Verificado con Nova Micro:
   invoca las 5 tools en orden en una sola ejecución.
2. Pipeline estructurado (`evaluate_candidate`): el contrato de
   producto llama a los mismos cores deterministas
   (`normalize_requirements`, `build_match_result`, `build_skill_gaps`)
   y añade un paso LLM de plan con validación posterior.

**`normalize_requirements` (core de `analyze_job`)**: clasifica y
deduplica requerimientos extraídos — alias unificados, critical implica
required, requerido gana sobre preferido, lo ya clasificado sale de
`unknown`. Se aplica en el pipeline tras la extracción y dentro de
`build_match_result` (idempotente, defensa en profundidad).

**Errores observados con Nova Micro y su corrección en orden
prompt → normalización (sin cambiar de modelo):**

1. `<thinking>` filtrado en texto libre → `clean_reasoning` strip
   determinista (aplicado a explicación y chat).
2. Skills extraídas con palabras de contexto ("AWS experience",
   "ci/cd familiarity") → `normalize_skill` elimina prefijos/sufijos de
   contexto + ejemplos canónicos en el prompt de extracción.
3. "Requirements:" marcado como crítico → prompt aclara que crítico
   requiere lenguaje explícito ("must have", "mandatory",
   "non-negotiable").

**`research_company`**: deferred. Requiere fetch web externo; no aporta
al core de decisión y agregaría una dependencia frágil al MVP.

## Consecuencias

- `EvaluationResult` crece con 4 campos nuevos con defaults: contrato
  backwards-compatible para CLI/API/tests existentes.
- El modo `--chat` (opt-in) expone el loop libre del agente para demo
  del workflow de tools; el contrato principal sigue siendo el
  pipeline estructurado.
- Los steps de preparación para skills que no son gaps se descartan
  en silencio: preparar algo que no falta no está fundamentado en el
  match.
- La severidad jamás proviene del LLM, ni en tools ni en pipeline.
