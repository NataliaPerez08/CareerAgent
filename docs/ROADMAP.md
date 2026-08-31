# CareerAgent Roadmap

## Estado general

**Versión actual:** `v0.9`
**Estado:** `DONE`

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

* [x] Upload de PDF (multipart + CLI por argumento; migrado a `POST /api/v1/evaluations/upload` en v0.5)
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

**Estado:** `DONE`

### Objetivo

Exponer CareerAgent como servicio mediante una API versionada y estable.

### Endpoints

```http
GET /health

POST /api/v1/evaluations

POST /api/v1/evaluations/upload
```

Posteriormente (v0.7, junto con persistencia):

```http
GET /api/v1/evaluations/{id}
```

### Implementado

* [x] FastAPI con prefijo `/api/v1` (contrato estable; `/evaluate` y `/evaluate/upload` migrados al namespace versionado junto con sus consumidores)
* [x] Request schema `EvaluationRequest` (`resume_text` + `job_description`, min 20 / max 100_000 chars)
* [x] Response `EvaluationResult` (`response_model` + OpenAPI)
* [x] Exception handler global: cualquier fallo inesperado (modelo/red/runtime) → 502 con logging centralizado
* [x] Errores de dominio del upload mapeados explícitamente (413/415/422/400)
* [x] Logging por request (tamaño de inputs) y logging de errores con traceback
* [x] Health endpoint
* [x] OpenAPI documentado en `/docs` y `/openapi.json` (tags, summaries)
* [x] Core desacoplado de HTTP (`app.service` no importa FastAPI)
* [x] `GET /api/v1/evaluations/{id}` diferido a v0.7 (sin persistencia; no se inventa almacenamiento temporal)

### Tests (FastAPI TestClient)

* [x] 200 happy path (texto y upload)
* [x] 422 payload inválido
* [x] 422 CV vacío
* [x] 422 vacante vacía
* [x] 422 campos faltantes / texto sobredimensionado
* [x] 502 fallo del modelo (texto y upload, vía exception handler global)
* [x] 415 formato no soportado, 413 tamaño excedido, 422 PDF corrupto/escaneado/vacío
* [x] OpenAPI documenta los endpoints

### Definition of Done

* [x] API documentada en `/docs`
* [x] Tests pasan (117 passed)
* [x] Core desacoplado de HTTP

---

## v0.6 — Web UI

**Estado:** `DONE`

### Objetivo

Crear una interfaz mínima para demo. No construir un ATS completo.

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

### Implementado

* [x] UI servida por FastAPI en `/` (`app/static/`: HTML + CSS + JS vanilla, sin build tooling ni dependencias nuevas)
* [x] Input de CV: pestañas Paste text / Upload file (PDF/TXT, con nombre de archivo visible)
* [x] Paste de job description
* [x] Botón Analyze con estado de carga (spinner + contador de segundos) y botón deshabilitado durante la ejecución
* [x] Botón Load example para demo instantánea (textos embebidos sincronizados con `examples/`)
* [x] Render del resultado: badge APPLY/MAYBE/SKIP, score ring con color por threshold, experience match, matched skills, missing skills agrupados por severidad (critical/required/preferred), evidence, skill gaps con preparation steps, interview topics, preparation plan, reasoning
* [x] Manejo de errores en la UI: validación client-side espejo del server (min 20 chars), render amigable de 413/415/422/502 y errores de red
* [x] Render XSS-safe: todo contenido dinámico (skills, evidence, topics del LLM) via `textContent`/`createElement`
* [x] Diseño responsive (single column en móvil), usabilidad > diseño sofisticado

### Mostrar

* [x] Recommendation
* [x] Match score
* [x] Matched skills
* [x] Missing skills
* [x] Evidence
* [x] Skill gaps
* [x] Interview preparation

### Definition of Done

* [x] Una evaluación puede hacerse sin CLI (`http://127.0.0.1:8000/`)
* [x] La demo principal tarda menos de 60 segundos (Load example → Analyze)
* [x] No requiere conocimientos técnicos para utilizarla
* [x] Tests pasan (111 passed) y Docker verificado (estáticos incluidos en el wheel)

---

## v0.7 — Persistencia

**Estado:** `DONE`

### Objetivo

Guardar evaluaciones e historial.

### Stack

* PostgreSQL (producción / docker compose)
* SQLite (default local, zero-config, mismas migraciones)
* SQLAlchemy 2.0 + Alembic

### Entidades

* [x] Candidate (`candidates`)
* [x] Resume (`resumes`)
* [x] Job (`jobs`)
* [x] Evaluation (`evaluations`)

### Relaciones

```text
Candidate ──1:N──> Resume
Resume + Job ──> Evaluation
```

### Implementado

* [x] Database layer (`app/db.py`: `DATABASE_URL`, engine/session factory, `get_session` dependency)
* [x] Models (`app/models.py`: tipos portables Integer/String/Text/Boolean/DateTime/JSON → mismos models y migraciones en SQLite y PostgreSQL)
* [x] Migrations (`app/migrations/` dentro del package → viajan en el wheel/Docker; `alembic.ini` + `make migrate`; autogenerate contra DB vacía)
* [x] Migraciones aplicadas on-boot (lifespan ejecuta `alembic upgrade head`; única fuente de verdad del schema)
* [x] Repository/service layer (`app/repository.py`: save/get/list, reconstrucción `EvaluationResult`, `job_title` determinista = primera línea no vacía)
* [x] Evaluation history (`GET /api/v1/evaluations?limit=` → summaries newest-first)
* [x] `GET /api/v1/evaluations/{id}` (404 si no existe) — endpoint diferido desde v0.5
* [x] POST devuelve `id`, `created_at`, `job_title` (`EvaluationResponse` extiende `EvaluationResult`)
* [x] Timestamps (`created_at` UTC en las 4 entidades)
* [x] Persistencia best-effort: si el guardado falla tras una evaluación exitosa (costosa), se devuelve el resultado sin `id` y se loguea el error — degradación explícita, nunca silenciosa
* [x] Guardado: score, recommendation, matched/missing skills, evidence, gaps, topics, plan, reasoning, texto del CV y de la vacante. Prompts internos nunca se guardan
* [x] docker-compose.yml (postgres + api con volumen `pgdata`)
* [x] UI: indicador "Saved — evaluation #N" enlazado al endpoint GET

### Definition of Done

* [x] Evaluaciones sobreviven al reinicio de la aplicación (verificado con Postgres en docker compose: restart del API + GET por id)
* [x] Migraciones reproducibles (verificadas en SQLite y PostgreSQL)
* [x] API permite recuperar evaluaciones guardadas
* [x] Tests pasan (122 passed)

---

## v0.8 — AWS AgentCore

**Estado:** `BLOCKED (deployment)`

> El código, la configuración, los tests y la documentación de deployment están
> DONE y verificados localmente. El deploy real a AWS y la demo remota quedan
> `BLOCKED`: este entorno no tiene credenciales AWS (`aws sts` → NoCredentialsError).
> Con credenciales, el despliegue es un comando: ver `docs/deploy/agentcore.md`.
> v0.9 (evals) no depende de AgentCore y puede avanzar.

### Objetivo

Desplegar el agente usando servicios administrados de AWS.

### Implementado

* [x] Adapter `app/agentcore_runtime.py` (`bedrock-agentcore` SDK 1.22, `@app.entrypoint`, payload `resume_text`/`resume_b64` + `job_description` → `EvaluationResult`)
* [x] Separación respetada: `domain/core ← local runtime (FastAPI) ← AgentCore runtime`; el core no se modifica y sigue 100% testeable localmente (`make test`, `make run`)
* [x] Protocolo verificado en local sin AWS: `/ping` 200, `/invocations` valida y responde (server `make agentcore-run`, port 8080)
* [x] Deployment reproducible: `scripts/agentcore_deploy.py` (direct code deployment: zip del core + S3 + `Create/UpdateAgentRuntime`, PYTHON_3_13, entrypoint `main.py`) + `make agentcore-zip` / `make agentcore-deploy`
* [x] Paquete de deployment deliberadamente lean: core + adapter (12 archivos, sin FastAPI/SQLAlchemy/Alembic/UI)
* [x] Observabilidad: logs de stage con duración en `app.service` (visible local y en CloudWatch), `requestId` + errores estructurados del runtime, doc de CloudWatch Transaction Search / traces
* [x] Sessions: decisión documentada de NO usarlas (evaluación single-shot, sin estado conversacional)
* [x] Docs reproducibles: `docs/deploy/agentcore.md` (prerequisitos, rol de ejecución, deploy, invocación, observabilidad, alternativa CLI `@aws/agentcore`)
* [x] Tests: 13 nuevos (handler text/b64/errores + protocolo `/ping` y `/invocations` con TestClient)
* [x] `bedrock-agentcore` como extra opcional `[agentcore]` (no es dependencia del core ni del API local)

### Pendiente (requiere credenciales AWS)

* [ ] Ejecutar `make agentcore-deploy` contra una cuenta real
* [ ] Demo remota funcional (InvokeAgentRuntime)
* [ ] Verificar traces en CloudWatch Transaction Search

### Restricción

El core debe seguir funcionando localmente.

### Definition of Done

* [x] Agent desplegable (paquete + script + docs reproducibles; ejecución pendiente de credenciales)
* [ ] Demo remota funcional
* [ ] Tracing visible
* [x] Documentación de deployment reproducible

---

## v0.9 — Agent Evaluations

**Estado:** `DONE`

### Objetivo

Medir objetivamente el comportamiento de CareerAgent.

### Dataset inicial

```text
tests/evals/
├── dataset.json (25 casos, 8 categorías, 3-4 casos por categoría)
├── README.md (schema, métricas, política de costos)
└── runner.py (importable + CLI)
```

* [x] `strong_match` (4), `weak_match` (3), `missing_required` (3), `missing_preferred` (3), `junior_vs_senior` (3), `ambiguous_requirement` (3), `skill_alias` (3), `irrelevant_experience` (3)
* [x] Cada caso auto-contenido: resume/job redactados para que la evidencia dorada sea verbatim y los `hallucination_probes` estén ausentes (verificado por tests)

### Métricas

Dos tiers separados por diseño (`make test` nunca llama a Bedrock):

* [x] Deterministic tier (`make eval`, gratis y reproducible): recommendation correctness, match exactness (score + 5 conjuntos de skills + experience_match), requirement classification, evidence grounding, evidence hallucination (probes descartados)
* [x] LLM tier (`make eval-llm`, Bedrock Nova Micro): skill extraction (recall/precision), years extraction, requirement classification (4 buckets + statuses inventados/demoted), recommendation correctness end-to-end, evidence hallucination post-guard, tool invocation (agent loop completo, sampleo por costo)

### Resultados ejecutados (Nova Micro, 25 casos, temperatura 0.2)

```text
Deterministic tier
Correct recommendation:      100% (25/25)
Match exactness:             100% (25/25)
Requirement classification:  100% (25/25)
Evidence grounding:          100% (25/25)
Evidence hallucination:        0 kept fabricated items

LLM tier
Skill recall (avg):          97.2%
Skill precision (avg):       99.2%
Years extraction:            100% (25/25)
Requirement classification:   88% (22/25)
Recommendation correctness:   92% (23/25)
Evidence hallucination:        0% (0 items)  ← target crítico cumplido
Tool invocation:             100% (3/3 agent loops, 5/5 tools)
```

Sólo se reportan métricas efectivamente ejecutadas; el reporte se escribe en
`dist/evals/report.md` con timestamp y modelo.

### Hallazgos → correcciones con regression test

El eval encontró problemas reales, corregidos en el código (no cambiando de modelo):

* [x] Alias faltantes emitidos por Nova Micro: `cicd` → `ci/cd`, `cpp` → `c++` (`SKILL_ALIASES`)
* [x] Duraciones extraídas como skills ("1+ year of") → regla explícita en el prompt de extracción
* [x] Items de listas "Requirements" dropeados cuando hay menciones en prosa → regla explícita en el prompt
* [x] Leak de ejemplo del prompt ("you will also work with kubernetes" echoado como requisito) → ejemplo eliminado del prompt

### Limitaciones conocidas de Nova Micro (documentadas, no perseguibles sin sobreajustar)

* varianza run-to-run a temperatura 0.2
* menciones en prosa ocasionalmente clasificadas como required (categoría `ambiguous_requirement`)
* escalado ocasional a critical de listas "Requirements" planas

### Definition of Done

* [x] Evals ejecutables por separado (`make eval` / `make eval-llm`, defaults seguros)
* [x] Resultados reproducibles (deterministic tier 100% estable; LLM tier con varianza documentada)
* [x] Reporte generado automáticamente (stdout + `dist/evals/report.md`, exit code por targets)
* [x] Tests: 219 passed (dataset integrity + tier determinista como tests normales)

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
v0.5  ██████████  DONE
v0.6  ██████████  DONE
v0.7  ██████████  DONE
v0.8  █████░░░░░  BLOCKED (deployment)
v0.9  ██████████  DONE
v1.0  ░░░░░░░░░░  TODO
```
