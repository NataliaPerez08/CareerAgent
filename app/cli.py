from pathlib import Path

from app.service import evaluate_candidate

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    resume = (ROOT / "examples" / "resume.txt").read_text()
    job = (ROOT / "examples" / "job.txt").read_text()
    result = evaluate_candidate(resume, job)
    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
