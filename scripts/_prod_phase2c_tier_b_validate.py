#!/usr/bin/env python3
"""Production Tier B structured persistence E2E acceptance (read/verify, one fixture)."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/opt/worldcup-predictor")
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.forward_evaluation.tier_b_persistence import (
    TIER_B_SCOPE,
    read_tier_b_structured_record,
    verify_tier_b_record,
)
from worldcup_predictor.mcp_server import runtime as mcp_runtime


def _git_sha() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except Exception:
        return "unknown"


def _service_active(name: str) -> bool:
    try:
        out = subprocess.check_output(["systemctl", "is-active", name], text=True, stderr=subprocess.DEVNULL).strip()
        return out == "active"
    except Exception:
        return False


def _pick_tier_b_fixture(conn: sqlite3.Connection, preferred: int = 1497629) -> tuple[int, str]:
    row = conn.execute(
        """
        SELECT f.fixture_id, f.competition_key, f.kickoff_utc, f.status
        FROM fixtures f
        WHERE f.fixture_id = ?
          AND (f.is_placeholder IS NULL OR f.is_placeholder = 0)
        LIMIT 1
        """,
        (int(preferred),),
    ).fetchone()
    if row and str(row["status"] or "NS") in ("NS", "TBD", "SCHEDULED", "Not Started"):
        return int(row["fixture_id"]), "preferred_fixture_pre_kickoff"
    alt = conn.execute(
        """
        SELECT f.fixture_id, f.competition_key, f.kickoff_utc
        FROM fixtures f
        WHERE f.competition_key IN (
            'allsvenskan','superettan','a_lyga','one_lyga','virsliga','urvalsdeild',
            'one_deild','eliteserien','veikkausliiga','la_liga','serie_a','ligue_1'
        )
          AND datetime(replace(replace(f.kickoff_utc,' UTC',''),'T',' ')) > datetime('now')
          AND (f.is_placeholder IS NULL OR f.is_placeholder = 0)
        ORDER BY f.kickoff_utc ASC
        LIMIT 1
        """
    ).fetchone()
    if alt:
        return int(alt["fixture_id"]), "discovered_upcoming_tier_b"
    return preferred, "fallback_read_only_existing"


def _count_before(conn: sqlite3.Connection, eval_conn: sqlite3.Connection, fid: int) -> dict[str, int]:
    return {
        "wsp": conn.execute(
            "SELECT COUNT(*) c FROM worldcup_stored_predictions WHERE fixture_id=?",
            (fid,),
        ).fetchone()["c"],
        "ecse": conn.execute(
            "SELECT COUNT(*) c FROM ecse_prediction_snapshots WHERE fixture_id=?",
            (fid,),
        ).fetchone()["c"],
        "freeze_owner_shadow": eval_conn.execute(
            "SELECT COUNT(*) c FROM frozen_predictions WHERE fixture_id=? AND prediction_scope=?",
            (fid, TIER_B_SCOPE),
        ).fetchone()["c"],
        "rankings": eval_conn.execute(
            """
            SELECT COUNT(*) c FROM exact_score_rankings r
            JOIN frozen_predictions f ON f.prediction_id = r.prediction_id
            WHERE f.fixture_id=? AND f.prediction_scope=?
            """,
            (fid, TIER_B_SCOPE),
        ).fetchone()["c"],
    }


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    eval_conn = connect_eval_db(ROOT)

    fixture_id, selection_reason = _pick_tier_b_fixture(conn)
    before = _count_before(conn, eval_conn, fixture_id)

    # One canonical Tier B prediction (MCP with auto owner_shadow context)
    raw = mcp_runtime.run_fixture_prediction(
        fixture_id,
        refresh_if_stale=False,
        bridge_context={
            "prediction_scope": TIER_B_SCOPE,
            "validation_tier": "B",
            "public_visible": False,
            "bridge_origin": "phase2c_e2e",
        },
    )
    quality = (raw.get("quality") or {}).get("status")
    tier_b_persist = raw.get("tier_b_persistence") or {}
    forward_eval = raw.get("forward_evaluation") or {}

    record = read_tier_b_structured_record(fixture_id, prod_conn=conn, eval_conn=eval_conn)
    ok, issues = verify_tier_b_record(record)

    after = _count_before(conn, eval_conn, fixture_id)
    wsp_scope = conn.execute(
        "SELECT prediction_scope, validation_tier FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fixture_id,),
    ).fetchone()

    freeze = eval_conn.execute(
        """
        SELECT prediction_id, prediction_scope, public_visible, evaluation_status, content_hash
        FROM frozen_predictions
        WHERE fixture_id=? AND prediction_scope=?
        ORDER BY frozen_at DESC LIMIT 1
        """,
        (fixture_id, TIER_B_SCOPE),
    ).fetchone()

    report = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "deployed_sha": _git_sha(),
        "services": {
            "worldcup-api": _service_active("worldcup-api"),
            "worldcup-gpt-actions": _service_active("worldcup-gpt-actions"),
            "worldcup-mcp": _service_active("worldcup-mcp"),
        },
        "fixture_id": fixture_id,
        "fixture_selection_reason": selection_reason,
        "quality_status": quality,
        "counts_before": before,
        "counts_after": after,
        "wsp_scope": dict(wsp_scope) if wsp_scope else None,
        "forward_evaluation": forward_eval,
        "tier_b_persistence": tier_b_persist,
        "structured_record_ok": ok,
        "structured_record_issues": issues,
        "freeze_row": dict(freeze) if freeze else None,
        "checks": {
            "prediction_completed": quality in ("OK", "PARTIAL"),
            "wde_present": bool(record and record.get("wde_decision")),
            "ft_marginal_present": bool(record and record.get("ft_marginal_direction")),
            "had_present": all(record.get(k) is not None for k in ("probability_home", "probability_draw", "probability_away")) if record else False,
            "btts_present": bool(record and record.get("btts_selection")),
            "ou_present": bool(record and record.get("ou_2_5_selection")),
            "ecse_top5_present": bool(record and record.get("ecse_top5")),
            "wsp_scope_owner_shadow": (wsp_scope["prediction_scope"] if wsp_scope else None) == TIER_B_SCOPE,
            "freeze_scope_owner_shadow": (freeze["prediction_scope"] if freeze else None) == TIER_B_SCOPE,
            "public_visible_false": int(freeze["public_visible"] or 0) == 0 if freeze else False,
            "evaluation_pending": (freeze["evaluation_status"] if freeze else None) in (None, "pending", "PENDING", "EVAL_PENDING"),
            "content_hash_present": bool((freeze or {}).get("content_hash")),
            "no_duplicate_freeze_spike": after["freeze_owner_shadow"] <= before["freeze_owner_shadow"] + 1,
            "structured_verification": ok,
        },
        "pass": False,
    }
    report["pass"] = all(report["services"].values()) and all(report["checks"].values())

    out = ROOT / "artifacts" / "phase2c_tier_b_production_e2e.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2, default=str))
    final = "TIER_B_STRUCTURED_PERSISTENCE_COMPLETE" if report["pass"] else "TIER_B_STRUCTURED_PERSISTENCE_VALIDATION_FAILED"
    print("FINAL:", final)
    conn.close()
    eval_conn.close()
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
