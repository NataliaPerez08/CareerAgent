# CareerAgent Roadmap

## Estado general

**Versión actual:** `v0.5`
**Estado:** `TODO`

CareerAgent se desarrollará de forma incremental. Cada versión debe quedar funcional, probada y documentada antes de avanzar a la siguiente.

---

## v0.1 — Vertical Slice del agente

**Estado:** `DONE`

### Objetivo

Construir el flujo mínimo funcional:

```text
Resume text
    +
Job description
    ↓
Strands Agent
    ↓
calculate_match()
    ↓
APPLY / MAYBE / SKIP
```

### Ya implementado

* [x] Strands Agent
* [x] Amazon Bedrock
* [x] Amazon Nova Micro
* [x] `calculate_match`
* [x] CLI
* [x] Ejemplo de CV
* [x] Ejemplo de vacante
* [x] Flujo agent → tool → response
* [x] Configuración de modelo por variables de entorno
* [x] Eliminar output duplicado del CLI (`callback_handler=None` en el Agent)
* [x] Normalizar aliases de skills (`postgres → postgresql`, `rest apis / rest api development / rest api design and integration → rest api`)
* [x] Tratar variantes como `REST APIs` y `REST API development`
* [x] Endurecer el system prompt (reglas explícitas anti-invención y anti-inferencia)
* [x] Evitar inferencias no soportadas sobre requisitos obligatorios/preferidos (regla en prompt)
* [x] Tests de aliases y regression test del caso real CV vs vacante
* [x] Verificar `make test` (8 passed)
* [x] Verificar `make cli` (una única respuesta, recomendación APPLY con match 100%)

### Definition of Done

* [x] `make test` pasa
* [x] `make cli` produce una única respuesta
* [x] La tool se invoca correctamente
* [x] No se inventan skills del candidato
* [x] El matching básico funciona con aliases
* [x] README actualizado

---

## v0.2 — Structured Evaluation

**Estado:** `DONE`

### Objetivo

Reemplazar el texto libre como contrato principal por resultados estructurados.

### Implementar

* [x] `CandidateProfile` (`app/schemas.py`)
* [x] `JobRequirements` (`app/schemas.py`)
* [x] `MatchResult` (`app/schemas.py`)
* [x] `EvaluationResult` (`app/schemas.py`)
* [x] Schemas Pydantic validados
* [x] `required_skills`
* [x] `preferred_skills`
* [x] `critical_skills`
* [x] `unknown_requirements` (nunca cuentan para el score)
* [x] Evidencia explícita proveniente del CV (validada verbatim contra el resume en `validate_evidence`)
* [x] Política determinista para `APPLY`, `MAYBE`, `SKIP` (`app/policy.py`, thresholds centralizados)
* [x] Pipeline: LLM extract → matching determinista → LLM explain (`app/service.py`)
* [x] API devuelve `EvaluationResult` estructurado

### Resultado esperado

```json
{
  "recommendation": "APPLY",
  "score": 85,
  "matched_skills": [
    "python",
    "postgresql",
    "rest api"
  ],
  "missing_required_skills": [
    "aws"
  ],
  "missing_preferred_skills": [],
  "experience_match": true,
  "evidence": [
    "2 years of backend development"
  ],
  "reasoning": "..."
}
```

### Tests

* [x] APPLY
* [x] MAYBE
* [x] SKIP
* [x] Preferred skill missing (no bloquea APPLY)
* [x] Required skill missing (baja score, no fuerza SKIP)
* [x] Critical skill missing (fuerza SKIP)
* [x] Requirement ambiguity (unknown_requirements no afectan score)
* [x] No hallucinated evidence (evidencia inventada se descarta)

### Definition of Done

* [x] Output validado mediante Pydantic
* [x] Recommendation calculada mediante reglas centralizadas
* [x] Tests pasan (42 passed)
* [x] CLI sigue funcionando (emite `EvaluationResult` JSON)

---

## v0.3 — Inputs reales

**Estado:** `DONE`

### Objetivo

Aceptar un CV real y una descripción de vacante.

### Implementar

* [x] Upload de PDF (`POST /evaluate/upload` multipart + CLI por argumento)
* [x] Extracción de texto (`app/resume_parser.py`, pypdf)
* [x] Limpieza del texto (`clean_text`: control chars, whitespace, párrafos)
* [x] Validación de archivos (extensión, magic bytes `%PDF`)
* [x] Tamaño máximo (`RESUME_MAX_SIZE_MB`, default 5 MB → HTTP 413)
* [x] Manejo de PDF inválido (corrupto → 422; escaneado/sin texto → 422 con mensaje explícito)
* [x] Interfaz multi-formato preparada para DOCX (dispatch por extensión en `parse_resume`)
* [x] Job description pegada como texto (contrato paste-first en CLI/API)
* [x] Interfaz preparada para futura URL de vacante (el input de vacante es texto plano; agregar URL no requiere cambios de interfaz)

### Opcional

* [ ] Extracción desde URL de vacante (deferred: scraping frágil/anti-bot fuera de alcance)

### Fuera de alcance inicialmente

* scraping masivo
* bypass anti-bot
* integración LinkedIn

### Definition of Done

* [x] PDF real puede convertirse en `CandidateProfile` (verificado end-to-end con Bedrock)
* [x] Vacante real puede convertirse en `JobRequirements`
* [x] La evaluación completa sigue funcionando (66 tests passed)

---

## v0.4 — Career Intelligence

**Estado:** `DONE`

### Objetivo

Convertir CareerAgent de matcher a asistente de decisión profesional.

### Tools

* [x] `analyze_job` (clasificación/normalización determinista de requerimientos)
* [x] `normalize_skills` (nombres canónicos para el agente)
* [x] `calculate_match` (existente, ahora parte del workflow de 5 tools)
* [x] `identify_skill_gaps` (gaps con severidad: critical > required > preferred)
* [x] `generate_interview_plan` (valida y ensambla el plan drafted por el agente)

### Opcional

* [ ] `research_company` (deferred: fetch web externo, fuera del core de decisión)

### Output adicional

* [x] strengths (100% determinista, derivados del match — nunca redactados por el LLM)
* [x] skill gaps con severidad y preparation steps (severidad siempre de código)
* [x] interview topics (LLM redacta, código deduplica/limita)
* [x] preparation plan (aplanado, ordenado por severidad)
* [x] explanation grounded in evidence (prompt extendido con strengths y gaps)

### Workflow verificado

```text
Agent
 ├── analyze_job
 ├── normalize_skills
 ├── calculate_match
 ├── identify_skill_gaps
 └── generate_interview_plan
```

Verificado con Nova Micro: el agente invoca las 5 tools en orden en una
sola ejecución (modo `--chat`).

### Correcciones de comportamiento del modelo (prompt/normalización, sin cambiar de modelo)

* [x] Strip determinista de bloques `<thinking>` filtrados (`clean_reasoning`)
* [x] Eliminación de palabras de contexto en skills ("AWS experience" → "aws")
* [x] "Requirements:" ya no se interpreta como crítico (crítico = lenguaje explícito)

### Definition of Done

* [x] El agente utiliza varias tools de forma coherente (5/5 en orden)
* [x] El workflow puede explicarse claramente en una demo (CLI `--chat` + pipeline)
* [x] Cada conclusión relevante tiene evidencia o estado `unknown`
* [x] Tests pasan (101 passed)
* [x] CLI/API verificados end-to-end con Bedrock

---

## v0.5 — API estable

**Estado:** `TODO`

### Objetivo

Exponer CareerAgent como servicio.

### Endpoints

```http
GET /health

POST /api/v1/evaluations
```

Posteriormente:

```http
GET /api/v1/evaluations/{id}
```

### Implementar

* [ ] FastAPI
* [ ] Request schemas
* [ ] Response schemas
* [ ] Error handling
* [ ] Logging
* [ ] Health endpoint
* [ ] OpenAPI
* [ ] Tests de integración

### Tests

* [ ] 200
* [ ] 422
* [ ] CV vacío
* [ ] Vacante vacía
* [ ] Error del modelo
* [ ] Input inválido

### Definition of Done

* [ ] API documentada en `/docs`
* [ ] Tests pasan
* [ ] Core desacoplado de HTTP

---

## v0.6 — Web UI

**Estado:** `TODO`

### Objetivo

Crear una demo visual sencilla.

### Flujo

```text
Upload CV
   ↓
Paste Job
   ↓
Analyze
   ↓
Results
```

### Mostrar

* [ ] Recommendation
* [ ] Match score
* [ ] Matched skills
* [ ] Missing skills
* [ ] Evidence
* [ ] Skill gaps
* [ ] Interview preparation

### Definition of Done

* [ ] Una evaluación puede hacerse sin CLI
* [ ] La demo principal tarda menos de 60 segundos
* [ ] No requiere conocimientos técnicos para utilizarla

---

## v0.7 — Persistencia

**Estado:** `TODO`

### Objetivo

Guardar evaluaciones e historial.

### Stack

* PostgreSQL
* Alembic

### Entidades

* [ ] Candidate
* [ ] Resume
* [ ] Job
* [ ] Evaluation

### Implementar

* [ ] Database layer
* [ ] Migrations
* [ ] Repository/service layer
* [ ] Evaluation history
* [ ] Timestamps

### Definition of Done

* [ ] Evaluaciones sobreviven al reinicio de la aplicación
* [ ] Migraciones reproducibles
* [ ] API permite recuperar evaluaciones guardadas

---

## v0.8 — AWS AgentCore

**Estado:** `TODO`

### Objetivo

Desplegar el agente usando servicios administrados de AWS.

### Implementar

* [ ] AgentCore Runtime
* [ ] Deployment configuration
* [ ] Observability
* [ ] Tracing
* [ ] Sessions si aportan valor

### Restricción

El core debe seguir funcionando localmente.

### Definition of Done

* [ ] Agent desplegado
* [ ] Demo remota funcional
* [ ] Tracing visible
* [ ] Documentación de deployment reproducible

---

## v0.9 — Agent Evaluations

**Estado:** `TODO`

### Objetivo

Medir objetivamente el comportamiento de CareerAgent.

### Dataset inicial

```text
tests/evals/
├── strong_match
├── weak_match
├── missing_required
├── missing_preferred
├── junior_vs_senior
├── ambiguous_requirement
├── skill_alias
└── irrelevant_experience
```

### Métricas

* [ ] Recommendation correctness
* [ ] Skill extraction accuracy
* [ ] Tool invocation
* [ ] Requirement classification
* [ ] Evidence grounding
* [ ] Hallucinated candidate experience

### Meta crítica

```text
Hallucinated candidate experience = 0
```

### Definition of Done

* [ ] Evals ejecutables por separado
* [ ] Resultados reproducibles
* [ ] Reporte generado automáticamente

---

# v1.0 — Hackathon Release

**Estado:** `TODO`

### Objetivo

Congelar funcionalidad y preparar la entrega.

No agregar grandes features en esta fase.

### Producto

* [ ] Flujo end-to-end estable
* [ ] UI funcional
* [ ] Deployment público
* [ ] Tests estables
* [ ] Eval report

### Documentación

* [ ] Problem
* [ ] Solution
* [ ] Architecture
* [ ] How it works
* [ ] Tech stack
* [ ] Local setup
* [ ] AWS setup
* [ ] Tests
* [ ] Docker
* [ ] Screenshots
* [ ] Eval results
* [ ] Limitations
* [ ] Future work

### Entrega hackathon

* [ ] GitHub público
* [ ] README final
* [ ] Licencia
* [ ] Architecture diagram
* [ ] Demo desplegada
* [ ] Video
* [ ] Submission Devpost

### Demo principal

```text
CV
 ↓
Job
 ↓
Analyze
 ↓
Recommendation
 ↓
Evidence
 ↓
Skill gaps
 ↓
Interview preparation
```

### Definition of Done

* [ ] Demo estable
* [ ] Video grabado
* [ ] Repositorio limpio
* [ ] Submission completa

---

# Post-hackathon

Las siguientes ideas quedan explícitamente fuera del MVP:

* búsqueda automática de vacantes
* ranking automático de múltiples empleos
* modificación automática del CV
* múltiples versiones del CV
* seguimiento de postulaciones
* auto-apply
* aprobación humana antes de aplicar
* agentes especializados múltiples
* integración con job boards
* integración con Gmail
* alertas de nuevas vacantes
* analytics de skills demandadas
* recomendaciones de aprendizaje basadas en mercado

Arquitectura futura posible:

```text
Job Search Agent
       ↓
Job Ranking Agent
       ↓
CareerAgent
       ↓
CV Adaptation Agent
       ↓
Human Approval
       ↓
Application Agent
```

---

# Regla de avance

Sólo una versión puede estar en estado:

```text
IN PROGRESS
```

Cuando una versión cumple su Definition of Done:

```text
IN PROGRESS → DONE
```

y únicamente entonces la siguiente pasa:

```text
TODO → IN PROGRESS
```

Estados permitidos:

```text
TODO
IN PROGRESS
BLOCKED
DONE
```

---

# Progreso

```text
v0.1  ██████████  DONE
v0.2  ██████████  DONE
v0.3  ██████████  DONE
v0.4  ██████████  DONE
v0.5  ░░░░░░░░░░  TODO
v0.6  ░░░░░░░░░░  TODO
v0.7  ░░░░░░░░░░  TODO
v0.8  ░░░░░░░░░░  TODO
v0.9  ░░░░░░░░░░  TODO
v1.0  ░░░░░░░░░░  TODO
```
