#!/usr/bin/env python3
"""WC-DAILY-WDE-INPUTS — Fix SQLite lock, import WC fixtures, refresh odds, generate WDE, re-report."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.owner_daily.constants import GENERATED_BY
from worldcup_predictor.owner_daily.cycle import DailyCycleConfig, run_daily_owner_cycle
from worldcup_predictor.owner_daily.provider_call_log import DailyProviderCallLog, ProviderQuotaGuard
from worldcup_predictor.owner_daily.wc_fixture_import import WC_TODAY_FIXTURE_IDS, import_wc_fixtures_for_date

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PHASE = "WC-DAILY-WDE-INPUTS"
ARTIFACTS = Path("artifacts")
TARGET_DATE = date(2026, 6, 30)
BEFORE_REPORT = ROOT / "reports" / "owner" / "wc_today_predictions_20260630.json"


def _python_processes() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        import psutil  # type: ignore

        for proc in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
            name = (proc.info.get("name") or "").lower()
            if "python" not in name and "streamlit" not in name:
                continue
            cmdline = proc.info.get("cmdline") or []
            text = " ".join(str(x) for x in cmdline)
            if "Footbal" not in text and "football_intelligence" not in text and "streamlit" not in text.lower():
                continue
            rows.append({"pid": proc.info.get("pid"), "name": proc.info.get("name"), "cmdline": text})
    except ImportError:
        pass
    if not rows and sys.platform == "win32":
        try:
            out = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "Get-CimInstance Win32_Process -Filter \"name='python.exe'\" | "
                    "Select-Object ProcessId,CommandLine | ConvertTo-Json",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
            )
            data = json.loads(out) if out.strip() else []
            if isinstance(data, dict):
                data = [data]
            for item in data:
                cmd = str(item.get("CommandLine") or "")
                if "Footbal" in cmd:
                    rows.append({"pid": item.get("ProcessId"), "name": "python.exe", "cmdline": cmd})
        except (subprocess.CalledProcessError, json.JSONDecodeError, FileNotFoundError):
            pass
    return rows


def diagnose_sqlite_lock() -> dict[str, Any]:
    settings = get_settings()
    db_path = get_db_path(settings.sqlite_path)
    procs = _python_processes()
    stale = [
        p
        for p in procs
        if p.get("cmdline")
        and (
            "_import_wc_today_fixtures.py" in str(p["cmdline"])
            or "watch_uefa_odds_readiness.py" in str(p["cmdline"])
        )
    ]
    diagnosis: dict[str, Any] = {
        "phase": PHASE,
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "wal_files": {
            "wal": db_path.with_suffix(db_path.suffix + "-wal").exists(),
            "shm": db_path.with_suffix(db_path.suffix + "-shm").exists(),
        },
        "relevant_processes": procs,
        "stale_import_processes": stale,
        "journal_mode": None,
        "busy_timeout_ms": None,
        "lock_type": "unknown",
        "safe_action": "retry_with_busy_timeout",
    }
    if db_path.exists():
        try:
            conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=5.0)
            diagnosis["journal_mode"] = conn.execute("PRAGMA journal_mode").fetchone()[0]
            diagnosis["busy_timeout_ms"] = conn.execute("PRAGMA busy_timeout").fetchone()[0]
            conn.close()
        except sqlite3.Error as exc:
            diagnosis["read_error"] = str(exc)
            diagnosis["lock_type"] = "read_blocked"
    if stale:
        diagnosis["lock_type"] = "stale_hung_import_script"
        diagnosis["safe_action"] = "stop_stale_import_process_then_retry"
    return diagnosis


def _stop_stale_processes(diagnosis: dict[str, Any]) -> list[int]:
    stopped: list[int] = []
    for proc in diagnosis.get("stale_import_processes") or []:
        pid = proc.get("pid")
        if not pid:
            continue
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid), "/F"], check=False, capture_output=True)
            else:
                subprocess.run(["kill", "-9", str(pid)], check=False, capture_output=True)
            stopped.append(int(pid))
        except (OSError, ValueError):
            pass
    return stopped


def _load_report_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("summary") or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _wde_count_for_fixtures(fixture_ids: tuple[int, ...]) -> dict[str, Any]:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    out: dict[str, Any] = {"with_wde": 0, "fixtures": {}}
    for fid in fixture_ids:
        row = conn.execute(
            "SELECT source, payload_json FROM worldcup_stored_predictions WHERE fixture_id = ? LIMIT 1",
            (fid,),
        ).fetchone()
        has = False
        pick = None
        if row and row["payload_json"]:
            try:
                payload = json.loads(row["payload_json"])
                pick = (payload.get("one_x_two") or {}).get("selection")
                has = bool(row["source"] == GENERATED_BY or payload.get("generated_by") == GENERATED_BY or pick)
            except json.JSONDecodeError:
                has = True
        out["fixtures"][str(fid)] = {"has_wde": has, "wde_1x2": pick, "source": row["source"] if row else None}
        if has:
            out["with_wde"] += 1
    conn.close()
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="WC daily WDE inputs hotfix")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="Overwrite existing owner WDE")
    parser.add_argument("--skip-import", action="store_true")
    parser.add_argument("--skip-owner-cycle", action="store_true")
    args = parser.parse_args()

    before_summary = _load_report_summary(BEFORE_REPORT)
    before_wde = _wde_count_for_fixtures(WC_TODAY_FIXTURE_IDS)

    diagnosis = diagnose_sqlite_lock()
    stopped_pids = _stop_stale_processes(diagnosis)
    diagnosis["stopped_stale_pids"] = stopped_pids

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    diag_path = ARTIFACTS / "wc_daily_sqlite_lock_diagnosis.json"
    diag_path.write_text(json.dumps(diagnosis, indent=2, ensure_ascii=False), encoding="utf-8")

    import_result: dict[str, Any] = {}
    if not args.skip_import:
        call_log = DailyProviderCallLog(
            run_date=TARGET_DATE.isoformat(),
            quota=ProviderQuotaGuard(max_api_football=100, max_oddalerts=100, max_sportmonks=100),
        )
        imp = import_wc_fixtures_for_date(
            TARGET_DATE,
            call_log=call_log,
            dry_run=args.dry_run,
            force_refresh=False,
        )
        log_path = call_log.flush()
        import_result = imp.to_dict()
        import_result["provider_log"] = str(log_path)

    cycle_result: dict[str, Any] = {}
    if not args.skip_owner_cycle and not args.dry_run:
        cycle = run_daily_owner_cycle(
            DailyCycleConfig(
                date_arg=TARGET_DATE.isoformat(),
                timezone="Europe/Vienna",
                competition_keys=["world_cup_2026"],
                limit=10,
                fetch_missing_odds=True,
                include_shadow=True,
                force_predictions=args.force,
                max_api_football_calls=100,
                max_oddalerts_calls=100,
                max_sportmonks_calls=100,
            )
        )
        cycle_result = cycle.to_dict()
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "build_wc_today_owner_report.py")],
            cwd=ROOT,
            check=False,
        )

    after_summary = _load_report_summary(BEFORE_REPORT)
    after_wde = _wde_count_for_fixtures(WC_TODAY_FIXTURE_IDS)

    hotfix_artifact = {
        "phase": PHASE,
        "diagnosis_path": str(diag_path),
        "import": import_result,
        "cycle": cycle_result,
        "before": {"report_summary": before_summary, "wde": before_wde},
        "after": {"report_summary": after_summary, "wde": after_wde},
    }
    out_path = ARTIFACTS / "wc_daily_wde_inputs_hotfix.json"
    out_path.write_text(json.dumps(hotfix_artifact, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(hotfix_artifact, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
