"""S5 promotion gate evaluation for EVAL-COVERAGE-1."""

from __future__ import annotations

from typing import Any

PHASE = "EVAL-COVERAGE-1"
MIN_MATCHES = 40
MIN_S5_RATE = 58.0
MIN_DELTA_PP = 5.0


def evaluate_s5_promotion_gate(
    optimizer_payload: dict[str, Any],
    *,
    odds_freshness: dict[str, Any] | None = None,
) -> dict[str, Any]:
    n = int(optimizer_payload.get("finished_count") or 0)
    baseline = optimizer_payload.get("baseline_audit") or {}
    raw_rate = float(baseline.get("raw_top3_hit_rate_pct") or 0)
    strategies = optimizer_payload.get("strategy_summary") or {}
    s5 = strategies.get("S5_conservative_coverage") or {}
    s5_all = (s5.get("segments") or {}).get("all") or {}
    s5_rate = float(s5_all.get("top3_hit_rate_pct") or 0)
    delta = round(s5_rate - raw_rate, 1)

    best_id = optimizer_payload.get("best_strategy_id") or ""
    best_rate = float(optimizer_payload.get("best_top3_hit_rate_pct") or 0)
    s5_is_best = "S5" in best_id or abs(best_rate - s5_rate) < 0.05

    seg_ok = True
    regressions: list[str] = []
    for seg in ("knockout", "group_stage"):
        seg_data = (s5.get("segments") or {}).get(seg) or {}
        seg_n = int(seg_data.get("count") or 0)
        if seg_n == 0:
            continue
        seg_delta = float(seg_data.get("delta_vs_raw_pp") or 0)
        if seg_delta < -5:
            seg_ok = False
            regressions.append(f"{seg}: {seg_delta}pp")

    odds = odds_freshness or {}
    stale_n = (odds.get("counts") or {}).get("STALE_ODDS", 0)
    total_n = odds.get("fixture_count") or n
    odds_blocked = total_n > 0 and stale_n == total_n

    checks = {
        "evaluated_matches_gte_40": n >= MIN_MATCHES,
        "s5_top3_gte_58": s5_rate >= MIN_S5_RATE,
        "s5_delta_gte_5pp": delta >= MIN_DELTA_PP,
        "s5_best_or_tied": s5_is_best,
        "no_major_segment_regression": seg_ok,
        "odds_freshness_not_invalidating": not odds_blocked,
    }
    passed = sum(1 for v in checks.values() if v)

    if odds_blocked and not checks["evaluated_matches_gte_40"]:
        decision = "S5_BLOCKED_BY_ODDS_FRESHNESS"
    elif not checks["evaluated_matches_gte_40"]:
        decision = "S5_NEEDS_MORE_DATA"
    elif not checks["s5_top3_gte_58"]:
        decision = "S5_FAILS_HITRATE_GATE"
    elif not checks["s5_delta_gte_5pp"]:
        decision = "S5_FAILS_BASELINE_DELTA_GATE"
    elif not checks["no_major_segment_regression"]:
        decision = "S5_FAILS_SEGMENT_STABILITY"
    elif checks["evaluated_matches_gte_40"] and passed >= 5:
        decision = "S5_PROMOTION_GATE_PASSED_FOR_OWNER_PREVIEW"
    else:
        decision = "S5_NEEDS_MORE_DATA"

    return {
        "phase": PHASE,
        "decision": decision,
        "checks": checks,
        "checks_passed": passed,
        "checks_total": len(checks),
        "evaluated_matches": n,
        "needed_matches": max(0, MIN_MATCHES - n),
        "raw_top3_pct": raw_rate,
        "s5_top3_pct": s5_rate,
        "delta_pp": delta,
        "best_strategy": best_id,
        "segment_regressions": regressions,
        "odds_all_stale": odds_blocked,
        "do_not_promote": True,
    }
