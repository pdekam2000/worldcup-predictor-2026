"""Transparent forensic scoring and classification."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.forward_evaluation.context import scoreline_side
from worldcup_predictor.research.ecse_esdi_fragility.metrics import esdi_metrics, ranks_to_rows
from worldcup_predictor.research.team_form_h2h_forensic.constants import (
    AGREEMENT_LEVELS,
    CLASSIFICATIONS,
    COMPLETENESS_LEVELS,
    RULE_VERSION,
    UNDERDOG_RISK_LEVELS,
)


def _rate(profile: dict[str, Any], section: str, field: str) -> float | None:
    block = profile.get(section) or {}
    val = block.get(field)
    if val is None:
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _count_rate(profile: dict[str, Any], section: str, count_field: str) -> float | None:
    n = _profile_n(profile)
    if n <= 0:
        return None
    count = _rate(profile, section, count_field)
    if count is None:
        return None
    return round(count / n, 4)


def _profile_n(profile: dict[str, Any]) -> int:
    return int((profile.get("identity") or {}).get("matches_found") or 0)


def analyze_top5(frozen: dict[str, Any] | None) -> dict[str, Any]:
    if not frozen:
        return {"available": False}
    ranks = frozen.get("rank_rows") or []
    rows = ranks_to_rows(ranks, limit=5)
    if len(rows) < 5:
        return {"available": False, "reason": "incomplete_top5"}
    mass = sum(float(r["probability"]) for r in rows)
    metrics = esdi_metrics(rows, mass)
    directions = {r["features"]["direction"] for r in rows}
    btts = {r["features"]["btts"] for r in rows}
    margins = {r["features"]["margin_bucket"] for r in rows}
    home_goals = [r["features"]["total_goals"] for r in rows if r["features"]["direction"] == "home_win"]
    away_goals = [r["features"]["total_goals"] for r in rows if r["features"]["direction"] == "away_win"]
    return {
        "available": True,
        "top5": [{"score": r["scoreline"], "probability": r["probability"], "rank": r["rank"]} for r in rows],
        "metrics": metrics,
        "directions": sorted(directions),
        "btts_modes": sorted(btts),
        "margin_modes": sorted(margins),
        "all_clean_sheet": metrics["clean_sheet_concentration"] >= 0.95,
        "single_direction": metrics["direction_concentration"] >= 0.98,
        "draw_in_top5": "draw" in directions,
        "btts_yes_in_top5": "yes" in btts,
        "top1": rows[0]["scoreline"] if rows else None,
        "top1_side": scoreline_side(rows[0]["scoreline"]) if rows else None,
    }


def underdog_scoring_risk(
    evidence: dict[str, Any],
    *,
    favourite_side: str | None,
) -> dict[str, Any]:
    home_p = evidence.get("home_profile") or {}
    away_p = evidence.get("away_profile") or {}
    if favourite_side == "home_win":
        fav_profile, dog_profile = home_p, away_p
        dog_venue = evidence.get("away_venue_form") or {}
    elif favourite_side == "away_win":
        fav_profile, dog_profile = away_p, home_p
        dog_venue = evidence.get("home_venue_form") or {}
    else:
        return {"level": "UNDERDOG_GOAL_RISK_MEDIUM", "reason": "no_clear_favourite", "signals": []}

    dog_scored = _count_rate(dog_profile, "goal_output", "scored_in_match_count")
    fav_conceded = _count_rate(fav_profile, "defensive_output", "conceded_in_match_count")
    dog_btts = _count_rate(dog_profile, "market_shape", "BTTS_yes_count")
    fav_cs = _count_rate(fav_profile, "defensive_output", "clean_sheets_count")
    venue_scored = dog_venue.get("scored_in_rate")

    signals = []
    score = 0.0
    if dog_scored is not None:
        if dog_scored >= 0.7:
            score += 0.35
            signals.append(f"underdog_scored_rate={dog_scored:.2f}")
        elif dog_scored >= 0.5:
            score += 0.2
    if fav_conceded is not None:
        if fav_conceded >= 0.6:
            score += 0.3
            signals.append(f"favourite_conceded_rate={fav_conceded:.2f}")
        elif fav_conceded >= 0.4:
            score += 0.15
    if dog_btts is not None and dog_btts >= 0.55:
        score += 0.15
        signals.append(f"underdog_btts_rate={dog_btts:.2f}")
    if fav_cs is not None and fav_cs <= 0.35:
        score += 0.15
        signals.append(f"favourite_clean_sheet_rate={fav_cs:.2f}")
    if venue_scored is not None and venue_scored >= 0.6:
        score += 0.1

    if score >= 0.55:
        level = "UNDERDOG_GOAL_RISK_HIGH"
    elif score >= 0.3:
        level = "UNDERDOG_GOAL_RISK_MEDIUM"
    else:
        level = "UNDERDOG_GOAL_RISK_LOW"
    return {
        "level": level,
        "score": round(score, 4),
        "signals": signals,
        "dog_scored_rate": dog_scored,
        "favourite_conceded_rate": fav_conceded,
        "dog_btts_rate": dog_btts,
        "favourite_clean_sheet_rate": fav_cs,
        "dog_venue_scored_rate": venue_scored,
    }


def data_completeness(evidence: dict[str, Any]) -> dict[str, Any]:
    matrix = []
    frozen = evidence.get("frozen_prediction") or {}
    has_top5 = len(frozen.get("rank_rows") or []) >= 5
    categories = {
        "recent_form": _profile_n(evidence.get("home_profile") or {}) >= 3 and _profile_n(evidence.get("away_profile") or {}) >= 3,
        "venue_form": (evidence.get("home_venue_form") or {}).get("matches_found", 0) >= 2,
        "h2h": len(evidence.get("h2h_meetings") or []) > 0,
        "xg_xga": "xg" in ((evidence.get("prematch_snapshots") or {}).get("families") or {}),
        "lineup": "lineup" in ((evidence.get("prematch_snapshots") or {}).get("families") or {}),
        "injuries": "injury" in ((evidence.get("prematch_snapshots") or {}).get("families") or {}),
        "odds": bool((evidence.get("odds") or {}).get("home")),
        "frozen_prediction": bool(frozen) and has_top5,
    }
    available = sum(1 for v in categories.values() if v)
    total = len(categories)
    ratio = available / max(total, 1)
    if ratio >= 0.75 and categories["recent_form"] and categories["frozen_prediction"]:
        level = "HIGH"
    elif categories["frozen_prediction"] and (categories["recent_form"] or categories["odds"]):
        level = "MEDIUM"
    elif categories["frozen_prediction"]:
        level = "LOW"
    elif ratio >= 0.35:
        level = "LOW"
    else:
        level = "INSUFFICIENT"
    for cat, ok in categories.items():
        matrix.append({"category": cat, "available": ok})
    return {"level": level, "score": round(ratio, 4), "matrix": matrix}


def agreement_matrix(evidence: dict[str, Any], top5: dict[str, Any]) -> dict[str, Any]:
    frozen = evidence.get("frozen_prediction") or {}
    rows: list[dict[str, Any]] = []
    wde = frozen.get("wde_decision")
    top1_side = top5.get("top1_side")
    rows.append(
        {
            "evidence": "WDE",
            "supports": wde == top1_side,
            "conflicts": bool(wde and top1_side and wde != top1_side),
            "reliability": "high" if frozen.get("wde_decision") else "low",
        }
    )
    rows.append(
        {
            "evidence": "ECSE",
            "supports": bool(top5.get("available")),
            "conflicts": False,
            "reliability": "high" if top5.get("available") else "low",
        }
    )
    btts_pred = str(frozen.get("btts_prediction") or "").lower()
    rows.append(
        {
            "evidence": "BTTS",
            "supports": bool(btts_pred),
            "conflicts": top5.get("all_clean_sheet") and btts_pred in ("yes", "btts_yes"),
            "reliability": "medium",
        }
    )
    home_n = _profile_n(evidence.get("home_profile") or {})
    away_n = _profile_n(evidence.get("away_profile") or {})
    rows.append(
        {
            "evidence": "Recent form",
            "supports": home_n >= 5 and away_n >= 5,
            "conflicts": home_n < 3 or away_n < 3,
            "reliability": "high" if min(home_n, away_n) >= 5 else "medium",
        }
    )
    rows.append(
        {
            "evidence": "H2H",
            "supports": len(evidence.get("h2h_meetings") or []) >= 2,
            "conflicts": False,
            "reliability": str(evidence.get("h2h_relevance") or "low"),
        }
    )
    supports = sum(1 for r in rows if r["supports"])
    conflicts = sum(1 for r in rows if r["conflicts"])
    if home_n < 3 and away_n < 3:
        level = "INSUFFICIENT_DATA"
    elif conflicts >= 2:
        level = "HIGH_CONFLICT"
    elif conflicts == 1:
        level = "MIXED"
    elif supports >= 4:
        level = "HIGH_AGREEMENT"
    else:
        level = "MODERATE_AGREEMENT"
    return {"level": level, "rows": rows, "support_count": supports, "conflict_count": conflicts}


def score_forensic(
    evidence: dict[str, Any],
    *,
    top5: dict[str, Any],
    underdog: dict[str, Any],
    completeness: dict[str, Any],
    agreement: dict[str, Any],
) -> dict[str, Any]:
    support = 0.0
    contradiction = 0.0
    breakdown: dict[str, float] = {}

    if agreement["level"] == "HIGH_AGREEMENT":
        support += 0.2
        breakdown["agreement"] = 0.2
    elif agreement["level"] == "HIGH_CONFLICT":
        contradiction += 0.25
        breakdown["agreement_conflict"] = 0.25

    if top5.get("all_clean_sheet"):
        if underdog["level"] == "UNDERDOG_GOAL_RISK_HIGH":
            contradiction += 0.35
            breakdown["clean_sheet_vs_underdog"] = 0.35
        elif underdog["level"] == "UNDERDOG_GOAL_RISK_MEDIUM":
            contradiction += 0.2
            breakdown["clean_sheet_vs_underdog"] = 0.2
        else:
            support += 0.1
            breakdown["clean_sheet_supported"] = 0.1

    home_n = _profile_n(evidence.get("home_profile") or {})
    away_n = _profile_n(evidence.get("away_profile") or {})
    if home_n >= 5 and away_n >= 5:
        support += 0.15
        breakdown["recent_form_depth"] = 0.15
    elif home_n < 3 or away_n < 3:
        contradiction += 0.15
        breakdown["thin_form_sample"] = 0.15

    if top5.get("available"):
        frag = float((top5.get("metrics") or {}).get("fragility_score") or 0)
        if frag >= 75:
            contradiction += 0.15
            breakdown["high_fragility"] = 0.15
        elif frag <= 45:
            support += 0.1
            breakdown["low_fragility"] = 0.1

    wde = (evidence.get("frozen_prediction") or {}).get("wde_decision")
    if wde and top5.get("top1_side") and wde == top5.get("top1_side"):
        support += 0.15
        breakdown["wde_ecse_direction"] = 0.15
    elif wde and top5.get("top1_side"):
        contradiction += 0.2
        breakdown["wde_ecse_mismatch"] = 0.2

    if completeness["level"] in ("LOW", "INSUFFICIENT"):
        contradiction += 0.1
        breakdown["low_completeness"] = 0.1

    support = min(1.0, support)
    contradiction = min(1.0, contradiction)
    forensic_score = round(max(0.0, support - contradiction) * 100.0, 2)
    return {
        "support_score": round(support, 4),
        "contradiction_score": round(contradiction, 4),
        "data_completeness_score": completeness["score"],
        "final_forensic_score": forensic_score,
        "breakdown": breakdown,
        "rule_version": RULE_VERSION,
    }


def classify_forensic(
    scores: dict[str, Any],
    *,
    top5: dict[str, Any],
    underdog: dict[str, Any],
    completeness: dict[str, Any],
    agreement: dict[str, Any],
) -> str:
    if not top5.get("available"):
        return "INSUFFICIENT_FORENSIC_DATA"
    if completeness["level"] == "INSUFFICIENT":
        return "INSUFFICIENT_FORENSIC_DATA"
    if completeness["level"] == "LOW":
        if scores["contradiction_score"] >= 0.55:
            return "TOP5_FRAGILE"
        return "TOP5_SUPPORTED_WITH_RISK"

    if scores["contradiction_score"] >= 0.6 and top5.get("all_clean_sheet"):
        return "HEDGE_RECOMMENDED"
    if scores["contradiction_score"] >= 0.5 or underdog["level"] == "UNDERDOG_GOAL_RISK_HIGH":
        if top5.get("all_clean_sheet"):
            return "TOP5_FRAGILE"
        return "TOP5_SUPPORTED_WITH_RISK"
    if scores["support_score"] >= 0.65 and scores["contradiction_score"] < 0.25 and completeness["level"] == "HIGH":
        return "TOP5_STRONGLY_SUPPORTED"
    if scores["support_score"] >= 0.45:
        return "TOP5_SUPPORTED_WITH_RISK"
    if agreement["level"] == "HIGH_CONFLICT":
        return "DIRECTION_ONLY_RECOMMENDED"
    if scores["contradiction_score"] >= 0.7:
        return "NO_BET"
    return "TOP5_SUPPORTED_WITH_RISK"


def build_forensic_result(evidence: dict[str, Any]) -> dict[str, Any]:
    frozen = evidence.get("frozen_prediction") or {}
    top5 = analyze_top5(frozen)
    favourite = frozen.get("wde_decision") or frozen.get("ft_marginal_direction")
    underdog = underdog_scoring_risk(evidence, favourite_side=favourite)
    completeness = data_completeness(evidence)
    agreement = agreement_matrix(evidence, top5)
    scores = score_forensic(
        evidence,
        top5=top5,
        underdog=underdog,
        completeness=completeness,
        agreement=agreement,
    )
    classification = classify_forensic(
        scores,
        top5=top5,
        underdog=underdog,
        completeness=completeness,
        agreement=agreement,
    )

    supporting = []
    conflicting = []
    if scores["breakdown"].get("wde_ecse_direction"):
        supporting.append("WDE direction aligns with ECSE Top1")
    if scores["breakdown"].get("clean_sheet_vs_underdog"):
        conflicting.append("All-clean-sheet Top5 conflicts with underdog scoring evidence")
    if underdog.get("signals"):
        conflicting.append("; ".join(underdog["signals"][:2]))
    if not supporting:
        supporting.append("Recent competitive form available for both teams")
    if not conflicting:
        conflicting.append("No major forensic conflict detected")

    return {
        "fixture_id": evidence.get("fixture_id"),
        "match": f"{evidence.get('home_team')} vs {evidence.get('away_team')}",
        "kickoff_utc": evidence.get("kickoff_utc"),
        "classification": classification,
        "support_score": scores["support_score"],
        "contradiction_score": scores["contradiction_score"],
        "data_completeness": completeness["level"],
        "agreement_level": agreement["level"],
        "strongest_supporting_evidence": supporting[0],
        "strongest_conflicting_evidence": conflicting[0],
        "underdog_scoring_risk": underdog["level"],
        "home_team_scoring_risk": _count_rate(evidence.get("home_profile") or {}, "goal_output", "scored_in_match_count"),
        "away_team_scoring_risk": _count_rate(evidence.get("away_profile") or {}, "goal_output", "scored_in_match_count"),
        "high_score_tail_risk": top5.get("metrics", {}).get("goal_regime_concentration"),
        "draw_risk": 1.0 if not top5.get("draw_in_top5") else 0.0,
        "clean_sheet_fragility": top5.get("metrics", {}).get("clean_sheet_concentration"),
        "recommendation_reason": _reason(classification, top5, underdog, completeness),
        "canonical_prediction": _canonical_summary(frozen, top5),
        "recent_form": {
            "home_last8": evidence.get("home_profile"),
            "away_last8": evidence.get("away_profile"),
            "home_venue": evidence.get("home_venue_form"),
            "away_venue": evidence.get("away_venue_form"),
        },
        "h2h": {
            "meetings": evidence.get("h2h_meetings"),
            "summary": evidence.get("h2h_detail"),
            "relevance": evidence.get("h2h_relevance"),
        },
        "agreement_matrix": agreement,
        "completeness_matrix": completeness,
        "forensic_scores": scores,
        "top5_analysis": top5,
        "underdog_analysis": underdog,
        "provenance": evidence.get("provenance"),
        "providers_used": sorted({p.get("source") for p in evidence.get("provenance") or [] if p.get("source")}),
        "public_visible": False,
        "rule_version": RULE_VERSION,
    }


def _canonical_summary(frozen: dict[str, Any], top5: dict[str, Any]) -> dict[str, Any]:
    return {
        "wde_decision": frozen.get("wde_decision"),
        "home_probability": frozen.get("home_probability"),
        "draw_probability": frozen.get("draw_probability"),
        "away_probability": frozen.get("away_probability"),
        "btts_prediction": frozen.get("btts_prediction"),
        "ou25_prediction": frozen.get("ou25_prediction"),
        "top5": top5.get("top5") or [],
        "top5_mass": frozen.get("top5_mass"),
        "entropy": frozen.get("entropy"),
    }


def _reason(classification: str, top5: dict[str, Any], underdog: dict[str, Any], completeness: dict[str, Any]) -> str:
    if classification == "INSUFFICIENT_FORENSIC_DATA":
        return "Core prematch forensic evidence incomplete; cannot strongly validate frozen Top5."
    if classification == "HEDGE_RECOMMENDED":
        return "Frozen Top5 is highly concentrated while underdog scoring and concession evidence conflicts with clean-sheet scripts."
    if classification == "TOP5_FRAGILE":
        return "Canonical Top5 remains unchanged but forensic evidence shows scenario concentration risk."
    if classification == "TOP5_STRONGLY_SUPPORTED":
        return "Recent form, direction agreement, and Top5 structure align with limited contradiction."
    if classification == "DIRECTION_ONLY_RECOMMENDED":
        return "Directional evidence is usable but exact-score concentration is not well supported."
    if classification == "NO_BET":
        return "Forensic contradiction and data gaps exceed owner comfort threshold for exact-score reliance."
    return f"Supported with caveats; data completeness={completeness['level']}, underdog risk={underdog['level']}."
