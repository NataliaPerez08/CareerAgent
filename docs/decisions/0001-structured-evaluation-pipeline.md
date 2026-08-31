# ADR-0001: Pipeline estructurado de evaluación (v0.2)

## Estado

Accepted

## Contexto

En v0.1 el contrato principal era texto libre producido por el agente Strands:
el score y la recomendación dependían de lo que el LLM dijera tras invocar
`calculate_match`. Esto hacía imposible garantizar el principio "el LLM
interpreta; el código decide" y exponía el sistema a alucinaciones
(score inventado, requisitos reclasificados, experiencia no evidenciada).

## Decisión

Reemplazar el texto libre por un pipeline de tres etapas:

1. **Extracción LLM estructurada**: `structured_output_model` de Strands
   (tool-forcing de Bedrock) produce `CandidateProfile` y `JobRequirements`
   validados por Pydantic. Requisitos ambiguos van a `unknown_requirements`;
   nunca se infiere categoría sin evidencia explícita en la vacante.
2. **Matching determinista**: `build_match_result` (código puro) calcula
   score, matched/missing y `experience_match`; `decide_recommendation`
   aplica la política centralizada (`app/policy.py`). Los críticos cuentan
   como requeridos; los unknown nunca puntúan.
3. **Explicación LLM**: el LLM redacta el `reasoning` a partir del resultado
   ya computado, prohibido contradecirlo o recomputarlo.

Decisiones complementarias:

- **Agente fresco por paso LLM**: evita contaminación cruzada entre
  extracciones (el resume no puede filtrarse en la extracción de la vacante)
  y estado compartido entre evaluaciones.
- **Núcleo compartido**: `calculate_match` (tool) y el pipeline llaman al
  mismo `build_match_result` + `decide_recommendation`. Una sola fuente de
  verdad para el cálculo.
- **Evidencia validada verbatim**: toda cita de `evidence` que no aparezca
  literalmente en el resume se descarta (`validate_evidence`). Objetivo:
  experiencia alucinada = 0.

## Consecuencias

- El score y la recomendación son 100% deterministas y testeables sin LLM.
- Cada evaluación cuesta 3 llamadas a Nova Micro (antes 1); aceptable por
  el bajo costo del modelo y la ganancia en confiabilidad.
- `evaluate_candidate` pasa de devolver `str` a `EvaluationResult`;
  consumidores (CLI, API) migrados simultáneamente.
- La tool `calculate_match` conserva su rol para el flujo conversacional
  del agente y futuras fases (v0.4).
