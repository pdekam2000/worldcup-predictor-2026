#!/usr/bin/env python3
"""Dry-run inventory of legacy Tier B JSONL rows for structured backfill eligibility."""

from __future__ import annotations

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
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.gpt_actions.shadow_storage import SHADOW_PREDICTIONS_PATH

CLASSIFICATIONS = (
    "already_fully_structured",
    "partially_structured",
    "jsonl_only",
    "freeze_only",
    "wsp_only",
    "ecse_only",
    "malformed",
    "missing_provenance",
    "LEGACY_TIER_B_INCOMPLETE_NOT_BACKFILLED",
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


def classify_row(
    row: dict,
    *,
    prod: sqlite3.Connection,
    eval_conn: sqlite3.Connection,
) -> str:
    if not row.get("fixture_id"):
        return "malformed"
    fid = int(row["fixture_id"])
    try:
        fx = prod.execute("SELECT kickoff_utc FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
    except sqlite3.Error:
        fx = None
    if not fx:
        return "missing_provenance"

    wsp = prod.execute(
        "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? AND (is_active IS NULL OR is_active=1)",
        (fid,),
    ).fetchone()
    ecse = prod.execute("SELECT 1 FROM ecse_prediction_snapshots WHERE fixture_id=?", (fid,)).fetchone()
    freeze = eval_conn.execute(
        "SELECT 1 FROM frozen_predictions WHERE fixture_id=? AND prediction_scope='owner_shadow'",
        (fid,),
    ).fetchone()

    gen = _parse_dt(row.get("generated_at"))
    kick = _parse_dt(row.get("kickoff") or fx["kickoff_utc"])
    if gen and kick and gen >= kick:
        return "LEGACY_TIER_B_INCOMPLETE_NOT_BACKFILLED"

    evidence = row.get("evidence") or {}
    has_wde = bool(evidence.get("wde"))
    has_ecse = bool((evidence.get("ecse") or {}).get("top_scores"))

    if wsp and ecse and freeze:
        return "already_fully_structured"
    if freeze and not wsp:
        return "freeze_only"
    if wsp and not ecse:
        return "wsp_only"
    if ecse and not wsp:
        return "ecse_only"
    if has_wde and has_ecse and not freeze:
        return "partially_structured"
    if row.get("payload_hash") and not wsp and not ecse:
        return "jsonl_only"
    return "LEGACY_TIER_B_INCOMPLETE_NOT_BACKFILLED"


def main() -> int:
    path = SHADOW_PREDICTIONS_PATH
    settings = get_settings()
    prod = connect(settings.sqlite_path)
    eval_conn = connect_eval_db(project_root())

    counts: Counter[str] = Counter()
    samples: dict[str, list[int]] = {k: [] for k in CLASSIFICATIONS}

    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                counts["malformed"] += 1
                continue
            label = classify_row(row, prod=prod, eval_conn=eval_conn)
            counts[label] += 1
            fid = row.get("fixture_id")
            if fid and len(samples.get(label, [])) < 5:
                samples.setdefault(label, []).append(int(fid))

    prod.close()
    eval_conn.close()

    report_path = ROOT / "TIER_B_STRUCTURED_PERSISTENCE_BACKFILL_DRY_RUN.md"
    lines = [
        "# Tier B Structured Persistence — Backfill Dry Run",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        f"**JSONL path:** `{path}`",
        "",
        "## Classification counts",
        "",
        "| Classification | Count |",
        "|---|---:|",
    ]
    for label in CLASSIFICATIONS:
        lines.append(f"| `{label}` | {counts.get(label, 0)} |")
    lines.extend(["", "## Sample fixture IDs", ""])
    for label, fids in samples.items():
        if fids:
            lines.append(f"- **{label}:** {fids}")
    lines.extend(
        [
            "",
            "## Policy",
            "",
            "- No automatic broad backfill in Phase 2C",
            "- Only `partially_structured` / `jsonl_only` with pre-kickoff timestamps and complete evidence are backfill candidates",
            "- Mark unsupported: `LEGACY_TIER_B_INCOMPLETE_NOT_BACKFILLED`",
            "",
        ]
    )
    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps(dict(counts), indent=2))
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
