"""Build owner knockout tracker from authoritative frozen DB rows — RESULT-TRUTH-REPAIR-1."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.api.market_level_evaluation import (
    btts_selection_from_payload,
    canonical_1x2_selection,
    ou_selection_from_payload,
)
from worldcup_predictor.outcomes.market_result_resolver import resolve_market_result

PHASE = "RESULT-TRUTH-REPAIR-1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_json(value: Any) -> Any:
    if value is None or isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return value


def _format_1x2_pick(payload: dict[str, Any]) -> str:
    sel = canonical_1x2_selection(payload)
    if not sel:
        return "—"
    mapping = {
        "home": "Home",
        "home_win": "Home",
        "draw": "Draw",
        "away": "Away",
        "away_win": "Away",
    }
    return mapping.get(str(sel).lower(), str(sel))


def _format_btts(payload: dict[str, Any]) -> str:
    sel = btts_selection_from_payload(payload)
    if not sel:
        return "—"
    return "Yes" if str(sel).lower() in {"yes", "btts_yes"} else "No"


def _format_ou(payload: dict[str, Any]) -> str:
    sel = ou_selection_from_payload(payload)
    if not sel:
        return "—"
    return "Over" if "over" in str(sel).lower() else "Under"


def _prob_triple(payload: dict[str, Any]) -> str:
    probs = payload.get("probabilities") or {}
    hw = probs.get("home_win") or probs.get("home")
    dr = probs.get("draw")
    aw = probs.get("away_win") or probs.get("away")
    if isinstance(hw, dict):
        hw = hw.get("probability")
    if isinstance(dr, dict):
        dr = dr.get("probability")
    if isinstance(aw, dict):
        aw = aw.get("probability")
    parts = []
    for label, val in (("H", hw), ("X", dr), ("A", aw)):
        if val is not None:
            pct = float(val) * 100 if float(val) <= 1 else float(val)
            parts.append(f"{label} {pct:.1f}%")
    return " / ".join(parts) if parts else "—"


def build_owner_tracker_row(conn: sqlite3.Connection, fixture_id: int) -> dict[str, Any] | None:
    fx = conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fixture_id,)).fetchone()
    if not fx:
        return None
    fx = dict(fx)
    wde = conn.execute(
        "SELECT fixture_id, predicted_at, payload_json FROM worldcup_stored_predictions WHERE fixture_id=?",
        (fixture_id,),
    ).fetchone()
    ecse = conn.execute(
        """SELECT id, generated_at, top_1_score, top_3_scores_json, is_frozen
           FROM ecse_prediction_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1""",
        (fixture_id,),
    ).fetchone()
    fr = conn.execute("SELECT * FROM fixture_results WHERE fixture_id=?", (fixture_id,)).fetchone()
    wde_ev = conn.execute(
        "SELECT market_1x2_status, market_btts_status, market_ou_status, overall_status FROM worldcup_prediction_evaluations WHERE fixture_id=?",
        (fixture_id,),
    ).fetchone()
    ecse_ev = conn.execute(
        "SELECT top1_correct, top3_correct, top5_correct, rank_of_actual_score FROM ecse_prediction_evaluations WHERE fixture_id=?",
        (fixture_id,),
    ).fetchone()

    payload = json.loads(wde["payload_json"]) if wde and wde["payload_json"] else {}
    top3 = _parse_json(ecse["top_3_scores_json"]) if ecse else []
    top3 = [str(x) for x in top3] if isinstance(top3, list) else []

    reg = resolve_market_result(dict(fr) if fr else None, fx, market_type="1x2")
    reg_score = reg.get("final_score") or "—"

    eval_status = "Pending"
    if wde_ev or ecse_ev:
        wde_ev_d = dict(wde_ev) if wde_ev else {}
        eval_status = "Evaluated ✅" if str(wde_ev_d.get("overall_status") or "") not in {"", "pending"} else "Evaluated"

    odds_meta = payload.get("odds_freshness_status") or (payload.get("odds_freshness_metadata") or {}).get("status") or "—"

    return {
        "fixture_id": fixture_id,
        "match": f"{fx['home_team']} vs {fx['away_team']}",
        "status": eval_status if fr else "Pending",
        "wde_1x2": _format_1x2_pick(payload),
        "wde_1x2_source": "canonical_1x2_selection",
        "wde_probs": _prob_triple(payload),
        "btts": _format_btts(payload),
        "ou": _format_ou(payload),
        "ecse_top3": " / ".join(top3[:3]) if top3 else "—",
        "ecse_snapshot_id": ecse["id"] if ecse else None,
        "regulation_result": reg_score,
        "odds": odds_meta,
        "generated_at": wde["predicted_at"] if wde else None,
        "payload_hash_prefix": None,
        "source_trace": {
            "wde_table": "worldcup_stored_predictions",
            "ecse_table": "ecse_prediction_snapshots",
            "result_table": "fixture_results",
            "eval_wde": "worldcup_prediction_evaluations" if wde_ev else None,
            "eval_ecse": "ecse_prediction_evaluations" if ecse_ev else None,
        },
    }


def render_owner_tracker_markdown(rows: list[dict[str, Any]], *, title: str | None = None) -> str:
    lines = [
        f"# {title or 'Controlled Knockout Predictions — Owner Tracker'}",
        "",
        f"**Updated:** {_utc_now()} · **Source:** frozen DB rows only (no manual picks)",
        "",
        "| Match | fixture_id | Status | 1X2 (auth) | H/X/A | BTTS | O/U | ECSE Top3 | Reg 90m | Odds |",
        "|-------|-----------:|--------|------------|-------|------|-----|-----------|---------|------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['match']} | {r['fixture_id']} | {r['status']} | {r['wde_1x2']} | {r['wde_probs']} "
            f"| {r['btts']} | {r['ou']} | {r['ecse_top3']} | {r['regulation_result']} | {r['odds']} |"
        )
    lines.extend([
        "",
        "## Source trace",
        "",
        "All 1X2/BTTS/O/U values from `worldcup_stored_predictions.payload_json` via canonical selection helpers.",
        "ECSE Top3 from latest frozen `ecse_prediction_snapshots` row.",
        "Reg 90m from `fixture_results.regulation_*` via market result resolver.",
        "",
    ])
    return "\n".join(lines)
