"""Embedded PostgreSQL for local development (Windows-friendly, no system install)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pgembed

DATA_DIR = Path(__file__).resolve().parents[1] / "data" / "pgembed_dev"
URL_FILE = DATA_DIR / "database.url"

_server = None


def start_server() -> str:
    global _server
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    _server = pgembed.get_server(str(DATA_DIR.resolve()))
    uri = _server.get_uri()
    URL_FILE.write_text(uri + "\n", encoding="utf-8")
    return uri


def read_url() -> str | None:
    if URL_FILE.exists():
        text = URL_FILE.read_text(encoding="utf-8").strip()
        return text or None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Local embedded PostgreSQL via pgembed")
    parser.add_argument("--print-url", action="store_true", help="Print connection URL and exit")
    parser.add_argument("--hold", action="store_true", help="Keep server running until Ctrl+C")
    args = parser.parse_args()

    uri = start_server()
    print(uri)
    if args.print_url and not args.hold:
        return 0
    if args.hold:
        print("Embedded PostgreSQL running. Press Ctrl+C to stop.", file=sys.stderr)
        try:
            import time

            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            if _server is not None:
                _server.cleanup()
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
