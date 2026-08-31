# CareerAgent — Video Script (hackathon)

Duración objetivo: 3-4 minutos. La mayor parte debe mostrar el producto
funcionando; la instalación no se explica en el video.

## 1. Intro — el problema (0:00-0:30)

> "Job descriptions are noisy. Cuando lees una vacante, es difícil
> saber si estás realmente underqualified o si solo te falta una skill
> no crítica. Los chatbots de CV genéricos no resuelven esto:
> inventan consejos, no trabajan con evidencia.
>
> CareerAgent evalúa un candidato contra una vacante usando evidencia
> literal del CV — y nada más que esa evidencia."

## 2. Product demo (0:30-2:00)

Seguir `docs/DEMO.md` (UI en http://127.0.0.1:8000/):

1. Load example → Analyze.
2. Mostrar el resultado mientras carga: narrar qué pasa por detrás
   (extracción LLM → matching determinista).
3. Resultado: **APPLY, 80** — recorrer en pantalla:
   - matched skills con evidence verbatim;
   - missing required: **aws** — "el sistema no te dice 'aplica a
     todo', te dice exactamente qué te falta";
   - preparation plan para cerrar el gap;
   - interview topics.

Frase clave: "cada claim en la respuesta está anclado a una cita del
CV. Si no hay evidencia, el sistema dice *unknown* — nunca inventa."

## 3. Technical architecture (2:00-2:45)

Diagrama en un slide (el mismo del README):

> "El principio de diseño: **el LLM interpreta, el código decide,
> los evals lo verifican.**
>
> El LLM (Amazon Nova Micro vía Bedrock, con el Strands Agents SDK)
> solo hace lo que un LLM debe hacer: extraer estructura de texto
> ambiguo y redactar la explicación. El score, los thresholds, la
> severidad de los gaps y la recomendación APPLY/MAYBE/SKIP son
> 100% deterministas — un policy module centralizado, no una opinion
> del modelo."

Mencionar las 5 tools del agente (analyze_job, normalize_skills,
calculate_match, identify_skill_gaps, generate_interview_plan) y la
separación FastAPI/UI/PostgreSQL local vs core reutilizable.

## 4. Reliability — evals (2:45-3:15)

> "¿Cómo sabemos que no alucina? Ejecutamos un eval suite de 25 casos
> en 8 categorías: evidencia fabricada conservada — cero, en todos
> los casos. Recomendación correcta: 92% con el modelo más barato de
> Bedrock. Y el tier determinista es 100% reproducible y corre gratis
> en CI."

Mostrar `dist/evals/report.md` o el bloque de resultados del README.

## 5. Impact y cierre (3:15-3:40)

> "Para un junior buscando su primer trabajo, esto convierte una
> decisión ansiosa y opaca en una evaluación con evidencia: dónde
> estás fuerte, qué te falta exactamente, y cómo prepararlo antes de
> la entrevista."

Cierre: repo + stack en pantalla.

---

## Checklist de grabación

- [ ] Terminal/HTTP con la app corriendo de antemano (no instalar en video)
- [ ] `make eval` ejecutado antes para tener el reporte fresco
- [ ] Navegador en ventana limpia, zoom legible
- [ ] No mostrar credenciales ni `.env`
- [ ] Capturar a 1080p+; el score ring y el evidence list deben leerse
