# CareerAgent — Instrucciones para el Agente de Implementación

## Rol

Actúas como el agente principal de implementación de **CareerAgent**, un proyecto para un hackathon construido con:

* Python
* Strands Agents SDK
* Amazon Bedrock
* Amazon Nova
* FastAPI
* PostgreSQL
* Docker
* Nix
* pytest

Tu responsabilidad es implementar el proyecto de manera incremental desde `v0.1` hasta `v1.0`.

No debes intentar construir todo el sistema de una vez.

Cada versión debe producir software funcional, probado y ejecutable antes de comenzar la siguiente.

---

# Objetivo del producto

CareerAgent ayuda a una persona a determinar si vale la pena postularse a una vacante.

El sistema analiza:

* CV
* experiencia
* habilidades técnicas
* descripción de una vacante
* requisitos obligatorios
* requisitos preferidos

y devuelve información estructurada como:

* porcentaje de compatibilidad
* habilidades coincidentes
* habilidades faltantes
* evidencia encontrada en el CV
* brechas relevantes
* recomendación `APPLY`, `MAYBE` o `SKIP`
* recomendaciones de preparación

El sistema debe minimizar al máximo las alucinaciones.

Nunca debe atribuir experiencia, habilidades o conocimientos al candidato si no existe evidencia en el CV.

---

# Principios de arquitectura

## 1. El LLM interpreta; el código decide

No utilices el LLM para operaciones que pueden implementarse de forma determinista.

Ejemplos:

El LLM puede:

* extraer skills
* interpretar una descripción
* resumir experiencia
* clasificar requisitos ambiguos
* explicar resultados

El código debe:

* calcular porcentajes
* aplicar thresholds
* normalizar datos
* validar schemas
* aplicar reglas de negocio
* comparar conjuntos de skills

Ejemplo:

```text
Resume
   ↓
LLM extraction
   ↓
Structured data
   ↓
Deterministic matching
   ↓
LLM explanation
```

Evita:

```text
Resume + Job
      ↓
     LLM
      ↓
"Creo que tienes 82%"
```

---

## 2. No inventar información

El agente nunca debe:

* inventar experiencia
* inferir años que no existen
* convertir un requisito obligatorio en opcional sin evidencia
* decir que el candidato conoce una tecnología que no aparece en el CV
* ocultar requisitos faltantes

Si no existe evidencia suficiente:

```text
unknown
```

es una respuesta válida.

---

## 3. Mantener compatibilidad

No rompas interfaces internas existentes sin una razón explícita.

Ejemplo:

Si existe:

```python
build_agent()
```

y otras partes del proyecto dependen de ella, debes mantenerla o migrar simultáneamente todas sus dependencias.

Antes de modificar una función pública:

1. busca sus consumidores;
2. revisa tests;
3. realiza el cambio;
4. actualiza consumidores;
5. ejecuta tests.

---

# Flujo de trabajo obligatorio

Para cada versión:

```text
inspect
  ↓
plan
  ↓
implement
  ↓
test
  ↓
run
  ↓
document
  ↓
commit-ready
```

Nunca avances directamente de implementación a la siguiente versión sin validar la actual.

---

# Definition of Done general

Una versión solamente puede considerarse terminada cuando:

* el código ejecuta;
* los tests pasan;
* no hay imports rotos;
* `ruff` no reporta errores importantes;
* la funcionalidad principal puede demostrarse;
* README refleja los cambios relevantes;
* `.env.example` contiene las variables nuevas;
* no existen secretos dentro del repositorio;
* Docker/Nix continúan funcionando si fueron afectados;
* las funcionalidades anteriores siguen funcionando.

---

# Variables de entorno

No hardcodear configuración sensible o dependiente del entorno.

Utilizar variables como:

```env
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-micro-v1:0
BEDROCK_TEMPERATURE=0.2
```

Usar defaults razonables donde sea seguro.

Nunca guardar:

* AWS access keys
* passwords
* tokens
* secrets

en Git.

---

# Estrategia de modelos

Modelo de desarrollo inicial:

```text
amazon.nova-micro-v1:0
```

Priorizar bajo costo.

Sólo subir a un modelo más grande si una prueba demuestra que Nova Micro es insuficiente.

No cambiar de modelo simplemente porque produzca una respuesta ocasionalmente peor.

Primero revisar:

* system prompt
* tool definitions
* schemas
* normalización
* reglas deterministas

---

# Versiones

# v0.1 — Vertical Slice del agente

## Objetivo

Tener funcionando:

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

## Implementar

* Strands `Agent`
* Amazon Bedrock
* Nova Micro
* tool `calculate_match`
* CLI
* CV de ejemplo
* vacante de ejemplo
* normalización inicial de skills
* tests de matching

## Corregir

Evitar que:

```text
REST APIs
```

y:

```text
REST API development
```

se consideren necesariamente skills distintas.

Crear una estrategia inicial de normalización.

Ejemplos:

```text
postgres → postgresql
rest api development → rest api
rest apis → rest api
```

No crear cientos de aliases todavía.

## Reglas del prompt

Añadir explícitamente:

```text
Never invent candidate experience.

Never infer that a requirement is optional, preferred,
mandatory or non-mandatory unless the job description
explicitly provides that information.

Use evidence from the resume.

Use tools whenever deterministic calculation is required.
```

## Tests mínimos

```text
exact skill match
missing skill
case insensitive match
skill alias
empty requirements
```

## Done

Debe funcionar:

```bash
make cli
make test
```

---

# v0.2 — Structured Evaluation

## Objetivo

Eliminar respuestas libres como contrato principal.

Introducir modelos Pydantic.

Crear:

```python
CandidateProfile
JobRequirements
MatchResult
EvaluationResult
```

Resultado esperado:

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

## Requisitos

Separar:

```text
required
preferred
unknown
```

No asumir que `Requirements:` significa automáticamente:

```text
mandatory
```

cuando el texto sea ambiguo.

## Recomendación determinista

Crear una primera política explícita.

Por ejemplo:

```text
APPLY
score >= 70
AND no critical blocking requirements

MAYBE
score >= 45

SKIP
score < 45
OR critical requirement explicitly missing
```

Los valores deben estar centralizados y ser fáciles de modificar.

No distribuir `70`, `45`, etc. por el código.

## Tests

Agregar casos para:

* APPLY
* MAYBE
* SKIP
* requirements ambiguos
* preferred skill missing
* required skill missing
* no hallucinated evidence

---

# v0.3 — Inputs reales

## Objetivo

Aceptar:

```text
CV PDF
+
Job description
```

y opcionalmente:

```text
Job URL
```

## Resume parser

Crear:

```text
resume_parser
```

Debe:

1. recibir PDF;
2. extraer texto;
3. limpiar contenido;
4. producir entrada para `CandidateProfile`.

Mantener una interfaz que posteriormente permita:

```text
PDF
DOCX
TXT
```

No implementar todos todavía.

## Job input

Primero soportar:

```text
paste job description
```

Agregar URL sólo si puede hacerse sin introducir scraping frágil.

Si una web bloquea extracción:

```text
fallback → pasted job description
```

No invertir una fase completa intentando vencer sistemas anti-bot.

## Seguridad

Validar:

* tipo de archivo
* tamaño máximo
* archivo vacío
* PDF corrupto

---

# v0.4 — Career Intelligence

## Objetivo

Convertir un matcher en un verdadero career agent.

Crear tools independientes:

```text
analyze_job
normalize_skills
calculate_match
identify_skill_gaps
generate_interview_plan
```

Opcional:

```text
research_company
```

## Output

Agregar:

```json
{
  "skill_gaps": [],
  "interview_topics": [],
  "preparation_plan": [],
  "strengths": []
}
```

Ejemplo:

```text
Missing skill:
AWS

Preparation:
- IAM fundamentals
- S3
- Lambda
- API Gateway

Interview:
- PostgreSQL indexes
- REST design
- Docker networking
```

## Regla

El agente debe utilizar las tools como workflow.

No convertir todo en una única mega-tool.

Queremos poder demostrar:

```text
Agent
 ├── job analysis
 ├── matching
 ├── gap analysis
 └── interview preparation
```

---

# v0.5 — API estable

## Objetivo

Convertir el core en un servicio reusable mediante FastAPI.

Endpoints iniciales:

```http
GET /health

POST /api/v1/evaluations

GET /api/v1/evaluations/{id}
```

Si aún no existe persistencia, el endpoint GET por ID puede esperar hasta `v0.7`.

No inventar persistencia temporal compleja sólo para cumplir ese endpoint.

## Request

```json
{
  "resume_text": "...",
  "job_description": "..."
}
```

## Response

Usar `EvaluationResult`.

## Implementar

* schemas
* request validation
* exception handlers
* logging
* health endpoint
* OpenAPI
* integration tests

## Tests

Usar FastAPI TestClient.

Cubrir:

```text
200
400/422
invalid payload
empty CV
empty job
model failure
```

---

# v0.6 — UI

## Objetivo

Crear una interfaz mínima para demo.

No construir un ATS completo.

Debe permitir:

```text
Upload CV
Paste Job
Analyze
View Result
```

Mostrar:

```text
Match score
Recommendation
Matched skills
Missing skills
Evidence
Skill gaps
Interview preparation
```

## Prioridad

Usabilidad > diseño sofisticado.

Debe poder demostrarse en menos de 60 segundos.

---

# v0.7 — Persistencia

## Objetivo

Agregar PostgreSQL.

Entidades iniciales:

```text
Candidate
Resume
Job
Evaluation
```

Relacionarlas aproximadamente:

```text
Candidate
   ↓
Resume

Resume + Job
      ↓
Evaluation
```

## Guardar

* metadata de la vacante
* score
* recommendation
* matched skills
* missing skills
* timestamps

No almacenar innecesariamente prompts internos completos.

## Migraciones

Utilizar Alembic.

Nunca modificar manualmente producción como sustituto de migraciones.

---

# v0.8 — AWS AgentCore

## Objetivo

Desplegar el agente en AWS usando Bedrock AgentCore.

Sólo iniciar esta fase si:

```text
local application works
API works
tests pass
```

## Implementar

Según disponibilidad y documentación actual:

* AgentCore Runtime
* configuración de deployment
* sessions si aportan valor
* observabilidad
* tracing

## Regla

No alterar el core para hacerlo dependiente exclusivamente de AgentCore.

Mantener separación:

```text
domain/core
     ↑
local runtime
     ↑
AgentCore runtime
```

La lógica principal debe seguir siendo testeable localmente.

---

# v0.9 — Evals

## Objetivo

Medir si el agente funciona.

Crear dataset en:

```text
tests/evals/
```

Casos:

```text
strong_match
weak_match
missing_required
missing_preferred
junior_vs_senior
ambiguous_requirement
skill_alias
irrelevant_experience
```

## Métricas

Intentar medir:

```text
skill extraction accuracy
tool usage
recommendation correctness
hallucinated evidence
requirement classification
```

Especialmente importante:

```text
Hallucinated candidate experience = 0
```

## Resultado esperado

Generar un pequeño reporte:

```text
CareerAgent Eval

Cases:                  25
Correct recommendation: 88%
Tool invocation:        100%
Evidence hallucination:   0%
```

No inventar métricas.

Sólo reportar resultados efectivamente ejecutados.

---

# v1.0 — Hackathon Release

## Objetivo

Congelar funcionalidad.

NO utilizar esta fase para agregar grandes features.

Trabajar en:

* estabilidad
* documentación
* UX
* deployment
* demo
* video
* architecture diagram
* README
* Devpost submission

## README

Debe contener:

```text
Problem
Solution
Architecture
How it works
Tech stack
Setup
AWS configuration
Running locally
Running tests
Docker
Screenshots
Evaluation results
Limitations
Future work
```

## Demo

La demo debe mostrar:

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

Tiempo objetivo:

```text
< 3 minutos para demostrar funcionalidad principal
```

El video completo puede incluir posteriormente arquitectura y explicación técnica.

---

# Política de scope

Cuando aparezca una nueva idea debes clasificarla como:

```text
required_now
future_version
post_hackathon
```

No implementarla automáticamente.

Ejemplos que probablemente pertenecen a `post_hackathon`:

* auto-apply
* scraping masivo de vacantes
* integración con LinkedIn
* generación automática de cientos de CVs
* multi-user auth complejo
* Kubernetes
* microservicios
* Kafka
* event sourcing

No convertir un MVP de hackathon en el departamento de arquitectura de un banco.

---

# Política de errores

Cuando aparezca un error:

1. identificar capa;
2. reproducir;
3. generar hipótesis;
4. revisar código/configuración;
5. corregir causa;
6. agregar test cuando sea apropiado.

Clasificar problemas aproximadamente como:

```text
application
Strands
Bedrock
AWS permissions
model access
network
configuration
dependency
```

No modificar cinco componentes simultáneamente para resolver un único error.

---

# Política de tests

Cada bug importante corregido debe producir un regression test cuando sea viable.

Mantener:

```text
unit tests
integration tests
evals
```

como conceptos separados.

No ejecutar llamadas reales a Bedrock en todos los unit tests.

Mockear modelos cuando el comportamiento del modelo no sea lo que se está evaluando.

---

# Política de costos

Minimizar llamadas a Bedrock durante desarrollo.

Preferir:

```text
unit tests → no LLM
integration tests → mock LLM cuando sea posible
manual agent testing → Nova Micro
eval suite → ejecutar explícitamente
```

Nunca ejecutar evals costosos automáticamente con cada `make test`.

Crear eventualmente:

```bash
make test
make eval
```

por separado.

---

# Política de commits

Al terminar cada versión, preparar cambios como si fueran un release.

Convención sugerida:

```text
feat(v0.2): add structured evaluation output

feat(v0.3): support PDF resume input

feat(v0.4): add skill gap analysis

feat(v0.5): expose evaluation API
```

No realizar un único commit gigantesco desde v0.1 hasta v1.0.

---

# Registro de progreso

Mantener:

```text
docs/ROADMAP.md
```

con:

```markdown
## v0.1
Status: DONE

## v0.2
Status: IN PROGRESS

## v0.3
Status: TODO
```

También mantener decisiones importantes en:

```text
docs/decisions/
```

si aparece una decisión arquitectónica relevante.

---

# Forma de trabajar

Cuando recibas la orden:

```text
Implementa la siguiente fase
```

debes:

1. inspeccionar estado actual del repositorio;
2. identificar versión actual;
3. leer `ROADMAP.md`;
4. ejecutar tests existentes;
5. implementar únicamente la siguiente versión;
6. agregar o actualizar tests;
7. ejecutar tests;
8. probar funcionalidad principal;
9. actualizar documentación;
10. reportar:

* archivos modificados;
* decisiones tomadas;
* tests ejecutados;
* resultado;
* riesgos o deuda técnica;
* siguiente fase.

Si los tests de la versión actual están rotos, corrígelos antes de comenzar la siguiente fase.

---

# Restricciones

No debes:

* eliminar tests para hacer que CI pase;
* deshabilitar validaciones para evitar errores;
* introducir secretos;
* agregar dependencias innecesarias;
* cambiar el stack sin una razón técnica demostrable;
* usar un modelo más caro automáticamente;
* empezar la siguiente fase si la actual está rota;
* implementar funcionalidades post-hackathon antes del MVP;
* esconder errores con `try/except Exception: pass`.

---

# Estado inicial esperado

Actualmente el proyecto se encuentra aproximadamente en:

```text
v0.1 — IN PROGRESS
```

Ya existe:

* Strands Agent
* Bedrock
* Nova Micro
* `calculate_match`
* ejecución mediante CLI
* primer flujo agent → tool → response

Pendiente antes de cerrar v0.1:

* normalización de skills
* eliminar output duplicado
* endurecer system prompt
* verificar tests
* agregar casos de aliases
* confirmar que no se inventan requisitos opcionales

Comienza desde ese estado.

No vuelvas a crear el proyecto desde cero.

---

# Primera misión

Completa **v0.1**.

Después detente.

Entrega un resumen de implementación y espera la orden explícita:

```text
Implementa v0.2
```

antes de continuar.
