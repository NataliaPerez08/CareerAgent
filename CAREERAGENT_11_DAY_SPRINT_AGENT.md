# CareerAgent — Sprint de 11 días para el Agente de Implementación

## Rol

Actúas como el agente principal de implementación de **CareerAgent** durante los 11 días restantes antes de la entrega del hackathon.

El proyecto ya tiene una base funcional con:

- Python
- Strands Agents SDK
- Amazon Bedrock
- Amazon Nova Micro
- FastAPI
- PostgreSQL
- SQLAlchemy
- Alembic
- Docker
- Nix
- pytest
- Amazon Bedrock AgentCore
- UI funcional
- evals
- persistencia
- deployment remoto

Tu objetivo NO es rehacer la arquitectura ni agregar infraestructura por gusto.

Tu objetivo es convertir CareerAgent en una demo rápida, cómoda y convincente.

---

# Objetivos prioritarios

Al final del sprint, la experiencia ideal debe ser:

```text
CV
 +
Job URL
   ↓
CareerAgent
   ↓
Resultado en menos de 15 segundos idealmente
   ↓
Score + APPLY / MAYBE / SKIP
   ↓
Evidence + skill gaps + interview plan
   ↓
Persistencia en historial
```

Si hay tiempo:

```text
1 CV + varias vacantes
        ↓
ranking de oportunidades
```

---

# Principios obligatorios

## 1. No agregar infraestructura innecesaria

No agregar:

- Kubernetes
- nuevos microservicios
- Kafka
- Redis salvo necesidad demostrable
- nuevas bases de datos
- auth compleja
- nuevas nubes
- frameworks frontend grandes sin necesidad
- nuevas capas arquitectónicas sin beneficio claro

El proyecto ya tiene suficiente infraestructura.

---

## 2. Medir antes de optimizar

No cambiar de modelo o reescribir el flujo sin medir.

Toda optimización de latencia debe registrar:

```text
request_start
resume_parse
job_parse
llm_call_1
tool_calls
llm_call_2
agentcore_overhead
persistence
response_end
```

Debe ser posible saber dónde se consume el tiempo.

---

## 3. LLM interpreta, código decide

Mantener la arquitectura:

```text
Resume / Job
     ↓
LLM extraction
     ↓
Structured data
     ↓
Deterministic normalization
     ↓
Deterministic matching
     ↓
Recommendation policy
     ↓
LLM explanation
```

No volver a convertir CareerAgent en:

```text
CV + Job → LLM → opinión
```

---

## 4. Mantener calidad

No sacrificar:

- evidence grounding
- skill precision
- recommendation correctness
- no fabricated evidence
- tests existentes
- evals existentes

por ganar unos segundos.

Toda optimización debe compararse contra el baseline actual.

---

# Estado inicial

Antes de empezar:

1. leer `AGENTS.md`;
2. leer `docs/ROADMAP.md`;
3. ejecutar tests;
4. ejecutar evals deterministas;
5. verificar deployment remoto;
6. registrar baseline de latencia.

No recrear el proyecto desde cero.

---

# Día 1 — Instrumentación de latencia

## Objetivo

Saber exactamente por qué una evaluación tarda 30–40 segundos.

## Implementar

Agregar medición de tiempo para:

```text
request total
resume parsing
job parsing
LLM extraction
tool execution
recommendation
LLM explanation
AgentCore invocation
database persistence
```

Preferir `time.perf_counter()`.

Registrar métricas estructuradas.

Ejemplo:

```json
{
  "total_ms": 34200,
  "resume_parse_ms": 120,
  "job_parse_ms": 40,
  "llm_ms": 27800,
  "tools_ms": 85,
  "agentcore_overhead_ms": 5100
}
```

No registrar contenido completo del CV ni prompts.

## Agregar comando

Idealmente:

```bash
make benchmark
```

## Done

Debe existir un baseline reproducible.

---

# Día 2 — Reducir agent loops

## Objetivo

Reducir la cantidad de rondas:

```text
LLM → tool → LLM → tool → LLM
```

## Meta

Preferir:

```text
LLM extraction
    ↓
Python deterministic pipeline
    ↓
LLM explanation
```

Objetivo ideal:

```text
2–3 llamadas al modelo máximo
```

## Reglas

- no unir todo en una mega-tool sin razón;
- evitar tools que sólo encapsulan lógica trivial;
- ejecutar en Python todo lo determinista;
- mantener tool usage demostrable para Strands.

## Validar

Comparar:

```text
before latency
after latency
before evals
after evals
```

No aceptar regresión significativa de calidad.

---

# Día 3 — Benchmark de modelos

## Objetivo

Comparar al menos:

```text
Amazon Nova Micro
Amazon Nova Lite
```

Opcionalmente un tercer modelo ya autorizado en Bedrock.

## Medir

Para los mismos casos:

```text
p50 latency
p95 latency
recommendation correctness
skill recall
skill precision
tool invocation success
evidence hallucination
estimated cost
```

## Resultado esperado

Crear:

```text
docs/MODEL_BENCHMARK.md
```

con una tabla comparativa.

## Regla

No cambiar el modelo por intuición.

Elegir según:

```text
latency + quality + cost
```

---

# Día 4 — Ingestión de vacante por URL

## Objetivo

Eliminar la necesidad de copiar y pegar la descripción manualmente.

## UI

Agregar:

```text
Job URL
[ https://company.com/jobs/... ]

[ Load job ]
```

Mantener:

```text
Paste description manually
```

como fallback.

## Backend

Crear una capa clara:

```text
job_ingestion
```

Debe intentar obtener:

- title
- company
- description
- source URL

## Reglas

- respetar timeout;
- usar user-agent razonable;
- no intentar bypass anti-bot;
- no hacer scraping agresivo;
- fallar elegantemente;
- permitir pegar texto manual.

## Done

Una URL sencilla debe cargar una vacante sin intervención manual adicional.

---

# Día 5 — UX del flujo

## Objetivo

Hacer que la espera parezca controlada.

## Estados UI

Mostrar progresivamente:

```text
Loading job...
Analyzing resume...
Extracting requirements...
Matching skills...
Preparing recommendation...
Saving evaluation...
```

No mostrar spinner muerto.

Agregar mensajes claros para:

- URL no accesible;
- PDF inválido;
- Bedrock timeout;
- AgentCore error;
- vacante vacía.

## Done

La demo debe poder entenderse sin explicación verbal.

---

# Día 6 — Historial

## Objetivo

Aprovechar la persistencia ya existente.

Agregar:

```text
Recent evaluations
```

Ejemplo:

```text
Backend Engineer    84% APPLY
Cloud Engineer      73% APPLY
SRE                 61% MAYBE
```

Click:

```text
abre evaluación guardada
```

No agregar auth.

---

# Día 7 — AgentCore session / warm-path benchmark

## Objetivo

Determinar si parte de la latencia es cold start o afinidad de sesión.

Medir:

```text
first invocation
second invocation
third invocation
```

con:

- misma session ID;
- session ID nueva.

Registrar resultados.

Si no hay mejora significativa, detener el trabajo en esta optimización.

No gastar un día entero persiguiendo 500 ms.

---

# Día 8 — Batch ranking MVP

## Objetivo

Sólo si los días anteriores están estables.

Permitir:

```text
CV
+
Job URL 1
Job URL 2
Job URL 3
```

Resultado:

```text
1. Backend Engineer   87% APPLY
2. Cloud Engineer     74% APPLY
3. SRE                58% MAYBE
```

## Regla

El ranking inicial debe ser barato.

No ejecutar análisis profundo completo para todas las vacantes si no es necesario.

Preferir:

```text
quick ranking
   ↓
user selects one
   ↓
deep analysis
```

---

# Día 9 — Regression Evals

Ejecutar:

```bash
make test
make eval
make eval-llm
```

si el costo es aceptable.

Agregar casos para:

- URL ingestion;
- aliases nuevos;
- pipeline optimizado;
- model switch;
- batch ranking;
- fabricated evidence;
- ambiguous requirements.

## Regla

No modificar prompts sólo para conseguir 100% en el dataset.

Evitar overfitting.

---

# Día 10 — Demo freeze

A partir de aquí:

NO agregar features nuevas.

Preparar demo exacta:

```text
1. Load sample CV
2. Paste job URL
3. Load job automatically
4. Analyze
5. Show recommendation
6. Show match score
7. Show evidence
8. Show skill gaps
9. Show interview plan
10. Show history
```

Si batch ranking está listo:

```text
11. Compare multiple jobs
```

Objetivo:

```text
core demo < 3 minutes
```

---

# Día 11 — Submission

Sólo:

- screenshots
- video
- README
- Devpost
- smoke test remoto
- revisión de enlaces públicos
- tag final

No refactors de último minuto.

---

# Orden de prioridad

## Must Have

1. latency instrumentation
2. reducir agent loops
3. job URL ingestion
4. UX de espera
5. benchmark de modelos

## Should Have

6. history
7. session reuse / warm-path validation
8. batch ranking

## Nice to Have

9. company research
10. más modelos
11. nuevas tools

No implementar Nice to Have si Must Have no está completamente estable.

---

# Política de benchmarking

Cada optimización debe guardar:

```text
before
after
delta
```

Ejemplo:

```text
Before:
p50 = 34.2 s

After:
p50 = 13.8 s

Improvement:
59.6%
```

No inventar métricas.

---

# Política de modelo

Modelo actual:

```text
amazon.nova-micro-v1:0
```

Sólo cambiar si el benchmark demuestra una mejora.

Configurar mediante:

```env
BEDROCK_MODEL_ID=
AWS_REGION=
BEDROCK_TEMPERATURE=
```

No hardcodear modelos en múltiples archivos.

---

# Política de costos

Separar:

```bash
make test
```

sin llamadas LLM costosas

de:

```bash
make eval-llm
```

con llamadas reales.

No ejecutar `eval-llm` en cada commit.

---

# Política de errores

Cuando aparezca un error:

1. identificar capa;
2. reproducir;
3. registrar logs;
4. aislar;
5. corregir causa;
6. agregar regression test.

Capas:

```text
UI
API
job ingestion
Strands
Bedrock
AgentCore
database
model
network
```

---

# Política de cambios

No romper:

- CLI
- API
- UI
- Docker
- Nix
- PostgreSQL
- AgentCore
- evals
- structured output
- recommendation policy

---

# Reporte diario

Al terminar cada día reportar:

```text
1. objetivo
2. archivos modificados
3. cambios implementados
4. tests ejecutados
5. benchmark antes/después
6. bugs encontrados
7. deuda técnica
8. siguiente paso
```

---

# Definition of Done del sprint

El sprint se considera terminado cuando:

- job URL ingestion funciona;
- existe fallback manual;
- la latencia está medida;
- agent loops fueron optimizados;
- existe benchmark de modelos;
- el modelo final fue seleccionado con datos;
- UX muestra progreso;
- historial funciona;
- tests pasan;
- evals no muestran regresiones importantes;
- AgentCore sigue funcionando;
- Docker sigue funcionando;
- demo está congelada;
- README actualizado;
- video preparado;
- Devpost preparado.

Objetivo de latencia:

```text
ideal: < 15 s
aceptable: < 20 s
```

Si no es posible, documentar el cuello de botella real.

---

# Primera misión

Comienza por:

```text
Día 1 — Instrumentación de latencia
```

No saltes directamente a cambiar de modelo.

Al completar Día 1, detente y reporta el baseline antes de comenzar Día 2.
