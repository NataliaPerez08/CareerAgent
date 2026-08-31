"""CLI entry point for the CareerAgent eval suite.

Usage:
    python scripts/run_evals.py
    python scripts/run_evals.py --tier llm
    python scripts/run_evals.py --tier llm --cases 5 --tools-sample 1
    python scripts/run_evals.py --tier all
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.evals.runner import main

if __name__ == "__main__":
    sys.exit(main())
