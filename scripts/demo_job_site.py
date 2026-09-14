"""Serve the local demo job board (demo/) over HTTP.

Used to record the CareerAgent demo without relying on live job sites or
scraping: /api/v1/jobs/fetch can read localhost URLs when the API process
runs with ``JOB_FETCH_ALLOW_PRIVATE_HOSTS=1``. Demo-only flag — never enable
it for anything else.

    python scripts/demo_job_site.py            # serves demo/ on port 8001
    python scripts/demo_job_site.py --port 8080
"""

from __future__ import annotations

import argparse
import functools
import http.server
from pathlib import Path

DEMO_DIR = Path(__file__).resolve().parent.parent / "demo"


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the local demo job board.")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    if not DEMO_DIR.is_dir():
        raise SystemExit(f"demo directory not found: {DEMO_DIR}")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(DEMO_DIR))
    with http.server.ThreadingHTTPServer(("127.0.0.1", args.port), handler) as server:
        print(f"Demo job board at http://127.0.0.1:{args.port} (serving {DEMO_DIR})")
        print(f"Index: http://127.0.0.1:{args.port}/")
        print("Point the API at this board with `make demo-run` "
              "(starts the API with JOB_FETCH_ALLOW_PRIVATE_HOSTS=1).")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped")


if __name__ == "__main__":
    main()
