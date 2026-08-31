# Screenshots

Capturas requeridas para el README y la submission. **No hay capturas
generadas/artificiales en este repo**: tomarlas desde la aplicación
real ejecutándose (`make run` + credenciales AWS para Bedrock).

## Lista

| Archivo | Contenido | Cómo capturarla |
|---|---|---|
| `01-home.png` | UI vacía: pestañas Paste text / Upload file, textarea de vacante, botones Load example y Analyze | `make run` → http://127.0.0.1:8000/ → captura completa del viewport |
| `02-cv-upload.png` | Pestaña Upload file con un PDF seleccionado y el nombre visible ("Selected: cv.pdf") | pestaña Upload file → elegir PDF (p. ej. un PDF generado desde `examples/demo_resume.txt`) |
| `03-evaluation-result.png` | Resultado de la demo: badge APPLY, score ring 80, matched skills, evidence verbatim | Load example → Analyze → esperar resultado → captura del bloque superior del resultado |
| `04-skill-gaps.png` | Gaps agrupados por severidad: aws (required), ci/cd y kubernetes (preferred), con preparation steps | scroll del resultado de la misma evaluación → sección Skill gaps |
| `05-interview-plan.png` | Interview topics + preparation plan | scroll → sección de interview preparation |
| `06-eval-results.png` | Reporte del eval suite (tier determinista + LLM) | `make eval` → captura de la terminal o de `dist/evals/report.md` renderizado |

## Convenciones

- Ventana del navegador limpia (sin bookmarks bar), 1080p+, zoom 100%.
- Para 03-05 usar la demo completa (`docs/DEMO.md`): produce APPLY 80
  con gap de AWS — la misma evaluación alimenta tres capturas.
- Una vez capturadas, colocarlas aquí y referenciarlas desde el
  README (sección Screenshots).
