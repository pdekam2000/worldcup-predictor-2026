"""PHASE ECSE-ODDALERTS-3/4 — segment scoring for OddAlerts shadow predictions."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEGMENT_MODEL_V1 = "oddalerts_ecse_segments_v1_initial"
SEGMENT_MODEL_V2 = "oddalerts_ecse_segments_v2_calibrated"
PROCESS_DATE = "2026-06-30"
MIN_CALIBRATION_SAMPLE = 20

# Evaluated Top-1 rates from ECSE-ODDALERTS-2 shadow evaluation (185 finished fixtures).
COMPETITION_TOP1_PRIOR: dict[str, float] = {
    "bundesliga": 0.1408,
    "premier_league": 0.1286,
    "world_cup_2026": 0.0682,
}

PROMOTION_TOP1_PRIOR: dict[str, float] = {
    "inserted": 0.137,
    "enriched": 0.1071,
}

BADGE_THRESHOLDS = (
    (75, "STRONG_SHADOW_SIGNAL"),
    (55, "MEDIUM_SHADOW_SIGNAL"),
    (35, "WEAK_SHADOW_SIGNAL"),
    (20, "WATCH_ONLY"),
    (0, "DO_NOT_USE"),
)


def score_to_outcome(score: str | None) -> str | None:
    if not score or "-" not in score:
        return None
    parts = score.split("-", 1)
    try:
        h, a = int(parts[0]), int(parts[1])
    except ValueError:
        return None
    if h > a:
        return "home"
    if h < a:
        return "away"
    return "draw"


def implied_1x2_pick(probs: dict[str, Any]) -> str | None:
    home = probs.get("match_result_home")
    draw = probs.get("match_result_draw")
    away = probs.get("match_result_away")
    if home is None or draw is None or away is None:
        return None
    vals = {"home": float(home), "draw": float(draw), "away": float(away)}
    return max(vals, key=vals.get)


def _parse_probs(raw: str | dict | None) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        val = json.loads(raw)
        return val if isinstance(val, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def _market_inconsistency_flags(probs: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    h = probs.get("match_result_home")
    d = probs.get("match_result_draw")
    a = probs.get("match_result_away")
    if h is not None and d is not None and a is not None:
        total = float(h) + float(d) + float(a)
        if abs(total - 100.0) > 2.5:
            flags.append("1x2_sum_off")
    ou_o = probs.get("goals_over_2_5")
    ou_u = probs.get("goals_under_2_5")
    if ou_o is not None and ou_u is not None:
        total = float(ou_o) + float(ou_u)
        if abs(total - 100.0) > 2.5:
            flags.append("ou25_sum_off")
    btts_y = probs.get("btts_yes")
    btts_n = probs.get("btts_no")
    if btts_y is not None and btts_n is not None:
        total = float(btts_y) + float(btts_n)
        if abs(total - 100.0) > 2.5:
            flags.append("btts_sum_off")
    return flags


def _draw_market_supports_1x1(probs: dict[str, Any], top1: str | None) -> bool:
    if top1 != "1-1":
        return True
    draw = probs.get("match_result_draw")
    if draw is None:
        return False
    return float(draw) >= 22.0


def score_shadow_segment(
    row: dict[str, Any],
    *,
    wde_direction: str | None = None,
    ecse_direction: str | None = None,
) -> dict[str, Any]:
    """Score a shadow row for owner lab usefulness (0–100)."""
    reasons: list[str] = []
    cautions: list[str] = []

    lh = float(row.get("lambda_home") or 0)
    la = float(row.get("lambda_away") or 0)
    top1 = row.get("top_1_score")
    shadow_outcome = score_to_outcome(top1)
    probs = _parse_probs(row.get("input_market_probabilities_json"))
    book_pick = implied_1x2_pick(probs)
    promo = str(row.get("promotion_action") or "unknown").lower()
    comp = str(row.get("competition") or "unknown").lower()
    crosswalk = str(row.get("crosswalk_confidence") or "").upper()

    score = 50.0

    if promo == "inserted":
        score += 8
        reasons.append("inserted_snapshot (+8)")
    elif promo == "enriched":
        score -= 3
        cautions.append("enriched_snapshot (-3)")

    comp_prior = COMPETITION_TOP1_PRIOR.get(comp)
    if comp_prior is not None:
        if comp_prior >= 0.13:
            score += 6
            reasons.append(f"strong_competition_{comp} (+6)")
        elif comp_prior < 0.09:
            score -= 10
            cautions.append(f"weak_competition_{comp} (-10)")

    if book_pick and shadow_outcome and book_pick == shadow_outcome:
        score += 12
        reasons.append("bookmaker_1x2_agrees (+12)")
    elif book_pick and shadow_outcome and book_pick != shadow_outcome:
        score -= 6
        cautions.append("bookmaker_1x2_disagrees (-6)")

    total_lambda = lh + la
    if 1.8 <= total_lambda <= 3.2 and 0.6 <= lh <= 2.8 and 0.4 <= la <= 2.2:
        score += 8
        reasons.append("sane_lambda_mid_range (+8)")
    elif lh > 3.5 or la > 3.0 or lh < 0.45 or la < 0.25:
        score -= 12
        cautions.append("extreme_lambda (-12)")

    if "HIGH" in crosswalk or crosswalk == "MATCHED_HIGH_CONFIDENCE":
        score += 5
        reasons.append("high_crosswalk (+5)")
    elif crosswalk and "LOW" in crosswalk:
        score -= 8
        cautions.append("low_crosswalk (-8)")

    if top1 == "1-1":
        if _draw_market_supports_1x1(probs, top1):
            score -= 2
            cautions.append("top1_1x1_concentration_mild (-2)")
        else:
            score -= 10
            cautions.append("top1_1x1_without_draw_support (-10)")

    inconsistency = _market_inconsistency_flags(probs)
    if inconsistency:
        score -= 5 * len(inconsistency)
        cautions.append(f"market_inconsistency:{','.join(inconsistency)}")

    if wde_direction and shadow_outcome and wde_direction != shadow_outcome:
        score -= 8
        cautions.append("wde_disagrees (-8)")

    if ecse_direction and shadow_outcome and ecse_direction != shadow_outcome:
        cautions.append("ecse_production_disagrees")

    warning_flags = row.get("warning_flags_json")
    if isinstance(warning_flags, str):
        try:
            warning_flags = json.loads(warning_flags)
        except json.JSONDecodeError:
            warning_flags = []
    if warning_flags:
        score -= min(10, 2 * len(warning_flags))
        cautions.append(f"warning_flags (-{min(10, 2 * len(warning_flags))})")

    score = max(0.0, min(100.0, round(score, 1)))

    badge = "DO_NOT_USE"
    for threshold, label in BADGE_THRESHOLDS:
        if score >= threshold:
            badge = label
            break

    if badge in ("STRONG_SHADOW_SIGNAL", "MEDIUM_SHADOW_SIGNAL"):
        promotion_eligibility = "eligible_limited_write_later"
    elif badge == "WEAK_SHADOW_SIGNAL":
        promotion_eligibility = "eligible_shadow_watch"
    else:
        promotion_eligibility = "not_eligible"

    if comp == "world_cup_2026" and badge == "STRONG_SHADOW_SIGNAL":
        promotion_eligibility = "eligible_shadow_watch"
        cautions.append("world_cup_caution_downgrade")

    return {
        "segment_score": score,
        "segment_badge": badge,
        "reasons": reasons,
        "cautions": cautions,
        "promotion_eligibility": promotion_eligibility,
        "shadow_outcome": shadow_outcome,
        "bookmaker_implied_direction": book_pick,
        "wde_direction": wde_direction,
        "ecse_production_direction": ecse_direction,
    }


def segment_recommendation_filter_match(row: dict[str, Any], segment: dict[str, Any], recommendation: str | None) -> bool:
    if not recommendation:
        return True
    key = recommendation.strip().upper()
    badge = segment.get("segment_badge", "")
    elig = segment.get("promotion_eligibility", "")
    if key in ("STRONG", "STRONG_SHADOW_SIGNAL"):
        return badge == "STRONG_SHADOW_SIGNAL"
    if key in ("MEDIUM", "MEDIUM_SHADOW_SIGNAL"):
        return badge == "MEDIUM_SHADOW_SIGNAL"
    if key in ("WEAK", "WEAK_SHADOW_SIGNAL"):
        return badge == "WEAK_SHADOW_SIGNAL"
    if key in ("WATCH", "WATCH_ONLY"):
        return badge == "WATCH_ONLY"
    if key in ("DO_NOT_USE", "NOT_ELIGIBLE"):
        return badge == "DO_NOT_USE" or elig == "not_eligible"
    if key == "ELIGIBLE_LIMITED_WRITE":
        return elig == "eligible_limited_write_later"
    if key == "ELIGIBLE_SHADOW_WATCH":
        return elig == "eligible_shadow_watch"
    return badge == key or elig == key.lower()


def _load_calibration_artifact(path: Path | None = None) -> dict[str, Any] | None:
    p = path or Path(f"artifacts/ecse_oddalerts_segment_calibration_{PROCESS_DATE.replace('-', '')}.json")
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _bucket_rate(calibration: dict[str, Any], bucket_id: str) -> dict[str, Any] | None:
    return (calibration.get("buckets") or {}).get(bucket_id)


def _utility_from_calibration(
    feature: dict[str, Any],
    calibration: dict[str, Any],
) -> tuple[float, float, float, list[str], list[str]]:
    """Return (utility_score, expected_top3, expected_top5, reasons, cautions)."""
    baseline = calibration.get("baseline") or {}
    base_t3 = float(baseline.get("top3_hit_rate") or 0.2919)
    base_t5 = float(baseline.get("top5_hit_rate") or 0.4432)
    base_t1 = float(baseline.get("top1_hit_rate") or 0.1189)

    from worldcup_predictor.research.oddalerts_ecse_segment_calibration import bucket_keys_for_feature

    reasons: list[str] = []
    cautions: list[str] = []
    t3_rates: list[float] = []
    t5_rates: list[float] = []
    t1_rates: list[float] = []
    weights: list[float] = []

    for dim, val in bucket_keys_for_feature(feature):
        bid = f"{dim}:{val}"
        b = _bucket_rate(calibration, bid)
        if not b or not b.get("sample_size"):
            continue
        n = int(b["sample_size"])
        w = 1.0 if n >= MIN_CALIBRATION_SAMPLE else 0.35
        if n < MIN_CALIBRATION_SAMPLE:
            cautions.append(f"caution_low_n:{bid}(n={n})")
        else:
            lift3 = round((b.get("top3_hit_rate") or 0) - base_t3, 4)
            if lift3 >= 0.05:
                reasons.append(f"{bid}_top3_lift_{lift3}")
            elif lift3 <= -0.05:
                cautions.append(f"{bid}_top3_penalty_{lift3}")
        t3_rates.append(float(b.get("top3_hit_rate") or base_t3))
        t5_rates.append(float(b.get("top5_hit_rate") or base_t5))
        t1_rates.append(float(b.get("top1_hit_rate") or base_t1))
        weights.append(w)

    if not t3_rates:
        exp_t3, exp_t5, exp_t1 = base_t3, base_t5, base_t1
    else:
        wsum = sum(weights)
        exp_t3 = sum(r * w for r, w in zip(t3_rates, weights)) / wsum
        exp_t5 = sum(r * w for r, w in zip(t5_rates, weights)) / wsum
        exp_t1 = sum(r * w for r, w in zip(t1_rates, weights)) / wsum

    utility = round((exp_t3 * 0.55 + exp_t5 * 0.30 + exp_t1 * 0.15) * 100, 2)
    return utility, round(exp_t3, 4), round(exp_t5, 4), reasons, cautions


def score_shadow_segment_v2(
    row: dict[str, Any],
    feature: dict[str, Any],
    *,
    calibration: dict[str, Any] | None = None,
    wde_direction: str | None = None,
    utility_percentiles: tuple[float, float] | None = None,
) -> dict[str, Any]:
    """Calibrated v2 segment score — evidence-based, Top3/Top5 primary."""
    calibration = calibration or _load_calibration_artifact()
    if not calibration:
        v1 = score_shadow_segment(row, wde_direction=wde_direction)
        return {
            **v1,
            "segment_model_version": SEGMENT_MODEL_V2,
            "segment_score_v2": v1["segment_score"],
            "segment_badge_v2": v1["segment_badge"],
            "reasons_v2": v1["reasons"] + ["calibration_artifact_missing_fallback_v1"],
            "cautions_v2": v1["cautions"],
            "promotion_eligibility_v2": v1["promotion_eligibility"],
            "expected_top3_rate": None,
            "expected_top5_rate": None,
            "top5_value_signal": False,
        }

    utility, exp_t3, exp_t5, reasons, cautions = _utility_from_calibration(feature, calibration)

    probs = _parse_probs(row.get("input_market_probabilities_json"))
    top1 = row.get("top_1_score")
    promo = str(row.get("promotion_action") or "").lower()
    comp = str(row.get("competition") or "").lower()

    # Evidence-based adjustments (only when calibration bucket supports, n>=20)
    buckets = calibration.get("buckets") or {}
    ins = buckets.get("promotion_action:inserted")
    enr = buckets.get("promotion_action:enriched")
    if ins and enr and ins.get("sample_size", 0) >= MIN_CALIBRATION_SAMPLE and enr.get("sample_size", 0) >= MIN_CALIBRATION_SAMPLE:
        if promo == "inserted" and (ins.get("top3_hit_rate") or 0) > (enr.get("top3_hit_rate") or 0):
            reasons.append("inserted_top3_benefit_confirmed")
        elif promo == "enriched":
            cautions.append("enriched_lower_top3_prior")

    wc = buckets.get("competition:world_cup_2026")
    if comp == "world_cup_2026" and wc and wc.get("sample_size", 0) >= MIN_CALIBRATION_SAMPLE:
        if (wc.get("top3_hit_rate") or 0) < (calibration.get("baseline") or {}).get("top3_hit_rate", 0.29):
            cautions.append("world_cup_top3_below_baseline")
    elif comp == "world_cup_2026" and wc and wc.get("sample_size", 0) < MIN_CALIBRATION_SAMPLE:
        cautions.append("world_cup_sample_too_small_caution_only")

    if top1 == "1-1":
        draw = probs.get("match_result_draw")
        book = implied_1x2_pick(probs)
        draw_supported = draw is not None and float(draw) >= 22.0
        book_draw = book == "draw"
        if not draw_supported and not book_draw:
            cautions.append("unsupported_1_1_top1")
        else:
            reasons.append("1_1_with_draw_support")

    book_agrees = feature.get("bookmaker_agreement")
    ba_bucket = buckets.get(f"bookmaker_agreement:{book_agrees}")
    if ba_bucket and ba_bucket.get("sample_size", 0) >= MIN_CALIBRATION_SAMPLE and book_agrees is True:
        if (ba_bucket.get("top3_hit_rate") or 0) >= (calibration.get("baseline") or {}).get("top3_hit_rate", 0):
            reasons.append("bookmaker_agreement_top3_lift")

    wde_cov = sum(1 for b in buckets if b.startswith("wde_agreement:") and buckets[b].get("sample_size", 0) > 0)
    if wde_direction and feature.get("wde_agreement") is False and wde_cov >= 2:
        cautions.append("wde_disagrees_caution")
    elif wde_direction is None:
        cautions.append("wde_coverage_low")

    top5_value = exp_t5 >= 0.48 and (feature.get("top1_concentration") or 0) < 0.14
    if top5_value:
        reasons.append("TOP5_VALUE_SIGNAL")

    # Badge from utility percentiles (computed externally) or fixed cutoffs on utility scale
    p33, p67 = utility_percentiles or (32.0, 36.0)
    if utility >= p67:
        badge = "STRONG_SHADOW_SIGNAL"
    elif utility >= p33:
        badge = "MEDIUM_SHADOW_SIGNAL"
    else:
        badge = "WEAK_SHADOW_SIGNAL"

    if top5_value and badge == "WEAK_SHADOW_SIGNAL" and exp_t5 >= 0.50:
        badge = "MEDIUM_SHADOW_SIGNAL"
        reasons.append("top5_value_badge_upgrade")

    if badge == "STRONG_SHADOW_SIGNAL" and exp_t3 < (calibration.get("baseline") or {}).get("top3_hit_rate", 0.29):
        badge = "MEDIUM_SHADOW_SIGNAL"
        cautions.append("strong_downgrade_below_baseline_top3")

    if badge in ("STRONG_SHADOW_SIGNAL", "MEDIUM_SHADOW_SIGNAL") and exp_t3 >= 0.30:
        elig = "eligible_limited_write_later"
    elif badge == "MEDIUM_SHADOW_SIGNAL" or top5_value:
        elig = "eligible_shadow_watch"
    else:
        elig = "not_eligible"

    if comp == "world_cup_2026" and elig == "eligible_limited_write_later":
        elig = "eligible_shadow_watch"
        cautions.append("world_cup_promotion_watch_only")

    return {
        "segment_model_version": SEGMENT_MODEL_V2,
        "segment_score_v2": utility,
        "segment_badge_v2": badge,
        "reasons_v2": reasons,
        "cautions_v2": cautions,
        "promotion_eligibility_v2": elig,
        "expected_top3_rate": exp_t3,
        "expected_top5_rate": exp_t5,
        "top5_value_signal": top5_value,
        "shadow_outcome": feature.get("top_1_outcome"),
        "bookmaker_implied_direction": feature.get("bookmaker_implied_direction"),
        "wde_direction": wde_direction,
    }


def load_v2_calibration_context() -> dict[str, Any]:
    """Load calibration artifact and v2 utility percentiles from rescored cache if present."""
    calibration = _load_calibration_artifact()
    tag = PROCESS_DATE.replace("-", "")
    rescored_path = Path(f"artifacts/ecse_oddalerts_owner_lab_rescored_v2_{tag}.json")
    utility_percentiles = None
    if rescored_path.exists():
        try:
            rescored = json.loads(rescored_path.read_text(encoding="utf-8"))
            utility_percentiles = tuple(
                rescored.get("utility_percentiles", {}).get(k)
                for k in ("p33", "p67")
            )
            if None in utility_percentiles:
                utility_percentiles = None
            else:
                utility_percentiles = (float(utility_percentiles[0]), float(utility_percentiles[1]))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            utility_percentiles = None
    return {
        "calibration": calibration,
        "utility_percentiles": utility_percentiles,
    }


def compute_utility_percentiles(utilities: list[float]) -> tuple[float, float]:
    if not utilities:
        return 32.0, 36.0
    sorted_u = sorted(utilities)
    n = len(sorted_u)

    def pct(p: float) -> float:
        idx = min(n - 1, max(0, int(p * n)))
        return sorted_u[idx]

    return round(pct(0.33), 2), round(pct(0.67), 2)


def badge_performance(rows: list[dict[str, Any]], badge_key: str = "segment_badge") -> dict[str, Any]:
    finished = [r for r in rows if r.get("finished")]
    out: dict[str, Any] = {}
    for badge in ("STRONG_SHADOW_SIGNAL", "MEDIUM_SHADOW_SIGNAL", "WEAK_SHADOW_SIGNAL", "WATCH_ONLY", "DO_NOT_USE"):
        grp = [r for r in finished if r.get(badge_key) == badge]
        n = len(grp)
        if not n:
            out[badge] = {"count": 0}
            continue
        out[badge] = {
            "count": n,
            "top1_hit_rate": round(sum(1 for r in grp if r.get("top1_hit")) / n, 4),
            "top3_hit_rate": round(sum(1 for r in grp if r.get("top3_hit")) / n, 4),
            "top5_hit_rate": round(sum(1 for r in grp if r.get("top5_hit")) / n, 4),
            "top10_hit_rate": round(sum(1 for r in grp if r.get("top10_hit")) / n, 4),
        }
    return out


def check_monotonicity(perf: dict[str, Any], *, primary: str = "top3_hit_rate") -> dict[str, Any]:
    strong = (perf.get("STRONG_SHADOW_SIGNAL") or {}).get(primary)
    medium = (perf.get("MEDIUM_SHADOW_SIGNAL") or {}).get(primary)
    weak = (perf.get("WEAK_SHADOW_SIGNAL") or {}).get(primary)
    monotonic = None
    if strong is not None and medium is not None and weak is not None:
        monotonic = strong >= medium >= weak
    return {
        "primary_metric": primary,
        "strong": strong,
        "medium": medium,
        "weak": weak,
        "monotonic": monotonic,
    }
