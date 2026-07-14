#!/usr/bin/env python3
"""Dry-run classifier for forward evaluation freeze candidates — read-only by default."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.forward_evaluation.freeze_service import create_or_reuse_freeze
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables

CATEGORIES = (
    "ELIGIBLE_FREEZE",
    "MISSING_WSP",
    "MISSING_ECSE",
    "POST_KICKOFF_SOURCE",
    "MISSING_TIMESTAMP",
    "INVALID_QUALITY",
    "INVALID_ODDS_FRESHNESS",
    "SOURCE_CONFLICT",
    "DUPLICATE_IDENTICAL",
    "QUARANTINE_REQUIRED",
)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _classify_fixture(prod_conn: sqlite3.Connection, fixture_id: int) -> str:
    wsp = prod_conn.execute(
        "SELECT * FROM worldcup_stored_predictions WHERE fixture_id=? AND (is_active IS NULL OR is_active=1)",
        (int(fixture_id),),
    ).fetchone()
    if not wsp:
        return "MISSING_WSP"
    ecse = prod_conn.execute(
        "SELECT * FROM ecse_prediction_snapshots WHERE fixture_id=?",
        (int(fixture_id),),
    ).fetchone()
    if not ecse:
        return "MISSING_ECSE"

    kickoff = _parse_dt(wsp["kickoff_utc"] or ecse["kickoff_utc"])
    predicted = _parse_dt(wsp["predicted_at"])
    generated = _parse_dt(ecse["generated_at"])
    now = datetime.now(timezone.utc)
    ts = predicted or generated
    if not ts:
        return "MISSING_TIMESTAMP"
    if kickoff and ts >= kickoff:
        return "POST_KICKOFF_SOURCE"
    if kickoff and now >= kickoff:
        return "POST_KICKOFF_SOURCE"
    if int(wsp["is_quarantined"] or 0) == 1:
        return "INVALID_QUALITY"

    try:
        payload = json.loads(wsp["payload_json"])
    except json.JSONDecodeError:
        return "INVALID_QUALITY"
    freshness = payload.get("odds_freshness") or {}
    if isinstance(freshness, dict):
        cls = str(freshness.get("odds_freshness_class") or "").upper()
        if cls in {"ODDS_STALE", "ODDS_MISSING", "DATA_QUALITY_BLOCKED"}:
            return "INVALID_ODDS_FRESHNESS"
    return "ELIGIBLE_FREEZE"


def main() -> int:
    parser = argparse.ArgumentParser(description="Dry-run forward eval freeze candidates")
    parser.add_argument("--write-local", action="store_true", help="Write freezes to local eval DB (test only)")
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--report", type=str, default="FORWARD_EVALUATION_FREEZE_CANDIDATE_DRY_RUN.md")
    args = parser.parse_args()

    settings = get_settings()
    prod_path = Path(settings.sqlite_path)
    if not prod_path.is_file():
        print(f"Production DB not found: {prod_path}", file=sys.stderr)
        return 2

    prod_conn = sqlite3.connect(str(prod_path))
    prod_conn.row_factory = sqlite3.Row
    ensure_ecse_live_tables(prod_conn)

    fixture_ids = [
        int(r[0])
        for r in prod_conn.execute(
            """
            SELECT DISTINCT fixture_id FROM worldcup_stored_predictions
            WHERE is_active IS NULL OR is_active = 1
            ORDER BY fixture_id
            LIMIT ?
            """,
            (int(args.limit),),
        ).fetchall()
    ]

    counts: Counter[str] = Counter()
    samples: dict[str, list[int]] = {c: [] for c in CATEGORIES}

    eval_conn = None
    if args.write_local:
        eval_conn = connect_eval_db(project_root())

    for fid in fixture_ids:
        category = _classify_fixture(prod_conn, fid)
        if category == "ELIGIBLE_FREEZE" and eval_conn is not None:
            result = create_or_reuse_freeze(fid, prod_conn=prod_conn, eval_conn=eval_conn)
            if result.get("status") == "reused":
                category = "DUPLICATE_IDENTICAL"
            elif result.get("status") == "conflict":
                category = "SOURCE_CONFLICT"
            elif result.get("quarantined"):
                category = "QUARANTINE_REQUIRED"
        counts[category] += 1
        if len(samples[category]) < 5:
            samples[category].append(fid)

    prod_conn.close()
    if eval_conn:
        eval_conn.close()

    lines = [
        "# Forward Evaluation Freeze Candidate Dry-Run",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**DB:** `{prod_path}`",
        f"**Write mode:** {'enabled (--write-local)' if args.write_local else 'read-only'}",
        "",
        "## Summary",
        "",
        "| Category | Count |",
        "|---|---:|",
    ]
    for cat in CATEGORIES:
        lines.append(f"| {cat} | {counts.get(cat, 0)} |")
    lines.append("")
    lines.append("## Sample fixture IDs")
    lines.append("")
    for cat in CATEGORIES:
        if samples[cat]:
            lines.append(f"- **{cat}:** {', '.join(str(x) for x in samples[cat])}")
    lines.append("")

    report_path = project_root() / args.report
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"counts": dict(counts), "report": str(report_path)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
