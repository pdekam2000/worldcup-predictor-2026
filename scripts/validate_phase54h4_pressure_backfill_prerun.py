#!/usr/bin/env python3
"""Phase 54H-4 pre-run server checks (secret-safe)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h4_pressure_backfill_batch1"
ENV_PATH = Path("/opt/worldcup-predictor/.env.production")
CACHE_DIR = Path("/opt/worldcup-predictor/data/feature_store/sportmonks_pressure/raw")

TOKEN_RE = re.compile(r"(api_token|SPORTMONKS_API_TOKEN)=[^&\s\"']+", re.I)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def _env_var_present(name: str) -> tuple[bool, int]:
    if not ENV_PATH.is_file():
        return False, 0
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith(f"{name}="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            return bool(val), len(val)
    return False, 0


def main() -> int:
    checks: list[dict] = []
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    db_path = ENV_PATH if ENV_PATH.is_file() else ROOT / ".env.production"
    if not db_path.is_file():
        db_path = ROOT / ".env"
    db_url_present = False
    db_name_ok = False
    db_name = ""
    if db_path.is_file():
        from urllib.parse import urlparse

        url = ""
        for line in db_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("DATABASE_URL="):
                url = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
        db_url_present = bool(url)
        parsed = urlparse(url)
        db_name = (parsed.path or "").lstrip("/")
        db_name_ok = db_name == "worldcup_predictor"
    checks.append(_check("database_url_present", db_url_present, db_name or "missing"))
    checks.append(_check("database_name_ok", db_name_ok, db_name))

    tok_present, tok_len = _env_var_present("SPORTMONKS_API_TOKEN")
    checks.append(_check("sportmonks_token_present", tok_present, f"length={tok_len}" if tok_present else "missing"))

    tables_ok = False
    fixture_count = 0
    try:
        from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository

        repo = SportmonksPressureRepository()
        audit = repo.audit_coverage()
        tables_ok = bool(audit.get("tables_ready"))
        fixture_count = int((audit.get("records") or {}).get("fixture_count") or 0)
        checks.append(_check("pressure_tables_ready", tables_ok))
        checks.append(_check("pressure_fixture_count_readable", fixture_count >= 0, f"count={fixture_count}"))
    except Exception as exc:
        checks.append(_check("pressure_tables_ready", False, str(exc)[:120]))

    cache_writable = False
    try:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        probe = CACHE_DIR / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        cache_writable = True
    except OSError as exc:
        checks.append(_check("cache_dir_writable", False, str(exc)[:80]))
    if cache_writable:
        checks.append(_check("cache_dir_writable", True, str(CACHE_DIR)))

    # Token probe without printing token
    probe_ok = False
    if tok_present:
        import subprocess

        probe_script = ROOT / "scripts" / "_phase54h3_server_probe_run.sh"
        if probe_script.is_file():
            proc = subprocess.run(["bash", str(probe_script)], capture_output=True, text=True, timeout=60, check=False)
            probe_ok = "SERVER_HTTP_STATUS=200" in proc.stdout and "SERVER_PRESSURE_ROWS" in proc.stdout
            if TOKEN_RE.search(proc.stdout):
                checks.append(_check("no_token_in_probe_output", False))
            else:
                checks.append(_check("no_token_in_probe_output", True))
        checks.append(_check("pressure_include_probe", probe_ok))

    out = {
        "phase": "54H-4",
        "pre_run_fixture_count": fixture_count,
        "checks": checks,
        "all_pass": all(c["pass"] for c in checks),
    }
    (ARTIFACT_DIR / "prerun_validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    passed = sum(1 for c in checks if c["pass"])
    print(f"PRERUN: {passed}/{len(checks)} PASS fixtures_before={fixture_count}")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
