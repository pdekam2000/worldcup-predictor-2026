"""Prematch ESDI and Fragility metrics for canonical Top5 (S4 unchanged)."""

from __future__ import annotations

import math
from collections import defaultdict
from typing import Any

from worldcup_predictor.forward_evaluation.context import scoreline_side

SELECTOR_VERSION = "S4"
PROB_FLOOR = 1e-12


def _prob01(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        p = float(value)
    except (TypeError, ValueError):
        return 0.0
    return p / 100.0 if p > 1.0 else p


def score_features(score: str) -> dict[str, Any]:
    if "-" not in score or score.upper() == "OTHER":
        raise ValueError(f"invalid scoreline: {score}")
    hg, ag = map(int, score.split("-", 1))
    direction = "draw"
    if hg > ag:
        direction = "home_win"
    elif hg < ag:
        direction = "away_win"
    btts = "yes" if hg > 0 and ag > 0 else "no"
    total = hg + ag
    if total <= 1:
        total_bucket = "0_1"
    elif total == 2:
        total_bucket = "2"
    elif total == 3:
        total_bucket = "3"
    else:
        total_bucket = "4_plus"
    margin = abs(hg - ag)
    if margin == 0:
        margin_bucket = "draw"
    elif margin == 1:
        margin_bucket = "one"
    elif margin == 2:
        margin_bucket = "two"
    else:
        margin_bucket = "three_plus"
    clean_sheet = hg == 0 or ag == 0
    scenario = f"{direction}|btts_{btts}|{margin_bucket}|{'cs' if clean_sheet else 'nocs'}"
    return {
        "direction": direction,
        "btts": btts,
        "total_goals": total,
        "total_bucket": total_bucket,
        "goal_diff": margin,
        "margin_bucket": margin_bucket,
        "clean_sheet": clean_sheet,
        "scenario": scenario,
    }


def ranks_to_rows(ranks: list[dict[str, Any]], *, limit: int = 5) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in sorted(ranks, key=lambda r: int(r.get("rank") or 99))[:limit]:
        score = str(raw.get("score") or raw.get("scoreline") or "")
        if not score or score.upper() == "OTHER":
            continue
        rows.append(
            {
                "scoreline": score,
                "rank": int(raw.get("rank") or len(rows) + 1),
                "probability": _prob01(raw.get("probability")),
                "features": score_features(score),
            }
        )
    return rows


def esdi_metrics(rows: list[dict[str, Any]], canonical_mass: float | None = None) -> dict[str, Any]:
    if not rows:
        return {
            "esdi_score": 0.0,
            "fragility_score": 100.0,
            "clean_sheet_concentration": 1.0,
            "direction_concentration": 1.0,
            "btts_concentration": 1.0,
            "goal_regime_concentration": 1.0,
            "scenario_concentration": 1.0,
            "probability_retention": 0.0,
            "set_mass": 0.0,
            "direction_coverage": [],
            "btts_coverage": [],
            "goal_regime_coverage": [],
            "margin_coverage": [],
            "scenario_types": 0,
        }
    if canonical_mass is None:
        canonical_mass = sum(float(r["probability"]) for r in rows)
    total_mass = sum(float(r["probability"]) for r in rows)
    dir_mass: dict[str, float] = defaultdict(float)
    btts_mass: dict[str, float] = defaultdict(float)
    total_mass_bucket: dict[str, float] = defaultdict(float)
    margin_mass: dict[str, float] = defaultdict(float)
    scenario_mass: dict[str, float] = defaultdict(float)
    clean_sheet_mass = 0.0
    for r in rows:
        p = float(r["probability"])
        f = r["features"]
        dir_mass[f["direction"]] += p
        btts_mass[f["btts"]] += p
        total_mass_bucket[f["total_bucket"]] += p
        margin_mass[f["margin_bucket"]] += p
        scenario_mass[f["scenario"]] += p
        if f["clean_sheet"]:
            clean_sheet_mass += p

    def balanced_score(mapping: dict[str, float], expected: list[str]) -> float:
        vals = [float(mapping.get(k, 0.0)) for k in expected]
        active = sum(1 for v in vals if v >= 0.03)
        if sum(vals) <= 0:
            return 0.0
        shares = [v / max(sum(vals), PROB_FLOOR) for v in vals if v > 0]
        entropy = (
            -sum(v * math.log(v) for v in shares) / math.log(len(expected))
            if len(expected) > 1 and shares
            else 0.0
        )
        return min(1.0, 0.55 * entropy + 0.45 * (active / len(expected)))

    direction_div = balanced_score(dir_mass, ["home_win", "draw", "away_win"])
    btts_div = balanced_score(btts_mass, ["yes", "no"])
    goal_div = balanced_score(total_mass_bucket, ["0_1", "2", "3", "4_plus"])
    margin_div = balanced_score(margin_mass, ["draw", "one", "two", "three_plus"])
    clean_sheet_conc = clean_sheet_mass / max(total_mass, PROB_FLOOR)
    direction_conc = max(dir_mass.values()) / max(total_mass, PROB_FLOOR) if dir_mass else 1.0
    btts_conc = max(btts_mass.values()) / max(total_mass, PROB_FLOOR) if btts_mass else 1.0
    goal_conc = max(total_mass_bucket.values()) / max(total_mass, PROB_FLOOR) if total_mass_bucket else 1.0
    scenario_conc = max(scenario_mass.values()) / max(total_mass, PROB_FLOOR) if scenario_mass else 1.0
    retention = total_mass / max(canonical_mass or total_mass, PROB_FLOOR)
    fragility = min(
        100.0,
        max(
            0.0,
            100.0
            * (
                0.35 * clean_sheet_conc
                + 0.25 * scenario_conc
                + 0.2 * direction_conc
                + 0.1 * btts_conc
                + 0.1 * goal_conc
            ),
        ),
    )
    esdi = max(
        0.0,
        min(
            100.0,
            100.0
            * (
                0.24 * direction_div
                + 0.18 * btts_div
                + 0.22 * goal_div
                + 0.18 * margin_div
                + 0.18 * max(0.0, min(1.0, retention))
            ),
        ),
    )
    return {
        "esdi_score": round(esdi, 3),
        "fragility_score": round(fragility, 3),
        "clean_sheet_concentration": round(clean_sheet_conc, 6),
        "direction_concentration": round(direction_conc, 6),
        "btts_concentration": round(btts_conc, 6),
        "goal_regime_concentration": round(goal_conc, 6),
        "scenario_concentration": round(scenario_conc, 6),
        "probability_retention": round(retention, 6),
        "set_mass": round(total_mass, 6),
        "direction_coverage": sorted(k for k, v in dir_mass.items() if v >= 0.03),
        "btts_coverage": sorted(k for k, v in btts_mass.items() if v >= 0.03),
        "goal_regime_coverage": sorted(k for k, v in total_mass_bucket.items() if v >= 0.03),
        "margin_coverage": sorted(k for k, v in margin_mass.items() if v >= 0.03),
        "scenario_types": len([1 for v in scenario_mass.values() if v >= 0.03]),
    }


def high_score_tail_mass(top_scorelines: list[dict[str, Any]]) -> float:
    total = 0.0
    for row in top_scorelines:
        score = str(row.get("scoreline") or row.get("score") or "")
        if "-" not in score:
            continue
        try:
            hg, ag = map(int, score.split("-", 1))
        except ValueError:
            continue
        if hg + ag >= 4:
            total += _prob01(row.get("probability"))
    return round(total, 6)


def draw_underrank_risk(draw_probability: float | None, top5_rows: list[dict[str, Any]]) -> float:
    draw_p = _prob01(draw_probability)
    draw_in_top5 = sum(1 for r in top5_rows if r["features"]["direction"] == "draw")
    if draw_p >= 0.28 and draw_in_top5 == 0:
        return 1.0
    if draw_p >= 0.25 and draw_in_top5 <= 1:
        return 0.5
    return 0.0


def risk_labels(
    metrics: dict[str, Any],
    *,
    top5_rows: list[dict[str, Any]],
    draw_probability: float | None,
    high_score_tail: float,
    wde_decision: str | None,
    ecse_top1_side: str | None,
    domain_type: str | None,
    competition_family: str | None,
) -> list[str]:
    labels: list[str] = []
    if metrics["clean_sheet_concentration"] >= 0.95:
        labels.append("ALL_CLEAN_SHEET_TOP5")
    if metrics["direction_concentration"] >= 0.98:
        labels.append("SINGLE_DIRECTION_TOP5")
    if high_score_tail >= 0.25:
        labels.append("HIGH_SCORE_TAIL_EXPOSED")
    if draw_underrank_risk(draw_probability, top5_rows) >= 0.5:
        labels.append("DRAW_NOT_REPRESENTED")
    btts_in_top5 = {r["features"]["btts"] for r in top5_rows}
    if "yes" not in btts_in_top5:
        labels.append("BTTS_YES_NOT_REPRESENTED")
    if "no" not in btts_in_top5:
        labels.append("BTTS_NO_NOT_REPRESENTED")
    domain = str(domain_type or competition_family or "").lower()
    if "uefa" in domain or "qualifier" in domain:
        labels.append("DOMAIN_RISK_ELEVATED")
    if wde_decision and ecse_top1_side and wde_decision != ecse_top1_side:
        labels.append("WDE_ECSE_DIRECTION_MISMATCH")
    return labels


def build_prematch_risk_record(
    *,
    prediction_id: str,
    fixture_id: int,
    ranks: list[dict[str, Any]],
    frozen: dict[str, Any],
    top10_scorelines: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    top5_rows = ranks_to_rows(ranks, limit=5)
    canonical_mass = sum(float(r["probability"]) for r in top5_rows)
    metrics = esdi_metrics(top5_rows, canonical_mass)
    top10 = top10_scorelines or ranks_to_rows(ranks, limit=10)
    tail = high_score_tail_mass(top10)
    top1_side = scoreline_side(top5_rows[0]["scoreline"]) if top5_rows else None
    labels = risk_labels(
        metrics,
        top5_rows=top5_rows,
        draw_probability=frozen.get("draw_probability"),
        high_score_tail=tail,
        wde_decision=frozen.get("wde_decision"),
        ecse_top1_side=top1_side,
        domain_type=frozen.get("domain_type"),
        competition_family=frozen.get("competition_family"),
    )
    wde_ecse_agree = bool(
        frozen.get("wde_decision")
        and top1_side
        and str(frozen.get("wde_decision")) == str(top1_side)
    )
    return {
        "prediction_id": prediction_id,
        "fixture_id": int(fixture_id),
        "source_freeze_hash": frozen.get("content_hash") or frozen.get("payload_hash"),
        "selector_version": SELECTOR_VERSION,
        "canonical_top5": [
            {
                "score": r["scoreline"],
                "probability": r["probability"],
                "rank": r["rank"],
                **r["features"],
            }
            for r in top5_rows
        ],
        "top3_mass": frozen.get("top3_mass"),
        "top5_mass": frozen.get("top5_mass"),
        "entropy": frozen.get("entropy"),
        "lambda_home": frozen.get("lambda_home"),
        "lambda_away": frozen.get("lambda_away"),
        "total_lambda": frozen.get("total_lambda"),
        "esdi_score": metrics["esdi_score"],
        "fragility_score": metrics["fragility_score"],
        "clean_sheet_concentration": metrics["clean_sheet_concentration"],
        "direction_concentration": metrics["direction_concentration"],
        "btts_coverage": metrics["btts_coverage"],
        "goal_regime_coverage": metrics["goal_regime_coverage"],
        "margin_coverage": metrics["margin_coverage"],
        "high_score_tail_warning": tail >= 0.25,
        "high_score_tail_mass": tail,
        "draw_underrank_warning": draw_underrank_risk(frozen.get("draw_probability"), top5_rows) >= 0.5,
        "draw_underrank_risk": draw_underrank_risk(frozen.get("draw_probability"), top5_rows),
        "risk_labels": labels,
        "league_domain_risk": "DOMAIN_RISK_ELEVATED" in labels,
        "data_quality": frozen.get("data_quality"),
        "odds_freshness": frozen.get("odds_freshness") or frozen.get("odds_freshness_status"),
        "competition": frozen.get("competition"),
        "competition_family": frozen.get("competition_family"),
        "domain_type": frozen.get("domain_type"),
        "tier": frozen.get("tier") or frozen.get("validation_tier"),
        "wde_decision": frozen.get("wde_decision"),
        "wde_ecse_agree": wde_ecse_agree,
        "kickoff": frozen.get("kickoff"),
        "frozen_at": frozen.get("frozen_at"),
        "generated_at": frozen.get("generated_at"),
        "metrics": metrics,
    }
