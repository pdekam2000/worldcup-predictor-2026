#!/usr/bin/env python3
"""Phase 2D dry-run inventory — classify frozen predictions vs results (no writes)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.freeze_integrity import verify_freeze_integrity
from worldcup_predictor.forward_evaluation.result_sync_service import sync_result_for_fixture


def _classify_row(
    *,
    eval_conn: sqlite3.Connection,
    prod_conn: sqlite3.Connection,
    freeze: dict,
) -> str:
    fid = int(freeze["fixture_id"])
    pid = str(freeze["prediction_id"])
    scope = str(freeze.get("prediction_scope") or "production")
    tier = str(freeze.get("validation_tier") or "A")

    if freeze.get("quarantine_reason"):
        return "QUARANTINED"
    if scope in ("owner_shadow",) or tier == "B":
        return "OWNER_ONLY"
    if scope == "owner_daily":
        return "OWNER_ONLY"

    integrity = verify_freeze_integrity(eval_conn, prod_conn, prediction_id=pid)
    if not integrity.get("ok"):
        return "FREEZE_INVALID"

    evaluated = eval_conn.execute(
        "SELECT 1 FROM market_evaluations WHERE prediction_id=?",
        (pid,),
    ).fetchone()
    if evaluated:
        return "ALREADY_EVALUATED"

    sync = sync_result_for_fixture(
        fid,
        prod_conn=prod_conn,
        eval_conn=eval_conn,
        dry_run=True,
        allow_provider_fetch=False,
    )
    if not sync.get("result_available"):
        return "RESULT_MISSING"
    if sync.get("conflict"):
        return "FREEZE_INVALID"

    btts_unavail = str(freeze.get("btts_execution_status") or "").upper() == "UNAVAILABLE"
    ou_unavail = str(freeze.get("ou_execution_status") or "").upper() == "UNAVAILABLE"
    if btts_unavail or ou_unavail:
        return "COMPONENTS_PARTIAL"

    if int(freeze.get("public_visible") or 0) == 1 and tier == "A" and scope == "production":
        return "PUBLIC_ELIGIBLE"
    return "OWNER_ONLY"


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 2D forward evaluation dry-run inventory")
    parser.add_argument("--output", type=Path, default=ROOT / "PHASE_2D_FORWARD_EVALUATION_DRY_RUN.md")
    parser.add_argument("--json", type=Path, default=None)
    args = parser.parse_args()

    settings = get_settings()
    prod = connect(settings.sqlite_path)
    ev = connect_eval_db(project_root())
    prod.row_factory = sqlite3.Row
    ev.row_factory = sqlite3.Row

    freezes = [
        dict(r)
        for r in ev.execute(
            """
            SELECT * FROM frozen_predictions
            WHERE freeze_status='ACTIVE'
            ORDER BY kickoff DESC
            """
        ).fetchall()
    ]

    by_class: dict[str, list[dict]] = defaultdict(list)
    by_scope: dict[str, Counter] = defaultdict(Counter)
    by_tier: dict[str, Counter] = defaultdict(Counter)

    for fr in freezes:
        cls = _classify_row(eval_conn=ev, prod_conn=prod, freeze=fr)
        scope = str(fr.get("prediction_scope") or "production")
        tier = str(fr.get("validation_tier") or "A")
        entry = {
            "fixture_id": fr["fixture_id"],
            "freeze_id": fr["prediction_id"],
            "prediction_scope": scope,
            "validation_tier": tier,
            "kickoff": fr.get("kickoff"),
            "classification": cls,
        }
        by_class[cls].append(entry)
        by_scope[scope][cls] += 1
        by_tier[tier][cls] += 1

    summary = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_active_freezes": len(freezes),
        "by_classification": {k: len(v) for k, v in sorted(by_class.items())},
        "by_scope": {s: dict(c) for s, c in by_scope.items()},
        "by_tier": {t: dict(c) for t, c in by_tier.items()},
        "fixtures": [e for items in by_class.values() for e in items],
    }

    lines = [
        "# Phase 2D Forward Evaluation Dry Run",
        "",
        f"**Generated:** {summary['generated_at_utc']}",
        "",
        "## Summary",
        "",
        f"- Active freezes: **{summary['total_active_freezes']}**",
        "",
        "### By classification",
        "",
    ]
    for cls, count in sorted(summary["by_classification"].items()):
        lines.append(f"- `{cls}`: {count}")

    for label, bucket in [("Tier A", "A"), ("Tier B", "B"), ("owner_daily scope", "owner_daily")]:
        lines.extend(["", f"### {label}", ""])
        if label == "owner_daily scope":
            data = summary["by_scope"].get("owner_daily", {})
        else:
            data = summary["by_tier"].get(bucket, {})
        if not data:
            lines.append("_No rows._")
        else:
            for cls, count in sorted(data.items()):
                lines.append(f"- `{cls}`: {count}")

    lines.extend(["", "## Fixture inventory", ""])
    for cls in sorted(by_class.keys()):
        lines.append(f"### {cls}")
        lines.append("")
        for row in by_class[cls][:50]:
            lines.append(
                f"- `{row['fixture_id']}` scope={row['prediction_scope']} tier={row['validation_tier']} kickoff={row['kickoff']}"
            )
        if len(by_class[cls]) > 50:
            lines.append(f"- _…and {len(by_class[cls]) - 50} more_")
        lines.append("")

    args.output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    prod.close()
    ev.close()
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
