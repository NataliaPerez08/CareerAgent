from pathlib import Path

from app import cli
from app.schemas import EvaluationResult
from tests.pdfgen import make_pdf

RESUME_LINES = [
    "Backend developer with 2 years of professional software development experience.",
    "- Python for backend services and automation.",
    "- REST API design and integration.",
    "- PostgreSQL for relational persistence.",
    "- Docker for local development and deployment packaging.",
]


def test_cli_defaults_use_examples(monkeypatch):
    captured = {}

    def fake_evaluate(resume, job_description):
        captured["resume"] = resume
        captured["job"] = job_description
        return EvaluationResult(recommendation="APPLY", score=100)

    monkeypatch.setattr(cli, "evaluate_candidate", fake_evaluate)

    cli.main([])

    assert "Backend developer with 2 years" in captured["resume"]
    assert "Junior Backend Engineer" in captured["job"]


def test_cli_accepts_pdf_resume_argument(monkeypatch, tmp_path):
    captured = {}

    def fake_evaluate(resume, job_description):
        captured["resume"] = resume
        captured["job"] = job_description
        return EvaluationResult(recommendation="APPLY", score=100)

    monkeypatch.setattr(cli, "evaluate_candidate", fake_evaluate)

    resume_pdf = tmp_path / "resume.pdf"
    resume_pdf.write_bytes(make_pdf(RESUME_LINES))
    job_txt = tmp_path / "job.txt"
    job_txt.write_text("Junior Backend Engineer. Requires Python and Docker.")

    cli.main([str(resume_pdf), str(job_txt)])

    assert "Backend developer with 2 years" in captured["resume"]
    assert "Python for backend services" in captured["resume"]
    assert "Junior Backend Engineer" in captured["job"]


def test_cli_rejects_unsupported_resume_format(tmp_path):
    docx = tmp_path / "resume.docx"
    docx.write_bytes(b"fake docx")

    try:
        cli.main([str(docx)])
    except ValueError as exc:
        assert "Supported" in str(exc)
    else:
        raise AssertionError("expected unsupported format error")


def test_examples_resume_exists():
    assert (Path(cli.ROOT) / "examples" / "resume.txt").exists()
    assert (Path(cli.ROOT) / "examples" / "job.txt").exists()


def test_cli_chat_mode_runs_agent_workflow(monkeypatch, capsys):
    captured = {}

    def fake_run_agent_workflow(resume_text, job_text):
        captured["resume"] = resume_text
        captured["job"] = job_text
        return "RECOMMENDATION: APPLY (agent workflow demo)"

    monkeypatch.setattr(cli, "run_agent_workflow", fake_run_agent_workflow)

    cli.main(["--chat"])

    assert "Backend developer with 2 years" in captured["resume"]
    assert "Junior Backend Engineer" in captured["job"]
    assert "RECOMMENDATION: APPLY" in capsys.readouterr().out


def test_cli_chat_mode_uses_passed_files(monkeypatch, tmp_path):
    captured = {}

    def fake_run_agent_workflow(resume_text, job_text):
        captured["resume"] = resume_text
        captured["job"] = job_text
        return "answer"

    monkeypatch.setattr(cli, "run_agent_workflow", fake_run_agent_workflow)

    resume_txt = tmp_path / "resume.txt"
    resume_txt.write_text("Backend developer with 2 years of experience. Python.")
    job_txt = tmp_path / "job.txt"
    job_txt.write_text("Junior backend engineer. Requires Python.")

    cli.main([str(resume_txt), str(job_txt), "--chat"])

    assert "Python." in captured["resume"]
    assert "Requires Python" in captured["job"]
