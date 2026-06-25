#!/usr/bin/env python3
"""Validate DATABASE_URL in .env.production without leaking secrets."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]


def validate_env_file(env_path: Path) -> dict[str, str | bool]:
    if not env_path.is_file():
        return {
            "database_url_present": False,
            "scheme_postgresql": False,
            "database_name": "",
            "database_name_ok": False,
            "error": "env_file_missing",
        }
    url = ""
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or not stripped.startswith("DATABASE_URL="):
            continue
        url = stripped.split("=", 1)[1].strip().strip('"').strip("'")
        break
    parsed = urlparse(url)
    db_name = (parsed.path or "").lstrip("/")
    return {
        "database_url_present": bool(url),
        "scheme_postgresql": url.startswith("postgresql:") or url.startswith("postgres:"),
        "database_name": db_name if db_name else "(none)",
        "database_name_ok": db_name == "worldcup_predictor",
        "env_path": str(env_path),
    }


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/worldcup-predictor/.env.production")
    report = validate_env_file(env_path)
    print("DATABASE_URL validation (secrets redacted):")
    print(f"  DATABASE_URL present: {'YES' if report['database_url_present'] else 'NO'}")
    print(f"  scheme starts with postgresql: {'YES' if report['scheme_postgresql'] else 'NO'}")
    print(f"  database name detected: {report['database_name']}")
    out_path = ROOT / "artifacts" / "phase54f5_server_xg_import" / "database_url_validation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    ok = bool(report["database_url_present"] and report["scheme_postgresql"] and report["database_name_ok"])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
