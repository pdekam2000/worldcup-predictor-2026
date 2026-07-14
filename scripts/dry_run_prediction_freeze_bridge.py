#!/usr/bin/env python3
"""Dry-run: classify prediction rows eligible for post-persist freeze bridge."""

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

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.forward_evaluation.bridge import (
    ForwardEvalBridgeContext,
    maybe_capture_after_prediction_persistence,
)
from worldcup_predictor.research.ecse_live.ddl import PHASE_ECSE_LIVE_DDL
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables

CATEGORIES = (
    "BRIDGE_ELIGIBLE",
    "MISSING_WSP",
    "MISSING_ECSE",
    "BRIDGE_SKIPPED",
    "BRIDGE_CREATED",
    "BRIDGE_REUSED",
    "BRIDGE_QUARANTINED",
    "BRIDGE_REJECTED",
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-local", action="store_true", help="Execute bridge writes locally")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    settings = get_settings()
    prod_path = Path(settings.sqlite_path)
    if not prod_path.is_file():
        print(json.dumps({"error": "db_not_found", "path": str(prod_path)}))
        return 2

    conn = sqlite3.connect(str(prod_path))
    conn.row_factory = sqlite3.Row
    ensure_ecse_live_tables(conn)

    fixture_ids = [
        int(r[0])
        for r in conn.execute(
            """
            SELECT DISTINCT w.fixture_id
            FROM worldcup_stored_predictions w
            WHERE w.is_active IS NULL OR w.is_active = 1
            ORDER BY w.fixture_id
            LIMIT ?
            """,
            (int(args.limit),),
        ).fetchall()
    ]

    counts: Counter[str] = Counter()
    samples: dict[str, list[int]] = {c: [] for c in CATEGORIES}

    for fid in fixture_ids:
        has_wsp = conn.execute(
            "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? AND (is_active IS NULL OR is_active=1)",
            (fid,),
        ).fetchone()
        has_ecse = conn.execute("SELECT id FROM ecse_prediction_snapshots WHERE fixture_id=?", (fid,)).fetchone()
        if not has_wsp:
            category = "MISSING_WSP"
        elif not has_ecse:
            category = "MISSING_ECSE"
        else:
            category = "BRIDGE_ELIGIBLE"
            if args.write_local:
                bridge = maybe_capture_after_prediction_persistence(
                    fid,
                    prod_conn=conn,
                    bridge_context=ForwardEvalBridgeContext(
                        prediction_scope="owner_daily",
                        bridge_origin="dry_run",
                        ecse_snapshot_id=int(has_ecse["id"]),
                    ),
                )
                category = f"BRIDGE_{bridge.status.upper()}"
                if bridge.status == "skipped":
                    category = "BRIDGE_SKIPPED"

        counts[category] += 1
        if len(samples.get(category, [])) < 5:
            samples.setdefault(category, []).append(fid)

    conn.close()
    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "db": str(prod_path),
        "write_mode": bool(args.write_local),
        "counts": dict(counts),
        "samples": samples,
    }
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
