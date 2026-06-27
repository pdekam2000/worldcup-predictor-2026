#!/usr/bin/env python3
"""Phase A15.5 — WDE decision & publication audit (read-only)."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]

MARKET_GROUPS = {
    "1x2": ("1x2", "match_winner"),
    "btts": ("btts",),
    "over_under": ("over_under_0_5", "over_under_1_5", "over_under_2_5", "over_under_3_5"),
    "correct_score": ("correct_score",),
    "goal_timing": (
        "first_goal_team",
        "first_goal_time_range",
        "estimated_first_goal_minute",
        "next_goal_team",
        "goal_timing_confidence",
        "goal_timing_tier",
    ),
    "goalscorer": ("anytime_goalscorer", "first_goalscorer", "player_most_likely_to_score"),
}

OFFICIAL_CONF = 60.0
MIN_DQ = 45.0
WDE_NO_BET_MIN = 60.0
WDE_DQ_NO_BET = 50.0


def _classify_reason(reason: str) -> str:
    r = reason.lower()
    if "confidence" in r:
        return "insufficient_confidence"
    if "data_quality" in r:
        return "missing_provider_data"
    if "placeholder" in r:
        return "missing_provider_data"
    if "disagreement" in r or "conflict" in r or "divergence" in r:
        return "model_disagreement"
    if "lineup" in r:
        return "missing_lineup"
    if "injury" in r or "absence" in r:
        return "missing_injuries"
    if "weather" in r:
        return "weather_dependency"
    if "odds" in r:
        return "missing_odds"
    return "other"


def _infer_fixture_reasons(payload: dict[str, Any]) -> list[str]:
    categories: list[str] = []
    audit = payload.get("audit_trace") or {}
    conf_block = audit.get("confidence") or {}
    wde_reasons = conf_block.get("no_bet_reasons") or []
    for r in wde_reasons:
        categories.append(_classify_reason(str(r)))

    confidence = float(payload.get("confidence") or 0)
    dq = float(payload.get("data_quality") or 0)
    if confidence < OFFICIAL_CONF and "insufficient_confidence" not in categories:
        categories.append("publication_threshold")
    if confidence < WDE_NO_BET_MIN and "insufficient_confidence" not in categories:
        categories.append("insufficient_confidence")
    if dq < MIN_DQ:
        categories.append("missing_provider_data")
    if dq < WDE_DQ_NO_BET:
        categories.append("missing_provider_data")
    if payload.get("no_bet") and not categories:
        categories.append("other")

    caution = str(payload.get("caution_reason") or "")
    if caution:
        if "confidence" in caution.lower():
            categories.append("publication_threshold")
        if "data quality" in caution.lower():
            categories.append("missing_provider_data")
        if "uncertainty" in caution.lower():
            categories.append("insufficient_confidence")

    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for c in categories:
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out or ["other"]


def _market_group_status(markets_doc: dict[str, Any], group: str) -> str:
    keys = MARKET_GROUPS[group]
    mkt = markets_doc.get("markets") if isinstance(markets_doc.get("markets"), dict) else markets_doc
    if not isinstance(mkt, dict):
        return "unavailable"
    statuses = []
    for k in keys:
        block = mkt.get(k)
        if isinstance(block, dict):
            statuses.append(block.get("market_status") or "unavailable")
    if not statuses:
        return "unavailable"
    if any(s == "prediction" for s in statuses):
        return "published"
    if any(s == "no_pick" for s in statuses):
        return "no_bet"
    return "unavailable"


def _candidate_strength(pick: dict[str, Any] | None) -> str | None:
    if not pick or not isinstance(pick, dict):
        return None
    prob = pick.get("probability") or pick.get("confidence")
    try:
        p = float(prob)
        if p > 1:
            p /= 100.0
    except (TypeError, ValueError):
        return "weak"
    if p >= 0.58:
        return "strong"
    if p >= 0.52:
        return "quality"
    return "weak"


def run_audit() -> dict[str, Any]:
    from worldcup_predictor.predops.store import PredOpsStore
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.config.competitions import list_competition_keys

    store = PredOpsStore()
    repo = FootballIntelligenceRepository()

    snapshots: list[dict[str, Any]] = []
    for key in list_competition_keys(enabled_only=True):
        for row in repo.list_worldcup_stored_predictions(competition_key=key, limit=500, offset=0):
            fid = row.get("fixture_id")
            if fid is None:
                continue
            snap = store.get_latest_snapshot(int(fid))
            if snap:
                snapshots.append(snap)
            else:
                try:
                    payload = json.loads(row["payload_json"]) if isinstance(row.get("payload_json"), str) else row.get("payload_json")
                except (json.JSONDecodeError, TypeError):
                    continue
                if isinstance(payload, dict):
                    snapshots.append(
                        {
                            "fixture_id": int(fid),
                            "competition_key": key,
                            "payload": payload,
                            "markets": {},
                            "coverage_state": "no_bet" if payload.get("no_bet") else "completed",
                        }
                    )

    total = len(snapshots)
    no_bet_fixtures = 0
    published_fixtures = 0
    reason_counter: Counter[str] = Counter()
    reason_by_fixture: dict[int, list[str]] = {}

    market_stats: dict[str, Counter[str]] = {g: Counter() for g in MARKET_GROUPS}

    hidden_candidates = 0
    has_best_pick_hidden = 0
    market_specific_only = 0

    threshold_rejections = Counter()
    confidence_values: list[float] = []
    dq_values: list[float] = []

    for snap in snapshots:
        payload = snap.get("payload") or {}
        markets_doc = snap.get("markets") or {}
        fid = int(snap.get("fixture_id") or payload.get("fixture_id") or 0)
        is_no_bet = bool(payload.get("no_bet")) or snap.get("coverage_state") == "no_bet"

        conf = float(payload.get("confidence") or 0)
        dq = float(payload.get("data_quality") or 0)
        confidence_values.append(conf)
        dq_values.append(dq)

        if conf < WDE_NO_BET_MIN:
            threshold_rejections["wde_confidence_below_60"] += 1
        if conf < OFFICIAL_CONF:
            threshold_rejections["publication_confidence_below_60"] += 1
        if dq < WDE_DQ_NO_BET:
            threshold_rejections["wde_data_quality_below_50"] += 1
        if dq < MIN_DQ:
            threshold_rejections["publication_data_quality_below_45"] += 1

        audit = payload.get("audit_trace") or {}
        for r in (audit.get("confidence") or {}).get("no_bet_reasons") or []:
            threshold_rejections[f"wde_reason:{r}"] += 1

        if is_no_bet:
            no_bet_fixtures += 1
            reasons = _infer_fixture_reasons(payload)
            reason_by_fixture[fid] = reasons
            for r in reasons:
                reason_counter[r] += 1

            best = payload.get("best_available_pick") or payload.get("caution_pick")
            if best:
                has_best_pick_hidden += 1
                strength = _candidate_strength(best if isinstance(best, dict) else None)
                if strength in ("quality", "strong"):
                    hidden_candidates += 1

            # per-market published while fixture no_bet
            any_market_pub = False
            for g in MARKET_GROUPS:
                st = _market_group_status(markets_doc, g)
                market_stats[g][st] += 1
                if st == "published":
                    any_market_pub = True
            if any_market_pub:
                market_specific_only += 1
        else:
            published_fixtures += 1
            for g in MARKET_GROUPS:
                market_stats[g][_market_group_status(markets_doc, g)] += 1

    avg_conf = round(sum(confidence_values) / len(confidence_values), 1) if confidence_values else 0
    avg_dq = round(sum(dq_values) / len(dq_values), 1) if dq_values else 0

    return {
        "total_fixtures": total,
        "no_bet_fixtures": no_bet_fixtures,
        "published_fixtures": published_fixtures,
        "no_bet_rate_pct": round(100.0 * no_bet_fixtures / total, 1) if total else 0,
        "reason_aggregate": dict(reason_counter.most_common()),
        "market_breakdown": {g: dict(c) for g, c in market_stats.items()},
        "hidden_best_available": {
            "fixtures_with_best_pick_in_payload": has_best_pick_hidden,
            "fixtures_with_quality_or_strong_hidden": hidden_candidates,
            "pct_of_no_bet": round(100.0 * has_best_pick_hidden / no_bet_fixtures, 1) if no_bet_fixtures else 0,
            "market_specific_while_fixture_no_bet": market_specific_only,
        },
        "threshold_impact": dict(threshold_rejections.most_common()),
        "averages": {"confidence": avg_conf, "data_quality": avg_dq},
        "sample_no_bet_fixtures": [
            {
                "fixture_id": fid,
                "reasons": reason_by_fixture.get(fid, []),
                "confidence": next(
                    (s.get("payload", {}).get("confidence") for s in snapshots if int(s.get("fixture_id", 0)) == fid),
                    None,
                ),
                "best_available": bool(
                    next(
                        (s.get("payload", {}).get("best_available_pick") for s in snapshots if int(s.get("fixture_id", 0)) == fid),
                        None,
                    )
                ),
            }
            for fid in list(reason_by_fixture.keys())[:8]
        ],
    }


def main() -> int:
    data = run_audit()
    out_path = ROOT / "data" / "validation" / "phase_a15_5_wde_publication_audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(json.dumps(data, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
