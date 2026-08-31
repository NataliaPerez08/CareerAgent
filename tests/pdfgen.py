"""Minimal deterministic PDF generator for tests.

Builds a single-page PDF with one text object per line, using a
standard Type1 font, so pypdf can extract the text without any
external dependency or fixture file.
"""

_PDF_TEMPLATE_OBJECTS = {
    1: b"<< /Type /Catalog /Pages 2 0 R >>",
    2: b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    3: (
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
    ),
    5: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
}


def _escape(line: str) -> str:
    return (
        line.replace("\\", r"\\")
        .replace("(", r"\(")
        .replace(")", r"\)")
        .encode("latin-1", "replace")
        .decode("latin-1")
    )


def make_pdf(lines: list[str]) -> bytes:
    """Return the bytes of a one-page PDF rendering each line of text."""
    content = []
    y = 720
    for line in lines:
        content.append(f"BT /F1 12 Tf 72 {y} Td ({_escape(line)}) Tj ET")
        y -= 20
    stream = "\n".join(content).encode("latin-1")

    objects = dict(_PDF_TEMPLATE_OBJECTS)
    objects[4] = (
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream
        + b"\nendstream"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets = {}
    for num in sorted(objects):
        offsets[num] = len(out)
        out += f"{num} 0 obj\n".encode() + objects[num] + b"\nendobj\n"

    xref_pos = len(out)
    out += b"xref\n0 6\n0000000000 65535 f \n"
    for num in sorted(objects):
        out += f"{offsets[num]:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n"
        + str(xref_pos).encode()
        + b"\n%%EOF"
    )
    return bytes(out)
