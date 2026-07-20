"""Extract canonical model outputs from WSP/ECSE after a temporary prediction run."""

from __future__ import annotations

import json
import math
import sqlite3
from typing import Any

from worldcup_predictor.forward_evaluation.context import scoreline_side
from worldcup_predictor.gpt_actions.bridge_semantics import extract_wde_semantics
from worldcup_predictor.research.ecse_live.store import get_snapshot
from worldcup_predictor.research.ecse_timing_experiment.hashing import as_float, as_prob, content_hash


def _norm_side(v: Any) -> str:
    s = str(v or "").lower().strip()
    if s in {"1", "home", "home_win", "h"}:
        return "home_win"
    if s in {"x", "draw", "d"}:
        return "draw"
    if s in {"2", "away", "away_win", "a"}:
        return "away_win"
    return s


def _fav(h: Any, d: Any, a: Any) -> str | None:
    vals = {"home_win": as_float(h), "draw": as_float(d), "away_win": as_float(a)}
    present = {k: v for k, v in vals.items() if v is not None and v > 1}
    if len(present) < 2:
        return None
    return min(present, key=present.get)  # type: ignore[arg-type]


def _consensus(wde: str | None, top1_side: str | None, market: str | None, ft: str | None) -> str:
    if not wde:
        return "INSUFFICIENT_DATA"
    if wde and top1_side and wde != top1_side:
        return "HIGH_CONFLICT"
    if wde and ft and wde != ft:
        return "HIGH_CONFLICT"
    sides = [s for s in (wde, top1_side, market, ft) if s]
    if market and wde != market and top1_side and wde == top1_side:
        return "MIXED"
    if len(set(sides)) == 1 and len(sides) >= 2:
        return "HIGH_AGREEMENT"
    if wde == top1_side:
        return "MODERATE_AGREEMENT"
    if len(set(sides)) >= 3:
        return "HIGH_CONFLICT"
    return "MIXED"


def top5_from_snap(snap: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not snap:
        return []
    rows: list[dict[str, Any]] = []
    for i, item in enumerate((snap.get("top_10_scorelines") or [])[:5], start=1):
        if isinstance(item, dict):
            rows.append(
                {
                    "rank": i,
                    "score": item.get("scoreline") or item.get("score"),
                    "probability": as_float(item.get("probability")),
                }
            )
    if len(rows) >= 5:
        return rows[:5]
    for i, item in enumerate((snap.get("top_5_scores") or [])[:5], start=1):
        if isinstance(item, dict):
            rows.append(
                {
                    "rank": i,
                    "score": item.get("scoreline") or item.get("score"),
                    "probability": as_float(item.get("probability")),
                }
            )
        elif isinstance(item, str):
            rows.append({"rank": i, "score": item, "probability": None})
    return rows[:5]


def mass(rows: list[dict[str, Any]], n: int) -> float | None:
    vals = []
    for r in rows[:n]:
        p = as_prob(r.get("probability"))
        if p is not None:
            vals.append(p)
    return round(sum(vals), 6) if vals else None


def entropy(rows: list[dict[str, Any]]) -> float | None:
    vals = []
    for r in rows:
        p = as_prob(r.get("probability"))
        if p is not None and p > 0:
            vals.append(p)
    if not vals:
        return None
    s = sum(vals)
    vals = [v / s for v in vals]
    return round(-sum(v * math.log(v) for v in vals), 6)


def no_bet_breakdown(payload: dict[str, Any]) -> dict[str, Any]:
    audit = payload.get("confidence_audit") or payload.get("audit") or {}
    if isinstance(audit, dict) and "confidence_audit" in audit:
        audit = audit.get("confidence_audit") or audit
    reasons = (
        payload.get("no_bet_reasons")
        or (audit.get("no_bet_reasons") if isinstance(audit, dict) else None)
        or (payload.get("trace") or {}).get("no_bet_reasons")
        or []
    )
    return {
        "no_bet": bool(payload.get("no_bet")) if "no_bet" in payload else None,
        "no_bet_reason": reasons,
        "pick_tier": payload.get("pick_tier") or (audit.get("pick_tier") if isinstance(audit, dict) else None),
    }


def odds_blob(snap: Any) -> dict[str, Any]:
    if snap is None:
        return {}
    d = snap.to_dict() if hasattr(snap, "to_dict") else dict(snap)
    home = as_float(d.get("home_odds") or d.get("home"))
    draw = as_float(d.get("draw_odds") or d.get("draw"))
    away = as_float(d.get("away_odds") or d.get("away"))
    blob = {
        "home": home,
        "draw": draw,
        "away": away,
        "bookmaker_count": d.get("bookmaker_count"),
        "fetched_at": d.get("fetched_at_utc") or d.get("captured_at") or d.get("fetched_at"),
        "odds_age_minutes": d.get("odds_age_minutes") or d.get("age_minutes"),
        "freshness_status": d.get("freshness_class") or d.get("freshness_status"),
        "provider": d.get("provider") or d.get("source"),
        "policy_status": d.get("policy_status"),
        "snapshot_id": d.get("row_id") or d.get("snapshot_id"),
    }
    blob["content_hash"] = content_hash(
        {"home": home, "draw": draw, "away": away, "fetched_at": blob.get("fetched_at")}
    )
    return blob


def extract_model_payload(
    prod: sqlite3.Connection,
    fixture_id: int,
    odds: dict[str, Any],
    *,
    model_version: str | None = None,
) -> dict[str, Any]:
    stored = prod.execute(
        "SELECT payload_json, predicted_at, updated_at FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    snap = get_snapshot(prod, int(fixture_id))
    if not stored:
        return {"complete": False, "reason": "no_wsp"}
    try:
        payload = json.loads(stored["payload_json"])
    except Exception:
        return {"complete": False, "reason": "bad_payload"}

    sem = extract_wde_semantics(payload)
    probs = payload.get("probabilities") or {}
    btts = probs.get("btts") or {}
    ou = probs.get("over_under_2_5") or {}
    top5 = top5_from_snap(snap)
    wde = _norm_side(sem.get("decision_pick"))
    ft = _norm_side(sem.get("probability_argmax"))
    top1 = top5[0] if top5 else {}
    top1_side = _norm_side(scoreline_side(str(top1.get("score") or "")))
    market = _fav(odds.get("home"), odds.get("draw"), odds.get("away"))
    cons = _consensus(wde, top1_side, market, ft)
    nobet = no_bet_breakdown(payload)

    out = {
        "complete": bool(top5) and bool(sem.get("decision_pick")),
        "predicted_at": stored["predicted_at"] or stored["updated_at"],
        "odds": odds,
        "wde": {
            "decision": sem.get("decision_pick"),
            "ft_marginal": sem.get("probability_argmax"),
            "home_probability": sem.get("home_prob"),
            "draw_probability": sem.get("draw_prob"),
            "away_probability": sem.get("away_prob"),
            "confidence": sem.get("confidence") or payload.get("confidence"),
        },
        "btts": {
            "prediction": btts.get("selection") or (sem.get("btts") or {}).get("prediction"),
            "yes_probability": as_float((btts.get("probabilities") or {}).get("yes")),
            "no_probability": as_float((btts.get("probabilities") or {}).get("no")),
        },
        "ou25": {
            "preferred_side": ou.get("selection") or (sem.get("ou25") or {}).get("prediction"),
            "over_probability": as_float((ou.get("probabilities") or {}).get("over_2_5")),
            "under_probability": as_float((ou.get("probabilities") or {}).get("under_2_5")),
        },
        "ecse": {
            "top1": top5[0] if len(top5) > 0 else None,
            "top2": top5[1] if len(top5) > 1 else None,
            "top3": top5[2] if len(top5) > 2 else None,
            "top4": top5[3] if len(top5) > 3 else None,
            "top5": top5[4] if len(top5) > 4 else None,
            "scores": [str(t.get("score")) for t in top5 if t.get("score")],
            "top1_probability": as_prob((top5[0] or {}).get("probability")) if top5 else None,
            "top3_mass": mass(top5, 3),
            "top5_mass": mass(top5, 5),
            "entropy": entropy(top5),
            "lambda_home": snap.get("lambda_home") if snap else None,
            "lambda_away": snap.get("lambda_away") if snap else None,
        },
        "consensus": cons,
        "no_bet": nobet.get("no_bet"),
        "no_bet_reason": nobet.get("no_bet_reason"),
        "pick_tier": nobet.get("pick_tier"),
        "model_version": model_version or payload.get("model_version") or payload.get("pipeline_version"),
        "research_only": True,
        "canonical": False,
        "final_decision_authority": False,
        "freeze_capture": False,
    }
    out["research_output_hash"] = content_hash(
        {
            "wde": out["wde"],
            "ecse_scores": (out["ecse"] or {}).get("scores"),
            "ecse_probs": [
                as_prob(((out["ecse"] or {}).get(f"top{i}") or {}).get("probability"))
                for i in range(1, 6)
            ],
            "odds": {"home": odds.get("home"), "draw": odds.get("draw"), "away": odds.get("away")},
        }
    )
    return out


def freeze_payload_from_eval(fr: dict[str, Any] | None) -> dict[str, Any] | None:
    if not fr:
        return None
    ranks = sorted(fr.get("ranks") or [], key=lambda r: int(r.get("rank") or 99))
    top5 = []
    for i, r in enumerate(ranks[:5], start=1):
        top5.append(
            {
                "rank": i,
                "score": r.get("score"),
                "probability": as_float(r.get("probability")),
            }
        )
    return {
        "wde": {"decision": fr.get("wde_decision"), "ft_marginal": fr.get("ft_marginal_direction")},
        "ecse": {
            "scores": [str(t["score"]) for t in top5 if t.get("score")],
            **{f"top{i}": top5[i - 1] if i - 1 < len(top5) else None for i in range(1, 6)},
            "top5_mass": as_float(fr.get("top5_mass")),
            "entropy": as_float(fr.get("entropy")),
        },
        "btts": {},
        "ou25": {},
        "no_bet": fr.get("no_bet"),
        "research_only": False,
        "canonical": True,
    }
