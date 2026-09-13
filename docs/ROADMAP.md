# CareerAgent Roadmap

## Estado general

**Versión actual:** `v1.0`
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

**Estado:** `DONE (deployed, remote invoke working)`

> El despliegue real se completó y la invocación remota funciona. Tres causas
> raíz se corrigieron en el camino:
> 1. **Prefijo de acciones**: AgentCore usa el prefijo IAM `bedrock-agentcore:`
>    (no `bedrock-agentcore-control:`) — el grant inicial no matcheaba nada.
> 2. **Arquitectura ARM64 + dependencias vendored**: AgentCore Runtime es solo
>    aarch64 y **no instala `requirements.txt` en cold start** — las deps deben
>    venderse como wheels arm64 en el zip. El venv local era x86_64.
> 3. **Python 3.13 breaka la serialización de toolUse en strands-agents**: el
>    runtime por defecto (PYTHON_3_13) emitía `toolUse.input` como string en vez
>    de objeto JSON → `ConverseStream ValidationException` (mascarado como 500
>    genérico "Received error (500) from runtime", sin logs en la capa API hasta
>    que se habilitó la lectura). Fix: desplegar con **PYTHON_3_11** + wheels
>    cp311-arm64, la versión donde el stack completo corre y se valida local.
>
> Estado actual: runtime `career_agent-FU4ZcW236R` desplegado y **READY** (v4,
> PYTHON_3_11) con nuestro core y empaquetado arm64 vendored; la **invocación
> remota funciona** y devuelve el `EvaluationResult` correcto (demo → APPLY,
> 80) en ~9s; logs de stage y duración visibles en CloudWatch
> `/aws/bedrock-agentcore/runtimes/<id>-DEFAULT`. Detalle en
> `docs/deploy/agentcore.md` § "Deployment attempt log".

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
* [x] Creación de rol de ejecución automatizada: `scripts/agentcore_deploy.py --create-role` / `make agentcore-role` (idempotente, política least-privilege cubierta por unit tests en `tests/test_agentcore_deploy.py`)
* [x] Corrección del grant admin: prefijo correcto `bedrock-agentcore:*` + lectura de logs (comando listo en `docs/deploy/agentcore.md` § "Option 1, ready to run")
* [x] Empaquetado ARM64 vendored: `build_package(..., vendor=True)` (uv pip --python-platform aarch64-manylinux_2_17, --only-binary=:all:) incluye las deps como wheels arm64 en el zip (29 MB, <.so> aarch64 verificado)

### Pendiente (bloqueo del runtime, requiere diagnóstico en la cuenta)

* [x] `make agentcore-deploy` contra la cuenta real — **DONE** (runtime READY v4)
* [x] Demo remota funcional (InvokeAgentRuntime) — **DONE** (demo → APPLY, 80, ~9s; ver logs en CloudWatch)
* [x] Verificar traces en CloudWatch Transaction Search — logs de stage y duración visibles en `/aws/bedrock-agentcore/runtimes/<id>-DEFAULT` (invocation completa 8.9s)

### Restricción

El core debe seguir funcionando localmente.

### Definition of Done

* [x] Agent desplegable (paquete + script + docs reproducibles; ejecución pendiente de credenciales)
* [x] Demo remota funcional
* [x] Tracing visible
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

**Estado:** `DONE`

> DONE en todo lo automatizable y verificable. Requieren acción humana
> (y quedan pendientes para el equipo): publicar el repo, grabar el
> video con `docs/VIDEO_SCRIPT.md`, capturar las screenshots listadas en
> `docs/screenshots/README.md` desde la app real, y crear la submission
> en Devpost a partir de `docs/DEVPOST.md`.

### Objetivo

Congelar funcionalidad y preparar la entrega. No se agregaron features nuevas.

### Producto

* [x] Flujo end-to-end estable (verificado: local, Docker, Bedrock real)
* [x] UI funcional (demo de un clic: Load example → Analyze)
* [x] Deployment público — runtime AgentCore desplegado y READY (v4), invocación remota funcional (APPLY, 80, ~9s); documentado en v0.8 y `docs/deploy/agentcore.md`
* [x] Tests estables (219 passed)
* [x] Eval report (ejecución final registrada en README con fecha/modelo/config)

### Freeze respetado

Sólo se hicieron: corrección de bugs (alias/leak del prompt), mejora de demo
(parábola demo nueva verificada: APPLY 80 con gap de AWS), documentación,
seguridad/limitaciones honestas, y cleanup (ejemplos obsoletos eliminados).

### Documentación

* [x] README final tipo landing page (Problem, Solution, Demo, How it works, Architecture Mermaid, Why agentic, Stack, Features, Evaluation, Quick start, AWS setup, Docker, Tests, Security/privacy, Limitations, Roadmap, Hackathon, License)
* [x] Architecture diagram (Mermaid, AgentCore como planned deployment — no como componente activo)
* [x] `docs/DEMO.md` (escenario reproducible < 3 min + guion con timeline)
* [x] `docs/VIDEO_SCRIPT.md`
* [x] `docs/DEVPOST.md` (sin premios/usuarios/métricas inventadas)
* [x] `docs/screenshots/README.md` (lista de capturas requeridas; ninguna generada artificialmente)
* [x] `docs/deploy/agentcore.md` + log exacto del intento de deployment (comando, error, servicio, permiso)

### Verificación final (2026-09-01)

* [x] `make test` → 219 passed
* [x] `ruff check .` → PASS
* [x] `make eval` → deterministic tier 100% en las 4 métricas, 0 evidencia fabricada
* [x] `make eval-llm` → ejecución final: recomendación 92%, alucinación de evidencia 0%, tool invocation 100% (rango run-to-run documentado en README)
* [x] Docker validado desde cero: build, compose up, health, UI, evaluación real end-to-end dentro del contenedor, persistencia PostgreSQL, history/GET por id, down
* [x] Fresh clone test desde el commit final (install → test → migrate → run → evaluación real) — README corregido si falla
* [x] Sin secretos en el repo (scan); `.gitignore` verificado
* [x] LICENSE Apache-2.0 completo presente

### Definition of Done

* [x] Demo estable (< 3 min, un clic, resultado verificado no-100%)
* [ ] Video grabado (requiere humano; guion listo)
* [x] Repositorio limpio
* [ ] Submission completa (requiere humano; borrador listo)

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
v1.0  ██████████  DONE (video/submission/publicación: acción humana)
```

---

# Sprint 11 días (post-v1.0)

Optimizaciones medibles sobre el producto ya lanzado. Cada día cierra
con medición antes/después. Detalles en
[`CAREERAGENT_11_DAY_SPRINT_AGENT.md`](../CAREERAGENT_11_DAY_SPRINT_AGENT.md).

```text
Día 1  Instrumentación de latencia      DONE (243 tests)
Día 2  3 calls, 0 tools, counters       DONE (254 tests; real: 4.49 s p50)
Día 3  Benchmark de modelos             DONE (Micro > Lite; docs/MODEL_BENCHMARK.md)
Día 4  Ingestión de vacante por URL     DONE (325 tests; POST /api/v1/jobs/fetch + UI;
                                           extracción además desde JSON embebido: JSON-LD
                                           JobPosting y scripts de datos de SPAs como Phenom)
Día 5  UX del flujo                     DONE (279 tests; SSE progress stages + timeout 504)
Día 6  Historial                         DONE (recent evaluations UI; click opens stored result)
Día 7  AgentCore session/warm-path       DONE (--warm-path probe: no significant warm-up
                                             → session reuse STOPPED; docs/MODEL_BENCHMARK.md)
Día 8  Batch ranking MVP                 DONE, RETIRADO POST-v1.0 (POST /api/v1/batch/quick-ranking
                                             eliminado a petición del usuario; UI, módulo, schemas y
                                             tests limpiados)
Día 9  Regression Evals                  DONE-DETERMINISTIC (alta de 32→33 originales; hoy 32 tras
                                              retirar batch_ranking: URL ingestion, ci/cd+cpp aliases,
                                              pipeline single-shot, model-switch guard,
                                              fabricated evidence)
                                              → `make eval` verde. `make eval-llm`: intentado,
                                             Bedrock degradado (calls 60s+), métricas NO ejecutadas
                                             → reportadas como NOT RUN, no fabricadas. Re-run pendiente.
Día 10 Demo freeze                        DONE (sin features nuevas; docs/DEMO.md: guion core < 3 min,
                                              SSE progress, history, checklist)
Día 11 Submission                         DONE (fix SSE stage parse — el Analyze del browser caía con
                                              error genérico desde el Día 5; restyle hand-drawn Y2K;
                                              5 screenshots verificados; smoke remoto PASS: runtime
                                              career_agent READY → APPLY/80/5 evidencias en ~14 s;
                                              README Screenshots; docs/DEVPOST.md; tag v1.0)

# Post-sprint (mantenimiento, sin features nuevas)

```text
Post-Día 11   Robustez Bedrock              DONE (retry 1x en app/service.py `_call_model` para
                                             throttling / modelStreamError / service-unavailable /
                                             server-errors de stream y tool-use inválido; tests
                                             FlakyAgent/AlwaysFlakyAgent; README Features)
Post-Día 11   Demo board local              DONE (scripts/demo_job_site.py sirve demo/jobs/* en
                                             :8001; flag opcional JOB_FETCH_ALLOW_PRIVATE_HOSTS=1 que
                                             relaja el guard SSRF SOLO para localhost de demo —
                                             documentado como demo-only; tests del flag; README
                                             "Demo job board")
```

Al retirar batch ranking (Día 8) la suite quedó en **313 tests** (antes
325 en Día 4; el dataset de evals pasó a 32 casos).
```
