#!/usr/bin/env python3
"""PHASE ECSE-LIVE-1 — Win2Day smoke test via live provider APIs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.ecse_live.runner import run_ecse_provider_snapshot_runner
from worldcup_predictor.research.ecse_live.smoke_targets import WIN2DAY_SMOKE_TARGETS, targets_as_dicts
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables

REPORT_PATH = ROOT / "ECSE_LIVE_1_REPORT.md"
ARTIFACT_PATH = ROOT / "artifacts" / "ecse_live_1_smoke.json"


def _write_report(payload: dict) -> None:
    lines = [
        "# ECSE-LIVE-1 — Live API Prediction Snapshot Report",
        "",
        f"**Phase:** ECSE-LIVE-1  ",
        f"**Mode:** Internal smoke — Win2Day targets  ",
        f"**Status:** {payload.get('status', 'ok')}  ",
        "",
        "## Summary",
        "",
        f"- Targets: **{payload.get('count', 0)}**",
        f"- Frozen: **{payload.get('frozen', 0)}**",
        f"- Already frozen: **{payload.get('already_frozen', 0)}**",
        f"- Failed / skipped: **{payload.get('count', 0) - payload.get('frozen', 0) - payload.get('already_frozen', 0)}**",
        "",
        "## Fixture Results",
        "",
        "| Match | Fixture ID | Status | Top-1 | Providers |",
        "|-------|------------|--------|-------|-----------|",
    ]
    for row in payload.get("results") or []:
        match = f"{row.get('home_team')} vs {row.get('away_team')}"
        fid = row.get("fixture_id") or "—"
        status = row.get("status") or "—"
        top1 = row.get("top_1_score") or "—"
        cov = row.get("coverage") or {}
        prov = ", ".join(cov.keys()) if cov else "—"
        lines.append(f"| {match} | {fid} | {status} | {top1} | {prov} |")

    lines.extend(
        [
            "",
            "## Provider Coverage Detail",
            "",
        ]
    )
    for row in payload.get("results") or []:
        lines.append(f"### {row.get('home_team')} vs {row.get('away_team')}")
        resolved = row.get("resolved") or {}
        lines.append(f"- API-Football: `{resolved.get('fixture_id')}`")
        lines.append(f"- Sportmonks: `{resolved.get('sportmonks_fixture_id')}`")
        lines.append(f"- OddAlerts: `{resolved.get('oddalerts_fixture_id')}`")
        lines.append(f"- Coverage: `{json.dumps(row.get('coverage') or {}, default=str)}`")
        if row.get("top_10"):
            lines.append(f"- Top 10: `{', '.join(row['top_10'])}`")
        api_log = (row.get("api_log") or {}).get("api_calls")
        if api_log is not None:
            lines.append(f"- API calls (fixture): **{api_log}**")
        lines.append("")

    lines.extend(
        [
            "## Safety",
            "",
            "- WDE / EGIE production prediction logic unchanged",
            "- Snapshots frozen once per `fixture_id`",
            "- No public API exposure",
            "",
            "## Artifacts",
            "",
            f"- `{ARTIFACT_PATH.as_posix()}`",
            "",
        ]
    )
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="ECSE-LIVE-1 Win2Day provider smoke test")
    parser.add_argument("--force", action="store_true", help="Attempt insert even if snapshot exists")
    parser.add_argument("--dry-run", action="store_true", help="No snapshot writes")
    args = parser.parse_args()

    settings = get_settings()
    if args.dry_run:
        settings = settings.model_copy(update={"ecse_live_dry_run": True})

    conn = connect(get_db_path(settings.sqlite_path))
    ensure_ecse_live_tables(conn)
    try:
        report = run_ecse_provider_snapshot_runner(
            conn,
            settings=settings,
            targets=targets_as_dicts(),
            force=args.force,
            skip_window=True,
        )
        report["status"] = "ok"
        report["targets"] = [t.display for t in WIN2DAY_SMOKE_TARGETS]
    finally:
        conn.close()

    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _write_report(report)

    print(json.dumps(report, indent=2, default=str))
    print(f"\nWrote {ARTIFACT_PATH}")
    print(f"Wrote {REPORT_PATH}")

    ok_statuses = {"frozen", "already_frozen", "dry_run"}
    failed = [r for r in report.get("results", []) if r.get("status") not in ok_statuses]
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
