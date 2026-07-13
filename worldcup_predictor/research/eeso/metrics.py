"""EESO evaluation metrics — End Result, lifts, league breakdown, promotion gate."""

from __future__ import annotations

from collections import Counter
from typing import Any

from worldcup_predictor.research.ecse_rerank.features import winner_side
from worldcup_predictor.research.ecse_historical_replay.replay_engine import ReplayRow
from worldcup_predictor.research.eeso.constants import (
    NAMED_LEAGUE_SPECS,
    PROMOTION_END_RESULT_MAX_DEGRADATION_PP,
    PROMOTION_MIN_LEAGUE_FIXTURES,
    PROMOTION_MIN_PAIRED_FIXTURES,
    PROMOTION_TOP3_MAX_DEGRADATION_PP,
    PROMOTION_TOP5_LIFT_PP,
)


def hit_rate(hits: int, n: int) -> float:
    return round(100.0 * hits / n, 3) if n else 0.0


def actual_end_result(home_goals: int, away_goals: int) -> str:
    if home_goals > away_goals:
        return "home_win"
    if home_goals < away_goals:
        return "away_win"
    return "draw"


def end_result_from_scoreline(line: str) -> str | None:
    return winner_side(line)


def topn_contains_end_result(lines: list[str], actual_direction: str) -> bool:
    for line in lines:
        side = end_result_from_scoreline(line)
        if side == actual_direction:
            return True
    return False


def top1_end_result_hit(top1: str, actual_direction: str) -> bool:
    return end_result_from_scoreline(top1) == actual_direction


def implied_wde_direction(odds_home: float, odds_draw: float, odds_away: float) -> str:
    ph = 1.0 / max(odds_home, 1.01)
    pd = 1.0 / max(odds_draw, 1.01)
    pa = 1.0 / max(odds_away, 1.01)
    total = ph + pd + pa
    ph, pd, pa = ph / total, pd / total, pa / total
    if ph >= pd and ph >= pa:
        return "home_win"
    if pa >= pd and pa >= ph:
        return "away_win"
    return "draw"


# CSV league codes used in external_historical_csv_raw_rows (e.g. SE1, CL1).
LEAGUE_CODE_TO_NAMED: dict[str, str] = {
    "SE1": "allsvenskan",
    "SE2": "superettan",
    "NO1": "eliteserien",
    "IS1": "urvalsdeild",
    "IS2": "one_deild",
    "FI1": "veikkausliiga",
    "LV1": "virsliga",
    "LT1": "a_lyga",
    "CL1": "uefa",
    "EL1": "uefa",
    "EC1": "uefa",
    "UCL": "uefa",
    "UEL": "uefa",
    "UECL": "uefa",
}


def classify_named_league(row: ReplayRow) -> str | None:
    league = (row.league or "").strip().upper()
    if league in LEAGUE_CODE_TO_NAMED:
        return LEAGUE_CODE_TO_NAMED[league]
    if league.startswith("WR"):
        return "world_cup"

    hay = f"{row.league} {row.competition} {row.stage}".lower()
    for key, (_, patterns) in NAMED_LEAGUE_SPECS.items():
        if any(p in hay for p in patterns):
            return key
    if row.competition == "World Cup":
        return "world_cup"
    if row.competition in ("Champions League", "Europa League", "Conference League"):
        return "uefa"
    return None


def bucket_entropy(entropy: float) -> str:
    if entropy < 1.5:
        return "low_entropy"
    if entropy < 2.0:
        return "mid_entropy"
    return "high_entropy"


def bucket_mass(mass: float, *, kind: str = "top5") -> str:
    if kind == "top3":
        if mass < 0.25:
            return "top3_mass_low"
        if mass < 0.45:
            return "top3_mass_mid"
        return "top3_mass_high"
    if mass < 0.35:
        return "top5_mass_low"
    if mass < 0.55:
        return "top5_mass_mid"
    return "top5_mass_high"


def bucket_data_quality(score: float) -> str:
    if score < 0.4:
        return "dq_low"
    if score < 0.7:
        return "dq_mid"
    return "dq_high"


def compute_lift_pp(method_rate: float, baseline_rate: float) -> float:
    return round(method_rate - baseline_rate, 3)


def compute_relative_lift(method_rate: float, baseline_rate: float) -> float | None:
    if baseline_rate <= 0:
        return None
    return round(100.0 * (method_rate - baseline_rate) / baseline_rate, 3)


def paired_comparison(
    *,
    baseline_hits: list[bool],
    method_hits: list[bool],
) -> dict[str, int]:
    wins = losses = ties = 0
    for b, m in zip(baseline_hits, method_hits):
        if m and not b:
            wins += 1
        elif b and not m:
            losses += 1
        else:
            ties += 1
    return {"paired_wins": wins, "paired_losses": losses, "paired_ties": ties}


def league_breakdown_entry(
    *,
    league_key: str,
    n: int,
    canonical_top1: float,
    canonical_top3: float,
    canonical_top5: float,
    best_eeso_top3: float,
    best_eeso_top5: float,
    best_eeso_top3_method: str,
    best_eeso_top5_method: str,
    end_result_canonical_top5: float,
    end_result_best_eeso: float,
) -> dict[str, Any]:
    net_lift_top5 = round(best_eeso_top5 - canonical_top5, 3)
    net_lift_top3 = round(best_eeso_top3 - canonical_top3, 3)
    label = NAMED_LEAGUE_SPECS.get(league_key, (league_key, ()))[0]
    insufficient = n < PROMOTION_MIN_LEAGUE_FIXTURES
    eligible = (
        not insufficient
        and net_lift_top5 >= PROMOTION_TOP5_LIFT_PP
        and net_lift_top3 >= -PROMOTION_TOP3_MAX_DEGRADATION_PP
        and (end_result_best_eeso - end_result_canonical_top5) >= -PROMOTION_END_RESULT_MAX_DEGRADATION_PP
    )
    return {
        "league_key": league_key,
        "label": label,
        "paired_fixture_count": n,
        "canonical_top1_pct": canonical_top1,
        "canonical_top3_pct": canonical_top3,
        "canonical_top5_pct": canonical_top5,
        "best_eeso_top3_pct": best_eeso_top3,
        "best_eeso_top5_pct": best_eeso_top5,
        "best_eeso_top3_method": best_eeso_top3_method,
        "best_eeso_top5_method": best_eeso_top5_method,
        "net_lift_top5_pp": net_lift_top5,
        "net_lift_top3_pp": net_lift_top3,
        "end_result_canonical_top5_pct": end_result_canonical_top5,
        "end_result_best_eeso_pct": end_result_best_eeso,
        "sample_warning": "INSUFFICIENT_LEAGUE_SAMPLE" if insufficient else None,
        "promotion_eligible": eligible,
    }


def evaluate_promotion_gate(
    *,
    paired_fixtures: int,
    top5_lift_pp: float,
    top3_delta_pp: float,
    end_result_delta_pp: float,
    leagues_improved: int,
    validation_passed: bool,
) -> dict[str, Any]:
    checks = {
        "min_paired_fixtures": paired_fixtures >= PROMOTION_MIN_PAIRED_FIXTURES,
        "no_leakage_assumed": True,
        "top5_lift_ge_3pp": top5_lift_pp >= PROMOTION_TOP5_LIFT_PP,
        "top3_not_degraded": top3_delta_pp >= -PROMOTION_TOP3_MAX_DEGRADATION_PP,
        "end_result_not_degraded": end_result_delta_pp >= -PROMOTION_END_RESULT_MAX_DEGRADATION_PP,
        "multiple_leagues_improve": leagues_improved >= 2,
        "validator_passed": validation_passed,
        "no_automatic_promotion": True,
    }
    recommend = all(
        [
            checks["min_paired_fixtures"],
            checks["top5_lift_ge_3pp"],
            checks["top3_not_degraded"],
            checks["end_result_not_degraded"],
            checks["multiple_leagues_improve"],
            checks["validator_passed"],
        ]
    )
    return {
        "checks": checks,
        "recommend_production_promotion": recommend,
        "min_paired_fixtures": PROMOTION_MIN_PAIRED_FIXTURES,
        "required_top5_lift_pp": PROMOTION_TOP5_LIFT_PP,
    }


def determine_final_status(
    *,
    paired_fixtures: int,
    best_top5_lift_pp: float,
    validation_passed: bool,
    promotion_recommended: bool,
) -> str:
    if not validation_passed:
        return "EESO_VALIDATION_FAILED"
    if paired_fixtures < PROMOTION_MIN_PAIRED_FIXTURES:
        return "EESO_MORE_DATA_REQUIRED"
    if promotion_recommended and best_top5_lift_pp >= PROMOTION_TOP5_LIFT_PP:
        return "EESO_SHADOW_IMPROVES_TOP5"
    return "EESO_NO_PROVEN_ADVANTAGE"


def summarize_method_rates(hits: Counter[str], n: int) -> dict[str, float]:
    return {k: hit_rate(int(v), n) for k, v in sorted(hits.items())}
