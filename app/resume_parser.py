"""Resume parsing: PDF or TXT bytes to cleaned plain text.

The public interface is parse_resume(data, filename), designed so new
formats (for example DOCX) only need a new extraction branch, and the
security validations (extension, size, emptiness, corruption) stay
shared across every format.
"""

import io
import os
import re
from pathlib import Path

from pypdf import PdfReader
from pypdf.errors import PdfReadError

SUPPORTED_EXTENSIONS = (".pdf", ".txt")
DEFAULT_MAX_SIZE_MB = 5.0


class ResumeParseError(ValueError):
    """Base error for any resume that cannot be parsed."""


class UnsupportedResumeFormatError(ResumeParseError):
    """The file extension is not supported."""


class ResumeTooLargeError(ResumeParseError):
    """The file exceeds the configured maximum size."""


class EmptyResumeError(ResumeParseError):
    """The file has no content."""


def max_resume_size_bytes() -> int:
    """Maximum accepted resume size in bytes (RESUME_MAX_SIZE_MB, default 5)."""
    try:
        max_mb = float(os.getenv("RESUME_MAX_SIZE_MB", str(DEFAULT_MAX_SIZE_MB)))
    except ValueError:
        max_mb = DEFAULT_MAX_SIZE_MB
    return int(max_mb * 1024 * 1024)


def parse_resume(data: bytes, filename: str, max_size_bytes: int | None = None) -> str:
    """Validate and parse a resume file into cleaned plain text.

    Args:
        data: Raw file bytes.
        filename: Original filename, used to select the parser.
        max_size_bytes: Size limit override; defaults to RESUME_MAX_SIZE_MB.

    Returns:
        Cleaned resume text, ready for CandidateProfile extraction.

    Raises:
        UnsupportedResumeFormatError: Extension is not .pdf or .txt.
        ResumeTooLargeError: File is larger than the limit.
        EmptyResumeError: File is empty.
        ResumeParseError: File is corrupt or contains no extractable text.
    """
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise UnsupportedResumeFormatError(
            f"Unsupported resume format '{extension or filename}'. "
            f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}."
        )

    limit = max_size_bytes if max_size_bytes is not None else max_resume_size_bytes()
    if not data:
        raise EmptyResumeError("Resume file is empty.")
    if len(data) > limit:
        raise ResumeTooLargeError(
            f"Resume file is {len(data)} bytes; maximum is {limit} bytes."
        )

    if extension == ".pdf":
        text = _extract_pdf_text(data)
    else:
        text = _decode_text(data)

    cleaned = clean_text(text)
    if not cleaned:
        raise ResumeParseError(
            "No extractable text found in the resume "
            "(the PDF may be scanned or image-based)."
        )
    return cleaned


def _extract_pdf_text(data: bytes) -> str:
    if not data.startswith(b"%PDF"):
        raise ResumeParseError("File does not look like a valid PDF.")
    try:
        reader = PdfReader(io.BytesIO(data))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfReadError as exc:
        raise ResumeParseError(f"Corrupt or unreadable PDF: {exc}") from exc


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1")


def clean_text(text: str) -> str:
    """Normalize whitespace and strip control characters from extracted text."""
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
