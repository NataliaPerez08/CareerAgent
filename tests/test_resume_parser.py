import pytest

from app.resume_parser import (
    EmptyResumeError,
    ResumeParseError,
    ResumeTooLargeError,
    UnsupportedResumeFormatError,
    clean_text,
    max_resume_size_bytes,
    parse_resume,
)
from tests.pdfgen import make_pdf

RESUME_LINES = [
    "Backend developer with 2 years of professional software development experience.",
    "Skills and evidence:",
    "- Python for backend services and automation.",
    "- REST API design and integration.",
    "- PostgreSQL for relational persistence.",
]


def test_parse_pdf_resume_extracts_clean_text():
    pdf = make_pdf(RESUME_LINES)

    text = parse_resume(pdf, "resume.pdf")

    assert "Backend developer with 2 years" in text
    assert "Python for backend services" in text
    assert "PostgreSQL for relational persistence" in text
    assert "\n\n\n" not in text


def test_parse_txt_resume_decodes_and_cleans():
    raw = "Backend developer.\r\n\r\n\r\nPython   and   Docker.\x00"

    text = parse_resume(raw.encode("utf-8"), "resume.txt")

    assert text == "Backend developer.\n\nPython and Docker."


def test_parse_txt_resume_latin1_fallback():
    text = parse_resume("Café con PostgreSQL".encode("latin-1"), "resume.txt")

    assert "PostgreSQL" in text


def test_unsupported_extension_is_rejected():
    with pytest.raises(UnsupportedResumeFormatError, match="Supported"):
        parse_resume(b"whatever", "resume.docx")


def test_empty_file_is_rejected():
    with pytest.raises(EmptyResumeError, match="empty"):
        parse_resume(b"", "resume.pdf")


def test_oversized_file_is_rejected():
    with pytest.raises(ResumeTooLargeError, match="maximum"):
        parse_resume(b"x" * 100, "resume.pdf", max_size_bytes=10)


def test_corrupt_pdf_is_rejected():
    with pytest.raises(ResumeParseError, match="Corrupt or unreadable"):
        parse_resume(b"%PDF-1.4 totally broken content", "resume.pdf")


def test_pdf_with_wrong_magic_bytes_is_rejected():
    with pytest.raises(ResumeParseError, match="valid PDF"):
        parse_resume(b"not a pdf at all", "resume.pdf")


def test_scanned_pdf_without_text_is_rejected():
    blank_pdf = make_pdf([])

    with pytest.raises(ResumeParseError, match="scanned or image-based"):
        parse_resume(blank_pdf, "resume.pdf")


def test_clean_text_strips_control_characters_and_collapses_whitespace():
    cleaned = clean_text("Line  one\x0b\x0c\x00\n\n\n\nLine    two\n\n\n")

    assert cleaned == "Line one\n\nLine two"


def test_max_resume_size_default():
    assert max_resume_size_bytes() == 5 * 1024 * 1024
