#!/usr/bin/env python3
"""Repair .env.production when DATABASE_URL is embedded in a comment line."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def repair_env_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines: list[str] = []
    fixed = False
    for line in lines:
        if "DATABASE_URL=" in line and line.strip().startswith("#"):
            match = re.search(r"(DATABASE_URL=.+)$", line)
            if match:
                new_lines.append("# PostgreSQL (required — SaaS auth, users, subscriptions)")
                new_lines.append(match.group(1))
                fixed = True
                continue
        new_lines.append(line)
    if fixed:
        path.write_text("\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8")
    return fixed


def validate_database_url(env_path: Path) -> dict[str, str | bool]:
    text = env_path.read_text(encoding="utf-8")
    url = ""
    for line in text.splitlines():
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
        "database_name": db_name,
        "database_name_ok": db_name == "worldcup_predictor",
        "fixed_file": str(env_path),
    }


def main() -> int:
    env_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/worldcup-predictor/.env.production")
    if not env_path.is_file():
        print(json_dumps({"error": "env_file_missing", "path": str(env_path)}))
        return 1
    repaired = repair_env_file(env_path)
    report = validate_database_url(env_path)
    report["repaired"] = repaired
    print(json_dumps(report))
    ok = bool(report["database_url_present"] and report["scheme_postgresql"] and report["database_name_ok"])
    return 0 if ok else 1


def json_dumps(obj: dict) -> str:
    import json

    return json.dumps(obj, indent=2)


if __name__ == "__main__":
    raise SystemExit(main())
