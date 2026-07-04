"""Shadow vs baseline evaluation metrics — read-only."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.research.ecse_rerank.features import total_goals, winner_side


def _hit(actual: str | None, candidates: list[str] | None) -> bool:
    if not actual or not candidates:
        return False
    return actual in candidates


def _hit_top1(actual: str | None, top1: str | None) -> bool:
    return bool(actual and top1 and actual == top1)


def _goal_error(actual: str | None, predicted: str | None) -> float | None:
    if not actual or not predicted:
        return None
    try:
        ah, aa = map(int, actual.split("-"))
        ph, pa = map(int, predicted.split("-"))
        return abs((ah + aa) - (ph + pa))
    except ValueError:
        return None


def _is_clean_sheet_line(line: str | None) -> bool:
    if not line or "-" not in line:
        return False
    h, a = map(int, line.split("-"))
    return h == 0 or a == 0


def evaluate_single_match(
    *,
    actual_90min: str | None,
    baseline_top1: str | None,
    baseline_top3: list[str],
    baseline_top5: list[str],
    shadow_top1: str | None,
    shadow_top3: list[str],
    shadow_top5: list[str],
    wde_1x2: str | None,
    wde_btts: str | None,
    wde_ou: str | None,
    ended_aet: bool = False,
    ended_pen: bool = False,
) -> dict[str, Any]:
    if not actual_90min:
        return {"evaluated": False}

    def actual_1x2():
        h, a = map(int, actual_90min.split("-"))
        if h > a:
            return "home_win"
        if h < a:
            return "away_win"
        return "draw"

    def actual_btts():
        h, a = map(int, actual_90min.split("-"))
        return "yes" if h > 0 and a > 0 else "no"

    def actual_ou():
        h, a = map(int, actual_90min.split("-"))
        return "over_2_5" if h + a > 2 else "under_2_5"

    a1 = actual_1x2()
    ab = actual_btts()
    aou = actual_ou()

    def btts_consistent(top1: str | None) -> bool | None:
        if not top1 or not wde_btts:
            return None
        pred_btts = "yes" if _is_btts_line(top1) else "no"
        return (wde_btts == "yes") == (pred_btts == "yes")

    def ou_consistent(top1: str | None) -> bool | None:
        if not top1 or not wde_ou:
            return None
        tg = total_goals(top1) or 0
        pred_ou = "over_2_5" if tg > 2 else "under_2_5"
        ou = str(wde_ou).lower()
        if "over" in ou:
            return pred_ou == "over_2_5"
        if "under" in ou:
            return pred_ou == "under_2_5"
        return pred_ou == wde_ou

    def winner_preserved(top1: str | None) -> bool | None:
        if not top1 or not wde_1x2:
            return None
        return winner_side(top1) == wde_1x2

    return {
        "evaluated": True,
        "actual_90min": actual_90min,
        "ended_in_extra_time": ended_aet,
        "ended_on_penalties": ended_pen,
        "baseline_top1_hit": _hit_top1(actual_90min, baseline_top1),
        "baseline_top3_hit": _hit(actual_90min, baseline_top3),
        "baseline_top5_hit": _hit(actual_90min, baseline_top5),
        "shadow_top1_hit": _hit_top1(actual_90min, shadow_top1),
        "shadow_top3_hit": _hit(actual_90min, shadow_top3),
        "shadow_top5_hit": _hit(actual_90min, shadow_top5),
        "baseline_goal_error": _goal_error(actual_90min, baseline_top1),
        "shadow_goal_error": _goal_error(actual_90min, shadow_top1),
        "baseline_clean_sheet_top1": _is_clean_sheet_line(baseline_top1),
        "shadow_clean_sheet_top1": _is_clean_sheet_line(shadow_top1),
        "wde_1x2_correct": wde_1x2 == a1 if wde_1x2 else None,
        "wde_btts_correct": wde_btts == ab if wde_btts else None,
        "wde_ou_correct": (wde_ou == aou or _ou_match(wde_ou, aou)) if wde_ou else None,
        "baseline_btts_consistent": btts_consistent(baseline_top1),
        "shadow_btts_consistent": btts_consistent(shadow_top1),
        "baseline_ou_consistent": ou_consistent(baseline_top1),
        "shadow_ou_consistent": ou_consistent(shadow_top1),
        "baseline_winner_preserved": winner_preserved(baseline_top1),
        "shadow_winner_preserved": winner_preserved(shadow_top1),
    }


def _is_btts_line(line: str) -> bool:
    h, a = map(int, line.split("-"))
    return h > 0 and a > 0


def _ou_match(wde_ou: str | None, actual: str) -> bool:
    if not wde_ou:
        return False
    w = str(wde_ou).lower()
    if "over" in w:
        return actual == "over_2_5"
    if "under" in w:
        return actual == "under_2_5"
    return wde_ou == actual


def aggregate_metrics(rows: list[dict[str, Any]], segment: str = "all") -> dict[str, Any]:
    ev = [r for r in rows if r.get("evaluated")]
    n = len(ev) or 1

    def rate(key: str) -> float | None:
        vals = [r[key] for r in ev if r.get(key) is True]
        total = sum(1 for r in ev if r.get(key) is not None)
        return round(100 * len(vals) / total, 1) if total else None

    def avg(key: str) -> float | None:
        vals = [r[key] for r in ev if r.get(key) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    return {
        "segment": segment,
        "count": len(ev),
        "baseline_top1_hit_rate_pct": rate("baseline_top1_hit"),
        "baseline_top3_hit_rate_pct": rate("baseline_top3_hit"),
        "baseline_top5_hit_rate_pct": rate("baseline_top5_hit"),
        "shadow_top1_hit_rate_pct": rate("shadow_top1_hit"),
        "shadow_top3_hit_rate_pct": rate("shadow_top3_hit"),
        "shadow_top5_hit_rate_pct": rate("shadow_top5_hit"),
        "baseline_avg_goal_error": avg("baseline_goal_error"),
        "shadow_avg_goal_error": avg("shadow_goal_error"),
        "baseline_clean_sheet_top1_rate_pct": rate("baseline_clean_sheet_top1"),
        "shadow_clean_sheet_top1_rate_pct": rate("shadow_clean_sheet_top1"),
        "baseline_btts_consistency_pct": rate("baseline_btts_consistent"),
        "shadow_btts_consistency_pct": rate("shadow_btts_consistent"),
        "baseline_ou_consistency_pct": rate("baseline_ou_consistent"),
        "shadow_ou_consistency_pct": rate("shadow_ou_consistent"),
        "baseline_winner_preserved_pct": rate("baseline_winner_preserved"),
        "shadow_winner_preserved_pct": rate("shadow_winner_preserved"),
        "wde_1x2_accuracy_pct": rate("wde_1x2_correct"),
        "wde_btts_accuracy_pct": rate("wde_btts_correct"),
        "wde_ou_accuracy_pct": rate("wde_ou_correct"),
        "aet_pen_count": sum(1 for r in ev if r.get("ended_in_extra_time") or r.get("ended_on_penalties")),
    }


def evaluate_shadow_vs_baseline(match_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate baseline vs shadow across segments."""
    all_ev = [r.get("evaluation") or {} for r in match_rows if (r.get("evaluation") or {}).get("evaluated")]
    segments: dict[str, list] = {"all": all_ev}
    for r in match_rows:
        ev = r.get("evaluation")
        if not ev or not ev.get("evaluated"):
            continue
        seg = r.get("segment") or "all"
        segments.setdefault(seg, []).append(ev)
        if r.get("odds_freshness", {}).get("freshness_flag") == "FRESH_ODDS":
            segments.setdefault("fresh_odds", []).append(ev)
        elif r.get("odds_freshness", {}).get("freshness_flag") == "STALE_ODDS":
            segments.setdefault("stale_odds", []).append(ev)
        else:
            segments.setdefault("unknown_odds", []).append(ev)

    metrics = {name: aggregate_metrics(rows, name) for name, rows in segments.items()}
    return {"segments": metrics, "match_count": len(match_rows)}
