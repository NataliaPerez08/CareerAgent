import argparse
from pathlib import Path

from app.agent import run_agent_workflow
from app.job_ingestion import JobFetchError, fetch_job
from app.resume_parser import parse_resume
from app.service import evaluate_candidate

ROOT = Path(__file__).resolve().parents[1]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate a resume against a job description.",
    )
    parser.add_argument(
        "resume",
        nargs="?",
        default=None,
        help="Path to a resume file (PDF or TXT). Defaults to examples/demo_resume.txt.",
    )
    parser.add_argument(
        "job",
        nargs="?",
        default=None,
        help="Path to a job description text file. Defaults to examples/demo_job.txt.",
    )
    parser.add_argument(
        "--job-url",
        default=None,
        help="Fetch the job description from a URL instead of a file.",
    )
    parser.add_argument(
        "--chat",
        action="store_true",
        help=(
            "Demo mode: run the Strands agent free loop through the five-tool "
            "workflow instead of the structured pipeline."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    resume_path = Path(args.resume) if args.resume else ROOT / "examples" / "demo_resume.txt"

    resume_text = parse_resume(resume_path.read_bytes(), resume_path.name)

    if args.job_url:
        try:
            job_text = fetch_job(args.job_url).description
        except JobFetchError as exc:
            msg = str(exc).strip()
            if not msg:
                msg = exc.__class__.__name__
            print(f"Job URL error: {msg}")
            raise SystemExit(2) from exc
    else:
        job_path = Path(args.job) if args.job else ROOT / "examples" / "demo_job.txt"
        job_text = job_path.read_text()

    if args.chat:
        print(run_agent_workflow(resume_text, job_text))
        return

    result = evaluate_candidate(resume_text, job_text)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
