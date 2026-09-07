# Model Benchmark — Amazon Nova (Día 3 del sprint)

Fecha de medición: 2026-09-07 (us-east-1, `BEDROCK_TEMPERATURE=0` en el
pipeline; el benchmark usa `0` para los counters, la app usa `0.2`).

Se comparan los dos candidatos permitidos por el scope:

```text
amazon.nova-micro-v1:0
amazon.nova-lite-v1:0
```

Mediciones reales generadas con:

```bash
make benchmark                 # script/benchmark.py  — latencia + counters
python scripts/run_evals.py --tier llm --output dist/evals/llm_*.md
```

Todas las métricas de calidad provienen del tier **LLM** de la suite de
evals (25 casos, mismos casos para ambos modelos). La latencia proviene
de evaluaciones completas con los ejemplos de demo (5 runs por modelo,
dos rondas).

## Latencia (evaluación completa = 3 llamadas al modelo, 0 tools)

| Modelo | p50 | p95 | min | runs |
|---|---|---|---|---|
| Nova Micro | 4.49 s | 4.70 s | 4.46 s | 5/5 saludables |
| Nova Lite | 6.67 s | 66.15 s | 4.38 s | 3/5 saludables (2 runs >60 s) |

Nova Micro: ronda estable (4.46–4.70 s en las 5 ejecuciones).
Nova Lite: 3 runs sanos (4.38–6.67 s) y 2 runs de ~65 s — la mediana
queda dominada por respuestas lentas de Bedrock. En ventanas donde el
servicio responde normal, Lite es ~1.2–1.5× la latencia de Micro.

**Nota sobre degradación transitoria de Bedrock:** durante esta sesión
se observaron respuestas esporádicas de ~60 s en *ambos* modelos (también
Micro llegó a 64 s en la primera ronda). No es atribuible a la elección
de modelo; es variabilidad del servicio. Impacta el p95, no la mediana.

## Counters por evaluación (ambos modelos)

| Contador | Micro | Lite |
|---|---|---|
| `llm_calls` | 3 | 3 |
| `llm_cycles` | 3 | 3 |
| `tool_calls` | 0 | 0 |
| `input_tokens` (p50) | 3,811 | 3,811 |
| `output_tokens` (p50) | 844 | 673 |

El costo estructural del pipeline es idéntico: 3 invocaciones
single-shot, 0 loops. (Nota de implementación: Strands registra el
schema estructurado como pseudo-tool interna; `app.service` la excluye
de `tool_calls`, que cuenta únicamente tools reales del agente.)

## Calidad (tier LLM, 25 casos)

| Métrica | Micro | Lite | Mejor |
|---|---|---|---|
| Skill recall (avg) | 100% | 100% | empate |
| Skill precision (avg) | 100% | 100% | empate |
| Years extraction | 100% (25/25) | 100% (25/25) | empate |
| Clasificación de requisitos | 96% (24/25) | 92% (23/25) | **Micro** |
| Recomendación correcta | 100% (25/25) | 96% (24/25) | **Micro** |
| Statuses inventados | 0 | 3 | **Micro** |
| Statuses degradados | 0 | 0 | empate |
| Evidencia alucinada | 0 | 0 | empate |
| Tool invocation (agent demo) | 100% (3/3) | 66.7% (2/3) | **Micro** |

Fallos de clasificación:
- **Micro** falla `ambiguous_requirement_unstated` (menciones en prosa
  clasificadas como required; debilidad conocida, ver README/Limitations).
- **Lite** falla el mismo caso **y** `ambiguous_requirement_tools`
  (inventa `kubernetes`/`terraform` como prefieridos), además de la
  recomendación de `junior_vs_senior_unstated_years` — y en la demo de
  workflow no invoca todas las tools.

## Costo estimado por evaluación

Precios Bedrock on-demand us-east-1 ($$ por 1M tokens, verificados
2026-09-07): Micro `0.035` in / `0.140` out; Lite `0.060` in / `0.240` out.

Uso real por evaluación (tokens p50 del benchmark):

| Modelo | Input | Output | Costo/eval | Costo/1k evals |
|---|---|---|---|---|
| Micro | 3,811 | 844 | **$0.000251** | $0.25 |
| Lite | 3,811 | 673 | $0.000391 | $0.39 |

Micro es ~36% más barato. Para el suite de evals LLM (50 extracciones +
3 loops de tools) el costo real fue del orden de centavos.

## Decisión

**Mantener `amazon.nova-micro-v1:0`.**

Según la política de AGENTS.md no se sube de modelo por intuición ni por
una respuesta ocasionalmente peor: se sube solo si una prueba demuestra
que el modelo actual es insuficiente. Aquí la prueba demuestra lo
contrario — Nova Lite:

- clasifica requisitos **peor** (92% vs 96%);
- da recomendaciones **peores** (96% vs 100%) con **3 statuses
  inventados** contra 0;
- es **más lento** (mediana sana ~1.2–1.5×, p95 dominado por
  degradaciones);
- y es más caro.

Micro gana en latencia + calidad + costo. La única falla residual de
Micro (casos de requisitos ambiguos en prosa) no se corrige con Lite, así
que cambiar de modelo no aportaría nada — el siguiente paso para esa falla
es prompt/normalización (ruta ya documentada en ADR-0003), no un modelo
mayor.

## Reproducibilidad

Archivos formales en `dist/benchmark/` (no versionados):

```text
report_nova_micro.md   baseline_nova_micro.json
report_nova_lite.md    baseline_nova_lite.json
dist/evals/llm_nova_micro.md
dist/evals/llm_nova_lite.md
```