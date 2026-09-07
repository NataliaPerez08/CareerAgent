# CareerAgent Demo

Escenario reproducible de demo, objetivo **< 3 minutos**.

## Setup (antes de grabar)

```bash
cp .env.example .env          # ajustar AWS_REGION si hace falta
make dev                      # o: python -m pip install -e '.[dev]'
make run                      # abre http://127.0.0.1:8000/
```

Requisitos: credenciales AWS con acceso a Bedrock (Nova Micro).
Todo el material de la demo está en:

```text
examples/demo_resume.txt   CV del candidato demo
examples/demo_job.txt      vacante demo
```

Ambos textos están también embebidos en el botón **Load example** de la
UI, así la demo es un clic (no requiere teclear ni subir archivos).

## Resultado esperado (verificado en una ejecución real)

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

## Guion (timeline)

```text
00:00  Problema: las vacantes son ruidosas; cuesta saber si eres
       un fit real o si te falta una sola skill no crítica.
00:20  Abrir la UI (http://127.0.0.1:8000/) — dos inputs: CV y vacante.
00:35  Click en "Load example" (carga CV + vacante demo).
00:50  Click en "Analyze" (el pipeline corre: extracción → matching
       determinista → política → plan de carrera).
01:10  Resultado: badge APPLY + score ring 80.
01:30  Evidence: cada skill coincide con una cita literal del CV
       (nada inventado).
01:50  Skill gaps agrupados por severidad: aws (required),
       ci/cd y kubernetes (preferred), con preparation steps.
02:10  Interview topics + preparation plan para el gap.
02:30  Arquitectura (una frase): "el LLM interpreta, el código decide,
       los evals lo verifican" — 5 tools deterministas.
02:45  Evals: reporte con 0 evidencia fabricada y 92% de recomendaciones
       correctas (Nova Micro, 25 casos).
03:00  Cierre.
```

## Demo alternativa por CLI (sin UI)

```bash
python -m app.cli                 # usa examples/demo_* por defecto → JSON estructurado
python -m app.cli --chat          # agente Strands con el workflow de 5 tools
```

## Nota sobre tiempos

Una evaluación completa (3 llamadas a Nova Micro, sin tools) tarda ~15-40 s según
la región. En la demo, narrar la arquitectura mientras corre el
spinner.
