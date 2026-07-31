"""Day-level prematch feature construction — research-only, no result leakage."""

from __future__ import annotations

import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from typing import Any

from worldcup_predictor.research.bet_portfolio_manager.input_adapter import attach_outcomes, normalize_fixture
from worldcup_predictor.research.betting_day_similarity.constants import FORBIDDEN_LIVE_FEATURES
from worldcup_predictor.research.betting_day_similarity.schemas import FEATURE_GROUPS


def _safe_mean(vals: list[float], default: float = 0.0) -> float:
    return float(sum(vals) / len(vals)) if vals else default


def _safe_median(vals: list[float], default: float = 0.0) -> float:
    return float(statistics.median(vals)) if vals else default


def _safe_stdev(vals: list[float], default: float = 0.0) -> float:
    if len(vals) < 2:
        return default
    return float(statistics.pstdev(vals))


def _hash_obj(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _tier_bucket(conf: float) -> str:
    if conf >= 0.85:
        return "S"
    if conf >= 0.70:
        return "A"
    if conf >= 0.55:
        return "B"
    return "lower"


def _competition_tier(league: str) -> float:
    lg = (league or "").lower()
    if any(x in lg for x in ("premier", "la liga", "bundesliga", "serie a", "ligue 1", "champions")):
        return 1.0
    if any(x in lg for x in ("championship", "2.", "segunda", "serie b")):
        return 2.0
    if any(x in lg for x in ("women", "u21", "u19", "reserve", "youth", "friendly")):
        return 4.0
    return 3.0


def _is_special_comp(league: str) -> bool:
    lg = (league or "").lower()
    return any(x in lg for x in ("women", "u21", "u19", "reserve", "youth", "friendly", "club friendly"))


def build_day_feature_vector(
    fixtures: list[dict[str, Any]],
    *,
    date: str,
    cutoff_timestamp: str,
    rolling_stats: dict[str, float] | None = None,
    baseline_decision: dict[str, Any] | None = None,
    calibrated_decision: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Prematch-only day feature vector.
    Outcomes on fixtures are ignored for feature values (may exist for later labels).
    """
    rows = [attach_outcomes(normalize_fixture(fx)) for fx in fixtures]
    n = len(rows) or 1
    confs = [float(r.get("confidence") or 0.0) for r in rows]
    ents = [float(r.get("entropy") or 0.0) for r in rows]
    top5 = [float(r.get("top5_mass") or r.get("confidence") or 0.0) for r in rows]
    residuals = [float(r.get("residual_risk") or 0.0) for r in rows]
    ins = [float(r.get("insurance_contribution") or 0.0) for r in rows]
    cov = [float(r.get("coverage_mass") or 0.0) for r in rows]
    odds = [float(r.get("odds_home") or 0.0) for r in rows if r.get("odds_home")]
    leagues = [str(r.get("league") or "unknown") for r in rows]
    league_counts = Counter(leagues)
    n_leagues = len(league_counts) or 1
    max_share = max(league_counts.values()) / n
    herfindahl = sum((c / n) ** 2 for c in league_counts.values())

    # Kickoff concentration: unique kickoff strings
    kickoffs = [str(r.get("kickoff") or date)[:16] for r in rows]
    ko_counts = Counter(kickoffs)
    simultaneous = max(ko_counts.values()) if ko_counts else 0
    # Evening proxy: if kickoff has hour >= 17 (when available)
    evening = 0
    for k in kickoffs:
        if len(k) >= 13 and k[11:13].isdigit():
            if int(k[11:13]) >= 17:
                evening += 1
        else:
            evening += 0  # unknown -> daytime default
    evening_ratio = evening / n

    tiers = [_tier_bucket(c) for c in confs]
    tier_c = Counter(tiers)
    special = 1.0 if any(_is_special_comp(lg) for lg in leagues) else 0.0

    # Market proxies
    balanced = sum(1 for o in odds if 1.70 <= o <= 2.40) / max(1, len(odds))
    one_sided = sum(1 for o in odds if o < 1.45 or o > 3.5) / max(1, len(odds))
    fav_bucket = 0.0
    if odds:
        m = _safe_median(odds)
        fav_bucket = 0.0 if m < 1.6 else (1.0 if m < 2.2 else 2.0)

    # Coupon proxies from decision metadata
    base = baseline_decision or {}
    cal = calibrated_decision or {}
    n_sel_base = len(base.get("selected_fixture_ids") or [])
    n_sel_cal = len(cal.get("selected_fixture_ids") or [])
    elig = sum(1 for c in confs if c >= 0.45)

    # Market families
    families: list[str] = []
    for r in rows:
        if r.get("main_market_label"):
            families.append(str(r["main_market_label"]))
        if r.get("insurance_market_label"):
            families.append(str(r["insurance_market_label"]))
    fam_c = Counter(families)
    fam_entropy = 0.0
    if fam_c:
        tot = sum(fam_c.values())
        for c in fam_c.values():
            p = c / tot
            fam_entropy -= p * math.log(p + 1e-12)

    rolling = rolling_stats or {}
    features: dict[str, float] = {
        # slate
        "n_discovered_fixtures": float(len(rows)),
        "n_eligible_fixtures": float(elig),
        "n_selected_fixtures": float(n_sel_base),
        "n_countries": float(n_leagues),  # proxy when country absent
        "n_leagues": float(n_leagues),
        "league_concentration": float(herfindahl),
        "max_league_share": float(max_share),
        "avg_fixtures_per_league": float(len(rows) / n_leagues),
        "reserve_youth_women_friendly_flag": special,
        "avg_competition_tier": _safe_mean([_competition_tier(lg) for lg in leagues], 3.0),
        "pct_tier_s": tier_c.get("S", 0) / n,
        "pct_tier_a": tier_c.get("A", 0) / n,
        "pct_tier_b": tier_c.get("B", 0) / n,
        "pct_tier_lower": tier_c.get("lower", 0) / n,
        "avg_kickoff_distance_hours": 6.0,  # research proxy without wall-clock prediction time
        "kickoff_time_concentration": float(simultaneous / n),
        "simultaneous_kickoff_count": float(simultaneous),
        "evening_vs_daytime_ratio": float(evening_ratio),
        # prediction quality
        "avg_wde_confidence": _safe_mean(confs),
        "median_wde_confidence": _safe_median(confs),
        "min_wde_confidence": min(confs) if confs else 0.0,
        "max_wde_confidence": max(confs) if confs else 0.0,
        "confidence_dispersion": _safe_stdev(confs),
        "avg_ecse_entropy": _safe_mean(ents),
        "median_entropy": _safe_median(ents),
        "avg_top5_mass": _safe_mean(top5),
        "min_top5_mass": min(top5) if top5 else 0.0,
        "pct_no_bet": sum(1 for c in confs if c < 0.40) / n,
        "pct_consensus_high": sum(1 for c, t in zip(confs, top5) if c >= 0.65 and t >= 0.55) / n,
        "pct_full_super_consensus": sum(1 for c, t in zip(confs, top5) if c >= 0.75 and t >= 0.65) / n,
        "pct_model_conflict": sum(1 for e in ents if e >= 2.8) / n,
        "pct_canonical_exact_v2_agreement": sum(1 for c, t in zip(confs, top5) if abs(c - t) < 0.08) / n,
        "pct_high_goal_shift": sum(1 for e in ents if e >= 3.0) / n,
        "avg_residual_risk": _safe_mean(residuals),
        "avg_insurance_gain": _safe_mean(ins),
        "avg_primary_covered_mass": _safe_mean([max(0.0, c - i) for c, i in zip(cov, ins)]),
        "avg_final_covered_mass": _safe_mean(cov),
        # market
        "avg_favorite_odds": _safe_mean(odds, 2.0),
        "median_favorite_odds": _safe_median(odds, 2.0),
        "avg_draw_odds": _safe_mean(odds, 2.0) * 1.15,  # proxy when draw odds absent
        "pct_balanced_market": float(balanced),
        "pct_one_sided_market": float(one_sided),
        "favorite_strength_bucket": float(fav_bucket),
        "expected_total_bucket": 1.0 if _safe_mean(ents) < 2.2 else 2.0,
        "pct_btts_yes": sum(
            1 for r in rows if "btts" in str(r.get("insurance_market_label") or "").lower()
        )
        / n,
        "pct_over_direction": sum(
            1 for r in rows if "over" in str(r.get("main_market_label") or "").lower()
        )
        / n,
        "bookmaker_completeness": sum(1 for r in rows if r.get("odds_home")) / n,
        "real_market_completeness": sum(1 for r in rows if r.get("insurance_odds") or r.get("odds_home")) / n,
        "avg_market_families": float(len(set(families)) / max(1, len(rows))),
        "pct_manually_transcribed_odds": 0.0,
        "odds_freshness_score": 1.0,
        "odds_volatility_proxy": _safe_stdev(odds, 0.0),
        # coupon
        "total_main_tickets": float(max(1, n_sel_base)),
        "total_insurance_tickets": float(max(0, n_sel_base)),
        "avg_insurance_legs": 1.0,
        "market_family_entropy": float(fam_entropy),
        "exact_score_concentration": _safe_mean([len(r.get("exact3") or []) for r in rows], 3.0) / 10.0,
        "avg_combined_odds": _safe_mean(
            [float(r.get("insurance_odds") or r.get("odds_home") or 2.0) for r in rows], 2.0
        ),
        "coupon_diversification_score": float(1.0 - herfindahl),
        "coupon_overlap_score": float(herfindahl),
        "league_correlation_score": float(max_share),
        "market_correlation_score": float(1.0 / max(1, len(set(families)))),
        "capital_concentration_baseline": float(1.0 / max(1, n_sel_base)) if n_sel_base else 0.0,
        "capital_concentration_calibrated": float(1.0 / max(1, n_sel_cal)) if n_sel_cal else 0.0,
        # rolling historical (must be precomputed excluding current/future)
        "rolling_league_reliability": float(rolling.get("rolling_league_reliability", 0.55)),
        "rolling_market_family_reliability": float(rolling.get("rolling_market_family_reliability", 0.55)),
        "rolling_odds_bucket_reliability": float(rolling.get("rolling_odds_bucket_reliability", 0.55)),
        "rolling_dow_reliability": float(rolling.get("rolling_dow_reliability", 0.55)),
        "rolling_month_phase": float(rolling.get("rolling_month_phase", 0.5)),
        "rolling_model_calibration": float(rolling.get("rolling_model_calibration", 0.55)),
        "rolling_insurance_rescue_rate": float(rolling.get("rolling_insurance_rescue_rate", 0.25)),
        "rolling_complete_coupon_failure_rate": float(
            rolling.get("rolling_complete_coupon_failure_rate", 0.20)
        ),
    }

    # Hard guard: strip forbidden keys if any slipped in
    for bad in FORBIDDEN_LIVE_FEATURES:
        features.pop(bad, None)

    meta = {
        "day_id": f"day_{date}",
        "vienna_date": date,
        "cutoff_timestamp": cutoff_timestamp,
        "feature_content_hash": _hash_obj(features),
        "n_fixtures": len(rows),
        "research_only": True,
        "predictions_not_modified": True,
        "result_features_excluded": True,
    }
    return {"features": features, "meta": meta}


def expected_feature_names() -> list[str]:
    names: list[str] = []
    for group in FEATURE_GROUPS.values():
        names.extend(group)
    return names


def compute_day_labels(fixtures: list[dict[str, Any]], decision: dict[str, Any]) -> dict[str, Any]:
    """Evaluation-only labels from frozen tickets / outcomes — NEVER used as similarity inputs."""
    rows = [attach_outcomes(normalize_fixture(fx)) for fx in fixtures]
    by_id = {int(r["fixture_id"]): r for r in rows}
    selected = [by_id[i] for i in (decision.get("selected_fixture_ids") or []) if i in by_id]
    if not selected:
        # counterfactual-free zero day
        return {
            "realized_roi": None,
            "net_return": 0.0,
            "max_daily_loss": 0.0,
            "coupon_survival": 0.0,
            "complete_coupon_failure": 0.0,
            "insurance_rescue_count": 0,
            "drawdown_state": 0.0,
            "profitable_day": 0,
            "losing_day": 0,
            "exposure_units": 0.0,
            "label_hash": _hash_obj({"empty": True}),
            "evaluation_only": True,
        }
    pnl = 0.0
    wins = losses = rescues = 0
    for fx in selected:
        if fx.get("hit_insurance") is True:
            odd = float(fx.get("insurance_odds") or fx.get("odds_home") or 2.0)
            pnl += odd - 1.0
            wins += 1
            if fx.get("hit_main") is False:
                rescues += 1
        elif fx.get("hit_insurance") is False:
            pnl -= 1.0
            losses += 1
    staked = float(len(selected))
    roi = pnl / staked if staked else None
    return {
        "realized_roi": round(roi, 8) if roi is not None else None,
        "net_return": round(pnl, 6),
        "max_daily_loss": round(min(0.0, pnl), 6),
        "coupon_survival": round(wins / max(1, wins + losses), 8),
        "complete_coupon_failure": 1.0 if wins == 0 and losses > 0 else 0.0,
        "insurance_rescue_count": rescues,
        "drawdown_state": round(max(0.0, -pnl), 6),
        "profitable_day": 1 if pnl > 0 else 0,
        "losing_day": 1 if pnl < 0 else 0,
        "exposure_units": staked,
        "label_hash": _hash_obj({"pnl": pnl, "staked": staked, "wins": wins}),
        "evaluation_only": True,
    }


def rolling_stats_before_date(
    history_days: list[dict[str, Any]],
    *,
    target_date: str,
    lookback_days: int = 90,
) -> dict[str, float]:
    """Rolling aggregates strictly before target_date (no current/future leakage)."""
    prior = [d for d in history_days if str(d.get("vienna_date") or d.get("date") or "") < target_date]
    if lookback_days > 0 and len(prior) > lookback_days:
        prior = prior[-lookback_days:]
    if not prior:
        return {
            "rolling_league_reliability": 0.55,
            "rolling_market_family_reliability": 0.55,
            "rolling_odds_bucket_reliability": 0.55,
            "rolling_dow_reliability": 0.55,
            "rolling_month_phase": 0.5,
            "rolling_model_calibration": 0.55,
            "rolling_insurance_rescue_rate": 0.25,
            "rolling_complete_coupon_failure_rate": 0.20,
        }
    rois = [float(d["labels"]["realized_roi"]) for d in prior if d.get("labels", {}).get("realized_roi") is not None]
    rescues = [float(d["labels"].get("insurance_rescue_count") or 0) for d in prior]
    fails = [float(d["labels"].get("complete_coupon_failure") or 0) for d in prior]
    confs = [float((d.get("features") or {}).get("avg_wde_confidence") or 0.5) for d in prior]
    month = int(target_date[5:7]) if len(target_date) >= 7 else 6
    return {
        "rolling_league_reliability": _safe_mean(
            [1.0 if (d.get("labels") or {}).get("profitable_day") else 0.0 for d in prior], 0.55
        ),
        "rolling_market_family_reliability": _safe_mean(
            [float((d.get("labels") or {}).get("coupon_survival") or 0.5) for d in prior], 0.55
        ),
        "rolling_odds_bucket_reliability": _safe_mean(rois, 0.0) * 0.5 + 0.5 if rois else 0.55,
        "rolling_dow_reliability": _safe_mean(
            [1.0 if (d.get("labels") or {}).get("profitable_day") else 0.0 for d in prior], 0.55
        ),
        "rolling_month_phase": (month - 1) / 11.0,
        "rolling_model_calibration": _safe_mean(confs, 0.55),
        "rolling_insurance_rescue_rate": _safe_mean([min(1.0, r / 3.0) for r in rescues], 0.25),
        "rolling_complete_coupon_failure_rate": _safe_mean(fails, 0.20),
    }
