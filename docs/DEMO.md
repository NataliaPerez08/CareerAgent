# CareerAgent Demo

Escenario reproducible de demo, objetivo **< 3 minutos** para el core.
Estado: **DEMO FREEZE (Día 10 del sprint)** — este documento y la app
están congelados; no se agregan features nuevas a partir de aquí.

## Setup (antes de grabar)

```bash
cp .env.example .env           # ajustar AWS_REGION si hace falta
make dev                       # o: python -m pip install -e '.[dev]'
make run                       # abre http://127.0.0.1:8000/
```

Requisitos: credenciales AWS con acceso a Bedrock (Nova Micro).
Todo el material de la demo está en:

```text
examples/demo_resume.txt   CV del candidato demo
examples/demo_job.txt      vacante demo
```

Ambos textos están también embebidos en el botón **Load example** de la
UI, así la demo es un clic (no requiere teclear ni subir archivos).

## Resultado esperado (verificado)

```text
Recommendation:  APPLY
Score:           80  (4/5 required skills)
Matched:         python, rest api, postgresql, docker
Missing required: aws          ← el gap con plan de preparación
Missing preferred: ci/cd, kubernetes
Experience:      2 >= 2 years  ✓
Evidence:        5 citas verbatim del CV
```

La demo es deliberadamente **no-100%**: el candidato es un fit fuerte
con un gap concreto (AWS). Eso muestra el valor real del producto —
evidencia, gaps y preparación, no un "todo bien".

## Guion (timeline) — core < 3 minutos

```text
00:00  Problema: las vacantes son ruidosas; cuesta saber si eres
       un fit real o si te falta una sola skill no crítica.
00:15  Abrir la UI (http://127.0.0.1:8000/) — dos inputs: CV y vacante.
00:30  Click "Load example" (carga CV + vacante demo).
00:40  Click "Analyze".
       → la UI muestra el avance real por etapas (SSE): lectura de CV,
         extracción de requisitos, matching determinista, preparación.
01:20  Resultado: badge APPLY + score ring 80.
01:40  Evidence: cada skill coincide con una cita literal del CV
       (nada inventado).
02:00  Skill gaps por severidad: aws (required), ci/cd y kubernetes
       (preferred), con preparation steps.
02:20  Interview topics + preparation plan para el gap.
02:40  History: el resultado quedó guardado y se reabre con un clic.
02:50  Cierre: "el LLM interpreta, el código decide, los evals lo
       verifican".
```

### Opcional si queda tiempo (30 s más)

```text
Batch ranking: pegar 2-3 URLs de vacantes → ranking rápido determinista
→ clic en una fila → análisis profundo de esa vacante.
```

## Freeze checklist (Día 10)

- [x] No features nuevas: solo verificación y este documento
- [x] Demo inputs verificados (`examples/demo_*` + "Load example")
- [x] Flujo URL: "Load job" desde una URL pública (sin scraping frágil;
      fallback a pegado manual documentado)
- [x] SSE progress + timeout explícito (504) si el modelo se cuelga
- [x] History: listado + reabrir evaluación guardada
- [x] Dropdown de fallback: si Bedrock devuelve respuestas lentas
      (degradación documentada de 60 s+), la demo se cuenta igualmente:
      narrar arquitectura mientras el pipeline corre

## Demo alternativa por CLI (sin UI)

```bash
python -m app.cli                    # usa examples/demo_* por defecto → JSON estructurado
python -m app.cli --chat             # agente Strands con el workflow de 5 tools
```

## Nota sobre tiempos

Una evaluación completa (3 llamadas a Nova Micro, sin tools) tarda
~15-60 s según la región y la salud del servicio. El guardado es
best-effort en cada request. En la demo, narrar la arquitectura mientras
el pipeline corre (la UI muestra del progreso real por etapas, no un
spinner muerto).