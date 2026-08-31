# ADR-0002: Resume parsing y job input paste-first (v0.3)

## Estado

Accepted

## Contexto

v0.2 aceptaba solo texto plano. Para una demo real del hackathon el sistema
debe aceptar un CV en PDF, y la vacante llega como texto pegado. AGENTS.md
exige validaciones de seguridad (tipo, tamaño, vacío, corrupto) y permite
URL de vacante solo si no introduce scraping frágil.

## Decisión

**Parser de CV** (`app/resume_parser.py`):

- `parse_resume(data, filename)` como única interfaz pública; dispatch por
  extensión (`.pdf`, `.txt`). Agregar DOCX después es una rama nueva sin
  tocar las validaciones compartidas.
- Extracción PDF con **pypdf** (BSD, pura Python, sin dependencias nativas;
  se descartó PyMuPDF por licencia AGPL en proyecto Apache-2.0).
- Validaciones en orden: extensión soportada → archivo vacío → tamaño
  (`RESUME_MAX_SIZE_MB`, default 5 MB) → magic bytes `%PDF` → parseo →
  texto extraíble no vacío.
- PDFs escaneados (sin texto) se reportan explícitamente en vez de devolver
  texto vacío silenciosamente.
- `clean_text` normaliza: control chars fuera, whitespace colapsado, máximo
  una línea en blanco entre párrafos.

**Job input paste-first**: la vacante sigue siendo texto plano en todos los
contratos (CLI, API JSON, API multipart). La extracción por URL queda
diferida: el fetch genérico de URLs de empleo es frágil (JS, anti-bot) y
AGENTS.md prohíbe invertir fase en vencerlo. Agregarla más adelante no
requiere cambios de interfaz.

**Errores tipados** para mapeo HTTP: `UnsupportedResumeFormatError` → 415,
`ResumeTooLargeError` → 413, `EmptyResumeError`/`ResumeParseError` → 422.

## Consecuencias

- El upload lee con tope de bytes (`max_resume_size_bytes() + 1`) antes de
  delegar al parser, evitando lecturas no acotadas.
- Tests de parser/API generan PDFs deterministas en memoria
  (`tests/pdfgen.py`): sin fixtures binarios ni dependencias extra.
- OCR para PDFs escaneados queda explícitamente fuera (post-hackathon).
