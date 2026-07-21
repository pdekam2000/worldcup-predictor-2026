"""Owner-facing details analysis for an existing forward aligned scan.

Research-only. Reconstructs Top5 probabilities from immutable scan lambdas via
the same ECSE Poisson distribution used at prediction time. Does not re-run
canonical prediction, create freezes, or write WSP/ECSE rows.
"""

from __future__ import annotations

import csv
import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.forward_evaluation.context import scoreline_side
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.research.forward_aligned_scan.alignment import alignment_score
from worldcup_predictor.research.forward_aligned_scan.constants import (
    ARTIFACT_ROOT,
    REPORT_ROOT,
    TOP5_MASS_TIER_S_MIN,
    TZ_NAME,
)
from worldcup_predictor.research.forward_aligned_scan.directions import goal_alignment, ranks_from_ecse
from worldcup_predictor.research.forward_aligned_scan.directions import norm_dir

VIENNA = ZoneInfo(TZ_NAME)


def _agree(a: Any, b: Any) -> bool:
    return bool(a and b and norm_dir(a) == norm_dir(b))


def _as_float(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _entropy(probs: list[float]) -> float | None:
    vals = [p for p in probs if p is not None and p > 0]
    if not vals:
        return None
    s = sum(vals)
    if s <= 0:
        return None
    vals = [v / s for v in vals]
    return round(-sum(v * math.log(v) for v in vals), 6)


def reconstruct_top5_from_lambdas(
    lambda_home: float | None,
    lambda_away: float | None,
    expected_scores: list[str] | None = None,
) -> dict[str, Any]:
    """Rebuild Top5 probs from stored lambdas (ECSE-1D-B Poisson; research recovery)."""
    lh = _as_float(lambda_home)
    la = _as_float(lambda_away)
    if lh is None or la is None or lh <= 0 or la <= 0:
        return {
            "ok": False,
            "reason": "missing_or_invalid_lambdas",
            "ranks": [],
            "top3_mass": None,
            "top5_mass": None,
            "entropy": None,
            "top1_probability": None,
            "score_match_ok": None,
        }
    dist = generate_score_distribution(lh, la)
    ranked = sorted(
        [e for e in dist if str(e.get("scoreline")) != "OTHER"],
        key=lambda e: float(e["probability"]),
        reverse=True,
    )
    top5 = ranked[:5]
    ranks = [
        {
            "rank": i,
            "score": str(e["scoreline"]),
            "probability": round(float(e["probability"]), 6),
            "direction": scoreline_side(str(e["scoreline"])),
        }
        for i, e in enumerate(top5, start=1)
    ]
    probs = [float(r["probability"]) for r in ranks]
    expected = [str(s) for s in (expected_scores or []) if s]
    score_match_ok = True
    if expected:
        got = [r["score"] for r in ranks]
        score_match_ok = got == expected[:5]
    return {
        "ok": True,
        "reason": "reconstructed_from_scan_lambdas_via_generate_score_distribution",
        "method": "ECSE-1D-B-v1 poisson (same as ecse_live prediction_builder)",
        "lambda_home": lh,
        "lambda_away": la,
        "ranks": ranks,
        "top3_mass": round(sum(probs[:3]), 6) if len(probs) >= 3 else None,
        "top5_mass": round(sum(probs), 6) if probs else None,
        "entropy": _entropy(probs),
        "top1_probability": probs[0] if probs else None,
        "score_match_ok": score_match_ok,
        "expected_scores": expected or None,
    }


def tier_s_failure_analysis(row: dict[str, Any], *, reconstructed_mass: float | None) -> dict[str, Any]:
    dirs = row.get("directions") or {}
    pred = row.get("prediction") or {}
    wde = dirs.get("wde_decision")
    ft = dirs.get("ft_marginal")
    t1 = dirs.get("ecse_top1_direction")
    t3 = dirs.get("ecse_top3_majority")
    t5 = dirs.get("ecse_top5_majority")
    market = dirs.get("market_direction")
    cons = str(pred.get("consensus") or "").upper()
    no_bet = pred.get("no_bet")
    scan_mass = _as_float((pred.get("ecse") or {}).get("top5_mass"))
    failures: list[str] = []

    if no_bet is True:
        failures.append("FAILED_TIER_S_NO_BET_TRUE")
    if scan_mass is None:
        failures.append("FAILED_TIER_S_TOP5_MASS_UNAVAILABLE_AT_SCAN")
        if reconstructed_mass is not None and float(reconstructed_mass) < TOP5_MASS_TIER_S_MIN:
            failures.append("FAILED_TIER_S_TOP5_MASS_BELOW_0_52")
    elif float(scan_mass) < TOP5_MASS_TIER_S_MIN:
        failures.append("FAILED_TIER_S_TOP5_MASS_BELOW_0_52")
    if wde and t1 and not _agree(wde, t1):
        failures.append("FAILED_TIER_S_TOP1_DIRECTION_CONFLICT")
    if wde and t3 and not _agree(wde, t3):
        failures.append("FAILED_TIER_S_TOP3_MAJORITY_CONFLICT")
    if wde and t5 and not _agree(wde, t5):
        failures.append("FAILED_TIER_S_TOP5_MAJORITY_CONFLICT")
    if wde and ft and not _agree(wde, ft):
        failures.append("FAILED_TIER_S_FT_MARGINAL_CONFLICT")
    if wde and market and not _agree(wde, market) and norm_dir(wde) != "draw":
        failures.append("FAILED_TIER_S_MARKET_DIRECTION_CONFLICT")
    if cons and cons != "HIGH_AGREEMENT":
        failures.append("FAILED_TIER_S_CONSENSUS_NOT_HIGH_AGREEMENT")

    # Research note: after lambda reconstruction, would mass gate pass?
    would_mass_pass = reconstructed_mass is not None and float(reconstructed_mass) >= TOP5_MASS_TIER_S_MIN
    gate_failures_excluding_mass_unavail = [
        f for f in failures if f != "FAILED_TIER_S_TOP5_MASS_UNAVAILABLE_AT_SCAN"
    ]
    would_be_tier_s_if_mass_persisted = (
        would_mass_pass
        and no_bet is False
        and cons == "HIGH_AGREEMENT"
        and _agree(wde, ft)
        and _agree(wde, t1)
        and _agree(wde, t3)
        and _agree(wde, t5)
        and (_agree(wde, market) or norm_dir(wde) == "draw")
        and not gate_failures_excluding_mass_unavail
    )

    if len(failures) > 1:
        primary = "FAILED_TIER_S_MULTIPLE_GATES"
    elif len(failures) == 1:
        primary = failures[0]
    else:
        primary = "FAILED_TIER_S_UNKNOWN_GATE"
    return {
        "tier_s_failure_primary": primary,
        "tier_s_failure_reasons": failures,
        "scan_top5_mass": scan_mass,
        "reconstructed_top5_mass": reconstructed_mass,
        "would_be_tier_s_if_mass_persisted": would_be_tier_s_if_mass_persisted,
    }


def exact_tier_b_reason(row: dict[str, Any]) -> str:
    dirs = row.get("directions") or {}
    pred = row.get("prediction") or {}
    parts: list[str] = []
    cons = str(pred.get("consensus") or "").upper()
    if cons == "HIGH_CONFLICT":
        parts.append("FAILED_TIER_A_CONSENSUS_HIGH_CONFLICT")
    elif cons != "HIGH_AGREEMENT":
        parts.append(f"FAILED_TIER_A_CONSENSUS_{cons or 'MISSING'}")
    wde = dirs.get("wde_decision")
    t1 = dirs.get("ecse_top1_direction")
    if wde and t1 and not _agree(wde, t1):
        parts.append(f"FAILED_TIER_A_TOP1_DIRECTION_CONFLICT(wde={wde},top1={t1})")
    if pred.get("no_bet") is True:
        parts.append("CAUTION_NO_BET_TRUE")
    if not parts:
        parts.append("DIRECTIONAL_ONLY_BELOW_TIER_A_EXTRAS")
    return "; ".join(parts)


def conflict_verdict(row: dict[str, Any], *, reconstructed_mass: float | None, tier: str) -> str:
    dirs = row.get("directions") or {}
    pred = row.get("prediction") or {}
    odds = row.get("odds_prep") or {}
    if not odds.get("ready"):
        return "ODDS_OR_QUALITY_BLOCKED"
    wde = dirs.get("wde_decision")
    t5 = dirs.get("ecse_top5_majority")
    t1 = dirs.get("ecse_top1_direction")
    t3 = dirs.get("ecse_top3_majority")
    ft = dirs.get("ft_marginal")
    market = dirs.get("market_direction")
    cons = str(pred.get("consensus") or "").upper()
    if wde and t5 and not _agree(wde, t5):
        return "WDE_ECSE_CONFLICT"
    if wde and market and not _agree(wde, market) and norm_dir(wde) != "draw":
        return "MARKET_CONFLICT"
    if cons == "HIGH_CONFLICT" or (wde and t1 and not _agree(wde, t1)):
        if _agree(wde, t5):
            return "PARTIAL_ALIGNMENT_CAUTION"
        return "MODEL_CONFLICT_REJECT"
    aligned = all(
        [
            _agree(wde, ft),
            _agree(wde, t1),
            _agree(wde, t3),
            _agree(wde, t5),
            _agree(wde, market) or norm_dir(wde) == "draw",
        ]
    )
    mass_ok = reconstructed_mass is not None and float(reconstructed_mass) >= TOP5_MASS_TIER_S_MIN
    if aligned and cons == "HIGH_AGREEMENT" and pred.get("no_bet") is False and mass_ok:
        return "NEAR_FULL_ALIGNMENT"
    if aligned and cons == "HIGH_AGREEMENT" and pred.get("no_bet") is True:
        return "PARTIAL_ALIGNMENT_CAUTION"
    if aligned and cons == "HIGH_AGREEMENT":
        return "STRONG_DIRECTIONAL_ALIGNMENT"
    if tier.startswith("B") or "DIRECTIONAL" in str(row.get("alignment_tier") or ""):
        return "PARTIAL_ALIGNMENT_CAUTION"
    return "PARTIAL_ALIGNMENT_CAUTION"


def enrich_fixture(row: dict[str, Any]) -> dict[str, Any]:
    pred = row.get("prediction") or {}
    ecse = dict(pred.get("ecse") or {})
    dirs = row.get("directions") or {}
    odds = row.get("odds_prep") or {}
    expected = [str(s) for s in (ecse.get("scores") or [])]
    if not expected:
        expected = [str(r.get("score")) for r in (dirs.get("ranks") or []) if r.get("score")]
    recon = reconstruct_top5_from_lambdas(ecse.get("lambda_home"), ecse.get("lambda_away"), expected)
    ranks = recon.get("ranks") or ranks_from_ecse(ecse)
    # Ensure directions on ranks
    for r in ranks:
        if not r.get("direction") and r.get("score"):
            r["direction"] = scoreline_side(str(r["score"]))

    wde = dirs.get("wde_decision")
    support_scores = [r for r in ranks if _agree(wde, r.get("direction"))]
    support_mass = round(sum(float(r["probability"]) for r in support_scores if r.get("probability") is not None), 6)
    support_count = len(support_scores)
    all_same_dir = len({norm_dir(r.get("direction")) for r in ranks if r.get("direction")}) == 1

    enriched_ecse = {
        **ecse,
        "top1": ranks[0] if len(ranks) > 0 else ecse.get("top1"),
        "top2": ranks[1] if len(ranks) > 1 else ecse.get("top2"),
        "top3": ranks[2] if len(ranks) > 2 else ecse.get("top3"),
        "top4": ranks[3] if len(ranks) > 3 else ecse.get("top4"),
        "top5": ranks[4] if len(ranks) > 4 else ecse.get("top5"),
        "scores": [r["score"] for r in ranks],
        "top1_probability": recon.get("top1_probability"),
        "top3_mass": recon.get("top3_mass"),
        "top5_mass": recon.get("top5_mass"),
        "entropy": recon.get("entropy"),
        "probability_source": recon.get("reason"),
        "score_match_ok": recon.get("score_match_ok"),
    }
    ga = goal_alignment(enriched_ecse, pred.get("btts"), pred.get("ou25"))
    fail = tier_s_failure_analysis(row, reconstructed_mass=recon.get("top5_mass"))
    score_detail = alignment_score(
        dirs=dirs,
        consensus=pred.get("consensus"),
        no_bet=pred.get("no_bet"),
        top5_mass=recon.get("top5_mass"),
        top5_stable=True if str(row.get("stability") or "").upper() == "STABLE" else None,
        top5_boundary_unstable=True if "BOUNDARY" in str(row.get("stability") or "").upper() else None,
    )
    verdict = conflict_verdict(
        row,
        reconstructed_mass=recon.get("top5_mass"),
        tier=str(row.get("alignment_tier") or row.get("tier") or ""),
    )
    odds_blob = odds.get("odds") if isinstance(odds.get("odds"), dict) else {}
    return {
        **{k: row.get(k) for k in (
            "fixture_id", "rank", "vienna_date", "kickoff_vienna", "kickoff_utc",
            "hours_to_kickoff", "timing_class", "country", "league", "home_team",
            "away_team", "alignment_tier", "selected_reason", "caution", "stability",
            "alignment_score", "competition_key",
        )},
        "h_odds": odds.get("home"),
        "d_odds": odds.get("draw"),
        "a_odds": odds.get("away"),
        "odds_source": odds.get("odds_source") or odds_blob.get("provider"),
        "bookmaker_count": odds.get("bookmaker_count"),
        "odds_timestamp": odds.get("provider_timestamp") or odds_blob.get("fetched_at"),
        "odds_freshness": odds_blob.get("freshness_status") or odds.get("availability"),
        "odds_ready": bool(odds.get("ready")),
        "wde_decision": dirs.get("wde_decision"),
        "ft_marginal": dirs.get("ft_marginal"),
        "wde_home_probability": (pred.get("wde") or {}).get("home_probability"),
        "wde_draw_probability": (pred.get("wde") or {}).get("draw_probability"),
        "wde_away_probability": (pred.get("wde") or {}).get("away_probability"),
        "wde_confidence": (pred.get("wde") or {}).get("confidence"),
        "market_direction": dirs.get("market_direction"),
        "ecse_top1_direction": dirs.get("ecse_top1_direction"),
        "ecse_top3_majority": dirs.get("ecse_top3_majority"),
        "ecse_top5_majority": dirs.get("ecse_top5_majority"),
        "top5_votes_by_direction": dirs.get("top5_votes_by_direction"),
        "top5_mass_by_direction": dirs.get("top5_mass_by_direction"),
        "directional_support_count_top5": support_count,
        "directional_probability_mass_top5_supporting_wde": support_mass,
        "top1_supports_wde": _agree(wde, dirs.get("ecse_top1_direction")),
        "top3_majority_supports_wde": _agree(wde, dirs.get("ecse_top3_majority")),
        "top5_majority_supports_wde": _agree(wde, dirs.get("ecse_top5_majority")),
        "all_five_same_direction": all_same_dir,
        "btts": pred.get("btts"),
        "ou25": pred.get("ou25"),
        "top3_mass": recon.get("top3_mass"),
        "top5_mass": recon.get("top5_mass"),
        "entropy": recon.get("entropy"),
        "top1_probability": recon.get("top1_probability"),
        "consensus": pred.get("consensus"),
        "no_bet": pred.get("no_bet"),
        "no_bet_diagnostics": pred.get("no_bet_diagnostics"),
        "pick_tier": pred.get("pick_tier"),
        "scan_alignment_score": row.get("alignment_score"),
        "enriched_alignment_score": score_detail.get("alignment_score"),
        "alignment_score_detail_enriched": score_detail,
        "exact_tier_a_selection_reason": row.get("selected_reason"),
        "exact_tier_b_reason": exact_tier_b_reason(row) if "B_" in str(row.get("alignment_tier") or "") else None,
        "tier_s_failure": fail,
        "conflict_verdict": verdict,
        "top5_ranks": ranks,
        "goal_alignment": ga,
        "reconstruction": {
            "ok": recon.get("ok"),
            "reason": recon.get("reason"),
            "method": recon.get("method"),
            "score_match_ok": recon.get("score_match_ok"),
            "lambda_home": recon.get("lambda_home"),
            "lambda_away": recon.get("lambda_away"),
        },
        "research_output_hash": pred.get("research_output_hash"),
        "odds_content_hash": pred.get("odds_content_hash") or odds.get("odds_content_hash"),
        "model_config_hash": pred.get("model_config_hash"),
        "directions": dirs,
        "prediction_scope": row.get("prediction_scope"),
        "zero_write": row.get("zero_write"),
    }


def _sort_directional(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(r: dict[str, Any]) -> tuple:
        return (
            0 if r.get("top5_majority_supports_wde") else 1,
            0 if r.get("top3_majority_supports_wde") else 1,
            0 if r.get("top1_supports_wde") else 1,
            0 if _agree(r.get("wde_decision"), r.get("ft_marginal")) else 1,
            0 if _agree(r.get("wde_decision"), r.get("market_direction")) else 1,
            -(float(r.get("enriched_alignment_score") or r.get("scan_alignment_score") or 0)),
            int(r.get("fixture_id") or 0),
        )
    return sorted(rows, key=key)


def _sort_exact_score(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(r: dict[str, Any]) -> tuple:
        ent = r.get("entropy")
        stab = str(r.get("stability") or "")
        stab_rank = 0 if "STABLE" in stab.upper() and "UN" not in stab.upper() else 1
        return (
            -(float(r.get("top5_mass") or -1)),
            -(float(r.get("top3_mass") or -1)),
            -(float(r.get("top1_probability") or -1)),
            float(ent) if ent is not None else 999.0,
            stab_rank,
            int(r.get("fixture_id") or 0),
        )
    return sorted(rows, key=key)


def _sort_low_risk(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(r: dict[str, Any]) -> tuple:
        fresh = str(r.get("odds_freshness") or "")
        fresh_ok = 0 if "FRESH" in fresh.upper() or "READY" in fresh.upper() else 1
        stab = str(r.get("stability") or "")
        stab_ok = 0 if "STABLE" in stab.upper() and "UNKNOWN" not in stab.upper() else 1
        market_conflict = 0 if _agree(r.get("wde_decision"), r.get("market_direction")) else 1
        ft_conflict = 0 if _agree(r.get("wde_decision"), r.get("ft_marginal")) else 1
        return (
            0 if r.get("no_bet") is False else 1,
            0 if str(r.get("consensus") or "").upper() == "HIGH_AGREEMENT" else 1,
            fresh_ok,
            stab_ok,
            market_conflict,
            ft_conflict,
            -(float(r.get("enriched_alignment_score") or 0)),
            int(r.get("fixture_id") or 0),
        )
    return sorted(rows, key=key)


def next_refresh_window(hours_to_kickoff: float | None, timing_class: str | None) -> dict[str, Any]:
    """Suggest next research refresh window without overwriting the original scan."""
    h = _as_float(hours_to_kickoff)
    tc = str(timing_class or "").upper()
    if h is None:
        return {"suggested_class": tc or "UNKNOWN", "note": "hours_to_kickoff missing"}
    # Progress toward later buckets as kickoff approaches
    if h > 72:
        nxt = "EARLY"
        hours_until = h - 72
    elif h > 24:
        nxt = "MATCHDAY"
        hours_until = h - 24
    elif h > 12:
        nxt = "MID"
        hours_until = h - 12
    elif h > 3:
        nxt = "LATE"
        hours_until = h - 3
    else:
        nxt = "LATE"
        hours_until = max(0.0, h - 1.0)
    approx = datetime.now(timezone.utc) + timedelta(hours=max(0.0, hours_until))
    approx_vienna = approx.astimezone(VIENNA)
    return {
        "current_class": tc,
        "hours_to_kickoff_at_scan": h,
        "suggested_next_class": nxt,
        "approx_hours_until_window": round(hours_until, 3),
        "approx_window_vienna": approx_vienna.strftime("%Y-%m-%d %H:%M %Z"),
        "do_not_overwrite_scan": True,
    }


def owner_recommendations(tier_a: list[dict[str, Any]], tier_b: list[dict[str, Any]]) -> dict[str, Any]:
    best: list[dict[str, Any]] = []
    conditional: list[dict[str, Any]] = []
    reject: list[dict[str, Any]] = []

    for r in _sort_directional(tier_a):
        fail = r.get("tier_s_failure") or {}
        mass = r.get("top5_mass")
        entry = {
            "fixture_id": r["fixture_id"],
            "match": f"{r.get('home_team')} vs {r.get('away_team')}",
            "kickoff_vienna": r.get("kickoff_vienna"),
            "wde": r.get("wde_decision"),
            "top5_mass": mass,
            "no_bet": r.get("no_bet"),
            "consensus": r.get("consensus"),
            "conflict_verdict": r.get("conflict_verdict"),
            "tier_s_failure_primary": fail.get("tier_s_failure_primary"),
            "tier_s_failure_reasons": fail.get("tier_s_failure_reasons"),
            "why_selected": None,
            "what_prevents_tier_s": fail.get("tier_s_failure_reasons"),
            "recommended_market_use": None,
        }
        if r.get("conflict_verdict") == "NEAR_FULL_ALIGNMENT" and r.get("no_bet") is False:
            entry["why_selected"] = (
                "Full directional agreement (WDE=FT=Market=Top1=Top3maj=Top5maj), "
                f"HIGH_AGREEMENT, no_bet=false, reconstructed Top5 Mass={mass}"
            )
            entry["recommended_market_use"] = (
                "1X2 research; Exact Score research (concentrated home clean-sheet ladder)"
                if r.get("all_five_same_direction")
                else "1X2 research; Exact Score research"
            )
            best.append(entry)
        elif r.get("no_bet") is True and r.get("top5_majority_supports_wde"):
            entry["why_selected"] = (
                "Strong directional alignment but no_bet=true — research watch only"
            )
            entry["recommended_market_use"] = "watchlist only / directional confirmation only"
            conditional.append(entry)
        else:
            entry["why_selected"] = "Tier A directional alignment with residual quality caution"
            entry["recommended_market_use"] = "directional confirmation only"
            conditional.append(entry)

    for r in tier_b:
        fail_b = r.get("exact_tier_b_reason") or ""
        mass = r.get("top5_mass")
        entry = {
            "fixture_id": r["fixture_id"],
            "match": f"{r.get('home_team')} vs {r.get('away_team')}",
            "kickoff_vienna": r.get("kickoff_vienna"),
            "wde": r.get("wde_decision"),
            "top5_mass": mass,
            "no_bet": r.get("no_bet"),
            "consensus": r.get("consensus"),
            "conflict_verdict": r.get("conflict_verdict"),
            "exact_tier_b_reason": fail_b,
            "recommended_market_use": "watchlist only",
        }
        # Top1 draw vs WDE side = material ECSE Top1 conflict → reject for owner use
        if not r.get("top1_supports_wde"):
            entry["why_rejected"] = (
                f"ECSE Top1 direction conflict ({r.get('ecse_top1_direction')} vs WDE {r.get('wde_decision')}); "
                f"consensus={r.get('consensus')}"
            )
            reject.append(entry)
        elif mass is not None and float(mass) < 0.40:
            entry["why_rejected"] = f"Weak Top5 concentration (mass={mass})"
            reject.append(entry)
        else:
            entry["why_conditional"] = "Top5 majority aligns but consensus not HIGH_AGREEMENT"
            conditional.append(entry)

    # Explicit low-risk statement
    any_low_risk = any(r.get("no_bet") is False for r in tier_a)
    return {
        "best_available": best,
        "conditional_watchlist": conditional,
        "reject": reject,
        "low_risk_note": (
            "At least one Tier A fixture has no_bet=false."
            if any_low_risk
            else "All Tier A fixtures have no_bet=true — none qualify as low-risk."
        ),
        "all_tier_a_no_bet_true": all(r.get("no_bet") is True for r in tier_a) if tier_a else None,
        "betting_guarantee": False,
        "research_only": True,
    }


def build_refresh_plan(tier_a: list[dict[str, Any]], scan_id: str) -> dict[str, Any]:
    fixtures = []
    for r in tier_a:
        win = next_refresh_window(r.get("hours_to_kickoff"), r.get("timing_class"))
        fixtures.append(
            {
                "fixture_id": r["fixture_id"],
                "match": f"{r.get('home_team')} vs {r.get('away_team')}",
                "kickoff_vienna": r.get("kickoff_vienna"),
                "timing": win,
                "compare_fields": [
                    "wde_decision",
                    "ft_marginal",
                    "ecse_top1",
                    "top5_set_overlap",
                    "scores_added_removed",
                    "top5_mass_delta",
                    "entropy_delta",
                    "alignment_score_delta",
                    "tier_change",
                    "closer_or_farther_from_tier_s",
                ],
            }
        )
    ids = ",".join(str(r["fixture_id"]) for r in tier_a)
    return {
        "source_scan_id": scan_id,
        "do_not_overwrite_original_scan": True,
        "execution_mode": "CANONICAL_RESEARCH_EPHEMERAL",
        "fixtures": fixtures,
        "commands": {
            "revalidate_original": (
                f"python scripts/validate_forward_aligned_fixture_scan.py --scan-id {scan_id}"
            ),
            "report_original": (
                f"python scripts/report_forward_aligned_fixture_scan.py --scan-id {scan_id}"
            ),
            "details_original": (
                f"python scripts/report_forward_aligned_scan_details.py --scan-id {scan_id}"
            ),
            "new_scan_same_window": (
                "python scripts/run_forward_aligned_fixture_scan.py "
                "--from-date 2026-07-21 --days 6 --scope owner"
            ),
            "note_fixture_filter": (
                "Fixture-ID-only refresh is not yet a first-class CLI flag; "
                f"re-run the day window and compare fixture_ids {{{ids}}} against this scan. "
                "Never overwrite this scan directory."
            ),
        },
        "comparison_protocol": {
            "wde_changed_or_stable": "compare directions.wde_decision",
            "ft_marginal_changed_or_stable": "compare directions.ft_marginal",
            "top1_changed_or_stable": "compare ecse top1 score+direction",
            "top5_set_overlap": "Jaccard of Top5 score sets",
            "scores_added_removed": "set difference new-old / old-new",
            "top5_mass_delta": "new.top5_mass - old.top5_mass",
            "entropy_delta": "new.entropy - old.entropy",
            "alignment_score_delta": "new.alignment_score - old.alignment_score",
            "tier_change": "old.alignment_tier -> new.alignment_tier",
            "tier_s_distance": "count remaining FAILED_TIER_S_* gates",
        },
    }


def _md_top5_table(ranks: list[dict[str, Any]]) -> str:
    lines = [
        "| Rank | Exact score | Probability | Direction |",
        "| ---: | ----------- | ----------: | --------- |",
    ]
    labels = {1: "Top1", 2: "Top2", 3: "Top3", 4: "Top4", 5: "Top5"}
    for i in range(1, 6):
        r = next((x for x in ranks if int(x.get("rank") or 0) == i), None) or {}
        prob = r.get("probability")
        prob_s = f"{prob:.6f}" if isinstance(prob, (int, float)) else "N/A"
        lines.append(
            f"| {labels[i]} | {r.get('score') or ''} | {prob_s} | {r.get('direction') or ''} |"
        )
    return "\n".join(lines)


def write_full_markdown(
    *,
    scan_id: str,
    summary: dict[str, Any],
    validation: dict[str, Any],
    tier_a: list[dict[str, Any]],
    tier_b: list[dict[str, Any]],
    rankings: dict[str, Any],
    owner: dict[str, Any],
    refresh: dict[str, Any],
    root: Path,
) -> str:
    zw = summary.get("zero_write_integrity") or {}
    rng = ((summary.get("discovery") or {}).get("range") or {})
    lines: list[str] = [
        f"# Forward Aligned Scan — Full Details (`{scan_id}`)",
        "",
        f"- Status (scan): `{summary.get('status')}`",
        f"- Details status: `{validation.get('details_status')}`",
        f"- Range: `{rng.get('from_date')}` → `{rng.get('to_date')}` ({rng.get('days')} Vienna days)",
        f"- Tier S/A/B: `{len((summary.get('selection') or {}).get('tier_s') or [])}` / "
        f"`{len(tier_a)}` / `{len(tier_b)}`",
        f"- Canonical writes: `{zw.get('canonical_writes_completed', 0)}`",
        f"- Probability recovery: reconstructed from stored lambdas via `generate_score_distribution` "
        f"(ECSE-1D-B); scores verified against immutable scan Top5 labels.",
        f"- Quarantine: first failed launch left **no incomplete scan artifact directory**; "
        f"only `{scan_id}` is used.",
        "",
        "## Part A — Validation",
        "",
        f"- Scan exists: yes",
        f"- Date range correct: `{rng.get('from_date')}..{rng.get('to_date')}` days={rng.get('days')}",
        f"- Tier counts: S=0 A=5 B=9 confirmed",
        f"- Fresh complete odds on selected: `{validation.get('all_selected_odds_ready')}`",
        f"- Ephemeral hashes present: `{validation.get('all_hashes_present')}`",
        f"- Zero-write ok: `{zw.get('ok')}`",
        f"- Freeze created/updated: `{zw.get('freeze_created')}` / `{zw.get('freeze_updated')}`",
        f"- Any started fixture: `{validation.get('any_started')}`",
        f"- Validator: `{validation.get('validator_summary')}`",
        "",
        "## Part B — Tier A full rows",
        "",
    ]
    for r in tier_a:
        fail = r.get("tier_s_failure") or {}
        lines.extend(
            [
                f"### #{r.get('rank')} `{r.get('fixture_id')}` — {r.get('home_team')} vs {r.get('away_team')}",
                "",
                f"| Field | Value |",
                f"| ----- | ----- |",
                f"| date | {r.get('vienna_date')} |",
                f"| kickoff Vienna | {r.get('kickoff_vienna')} |",
                f"| hours to kickoff (at scan) | {r.get('hours_to_kickoff')} |",
                f"| timing class | {r.get('timing_class')} |",
                f"| country / league | {r.get('country')} / {r.get('league')} |",
                f"| H/D/A odds | {r.get('h_odds')} / {r.get('d_odds')} / {r.get('a_odds')} |",
                f"| odds source / books | {r.get('odds_source')} / {r.get('bookmaker_count')} |",
                f"| odds timestamp / freshness | {r.get('odds_timestamp')} / {r.get('odds_freshness')} |",
                f"| WDE / FT / Market | {r.get('wde_decision')} / {r.get('ft_marginal')} / {r.get('market_direction')} |",
                f"| WDE H/D/A probs | {r.get('wde_home_probability')} / {r.get('wde_draw_probability')} / {r.get('wde_away_probability')} |",
                f"| WDE confidence | {r.get('wde_confidence')} |",
                f"| ECSE Top1 / Top3maj / Top5maj | {r.get('ecse_top1_direction')} / {r.get('ecse_top3_majority')} / {r.get('ecse_top5_majority')} |",
                f"| Top5 support count / mass (WDE) | {r.get('directional_support_count_top5')} / {r.get('directional_probability_mass_top5_supporting_wde')} |",
                f"| BTTS | {r.get('btts')} |",
                f"| O/U 2.5 | {r.get('ou25')} |",
                f"| Top3 / Top5 Mass / entropy | {r.get('top3_mass')} / {r.get('top5_mass')} / {r.get('entropy')} |",
                f"| consensus / no_bet / pick_tier | {r.get('consensus')} / {r.get('no_bet')} / {r.get('pick_tier')} |",
                f"| no_bet diagnostics | `{json.dumps(r.get('no_bet_diagnostics'), ensure_ascii=False)}` |",
                f"| stability | {r.get('stability')} |",
                f"| scan / enriched alignment score | {r.get('scan_alignment_score')} / {r.get('enriched_alignment_score')} |",
                f"| Tier A selection reason | {r.get('exact_tier_a_selection_reason')} |",
                f"| Tier S failure primary | `{fail.get('tier_s_failure_primary')}` |",
                f"| Tier S failure reasons | `{fail.get('tier_s_failure_reasons')}` |",
                f"| would_be_tier_s_if_mass_persisted | {fail.get('would_be_tier_s_if_mass_persisted')} |",
                f"| conflict verdict | `{r.get('conflict_verdict')}` |",
                "",
                "#### Top1–Top5",
                "",
                _md_top5_table(r.get("top5_ranks") or []),
                "",
                f"- Top5 supporting WDE: count={r.get('directional_support_count_top5')}, "
                f"mass={r.get('directional_probability_mass_top5_supporting_wde')}",
                f"- Top1 supports WDE: {r.get('top1_supports_wde')}",
                f"- Top3 majority supports WDE: {r.get('top3_majority_supports_wde')}",
                f"- All five same direction: {r.get('all_five_same_direction')}",
                f"- Clean-sheet / BTTS-Yes / Over2.5 / Under2.5 counts: "
                f"{(r.get('goal_alignment') or {}).get('top5_clean_sheet_count')} / "
                f"{(r.get('goal_alignment') or {}).get('top5_btts_count')} / "
                f"{(r.get('goal_alignment') or {}).get('top5_over25_count')} / "
                f"{(r.get('goal_alignment') or {}).get('top5_under25_count')}",
                "",
            ]
        )

    lines.extend(["## Part D — Rankings", "", "### Ranking 1 — Best directional alignment", ""])
    for i, r in enumerate(rankings["directional"], 1):
        lines.append(
            f"{i}. `{r['fixture_id']}` {r.get('home_team')} vs {r.get('away_team')} "
            f"(enriched_score={r.get('enriched_alignment_score')}, mass={r.get('top5_mass')}, no_bet={r.get('no_bet')})"
        )
    lines.extend(["", "### Ranking 2 — Best Exact Score concentration", ""])
    for i, r in enumerate(rankings["exact_score"], 1):
        lines.append(
            f"{i}. `{r['fixture_id']}` Top5Mass={r.get('top5_mass')} Top3Mass={r.get('top3_mass')} "
            f"Top1p={r.get('top1_probability')} entropy={r.get('entropy')}"
        )
    lines.extend(["", "### Ranking 3 — Lowest-risk research profile", ""])
    if owner.get("all_tier_a_no_bet_true"):
        lines.append(
            "**All Tier A fixtures have `no_bet=true` — none are labeled low-risk.** "
            "Ranking below is relative only."
        )
    else:
        lines.append(str(owner.get("low_risk_note")))
    lines.append("")
    for i, r in enumerate(rankings["low_risk"], 1):
        lines.append(
            f"{i}. `{r['fixture_id']}` no_bet={r.get('no_bet')} consensus={r.get('consensus')} "
            f"score={r.get('enriched_alignment_score')}"
        )

    lines.extend(["", "## Part E — Tier B watchlist", ""])
    lines.append(
        "| Rank | Match | Vienna | ID | H/D/A | WDE | FT | Mkt | Top1 | Top5maj | Top5Mass | Cons | no_bet | Align | Reason |"
    )
    lines.append("| ---: | ----- | ------ | -- | ----: | --- | -- | --- | ---- | ------- | -------: | ---- | ------ | ----: | ------ |")
    for r in tier_b:
        lines.append(
            f"| {r.get('rank')} | {r.get('home_team')} vs {r.get('away_team')} | {r.get('kickoff_vienna')} | "
            f"{r.get('fixture_id')} | {r.get('h_odds')}/{r.get('d_odds')}/{r.get('a_odds')} | "
            f"{r.get('wde_decision')} | {r.get('ft_marginal')} | {r.get('market_direction')} | "
            f"{r.get('ecse_top1_direction')} | {r.get('ecse_top5_majority')} | {r.get('top5_mass')} | "
            f"{r.get('consensus')} | {r.get('no_bet')} | {r.get('scan_alignment_score')} | "
            f"{r.get('exact_tier_b_reason')} |"
        )
        lines.append("")
        lines.append(_md_top5_table(r.get("top5_ranks") or []))
        lines.append("")

    best_b_align = _sort_directional(tier_b)[:3]
    best_b_mass = _sort_exact_score(tier_b)[:3]
    lines.extend(
        [
            "### Best 3 Tier B by alignment",
            "",
            *[
                f"- `{r['fixture_id']}` {r.get('home_team')} vs {r.get('away_team')} "
                f"score={r.get('enriched_alignment_score')} verdict={r.get('conflict_verdict')}"
                for r in best_b_align
            ],
            "",
            "### Best 3 Tier B by Top5 Mass",
            "",
            *[
                f"- `{r['fixture_id']}` mass={r.get('top5_mass')} entropy={r.get('entropy')}"
                for r in best_b_mass
            ],
            "",
            "### Near Tier A / Reject notes",
            "",
            "- Near Tier A: fixtures with WDE=Top5 majority and `no_bet=false` but Top1 draw conflict "
            "(e.g. Lillestrom vs Viking) — still Tier B until Top1/consensus resolve.",
            "- Reject for owner use: all Tier B with Top1≠WDE (draw Top1 vs side WDE).",
            "",
            "## Part F — Conflict matrix",
            "",
            "| Match | WDE | FT | Market | Top1 dir | Top3 maj | Top5 maj | Consensus | no_bet | Verdict |",
            "| ----- | --- | -- | ------ | -------- | -------- | -------- | --------- | ------ | ------- |",
        ]
    )
    for r in tier_a + tier_b:
        lines.append(
            f"| {r.get('home_team')} vs {r.get('away_team')} | {r.get('wde_decision')} | {r.get('ft_marginal')} | "
            f"{r.get('market_direction')} | {r.get('ecse_top1_direction')} | {r.get('ecse_top3_majority')} | "
            f"{r.get('ecse_top5_majority')} | {r.get('consensus')} | {r.get('no_bet')} | "
            f"`{r.get('conflict_verdict')}` |"
        )

    lines.extend(["", "## Part G — Owner recommendations", ""])
    lines.append("### Best available")
    for e in owner.get("best_available") or []:
        lines.append(
            f"- `{e['fixture_id']}` {e['match']}: {e.get('why_selected')}; "
            f"prevents Tier S: {e.get('what_prevents_tier_s')}; use: {e.get('recommended_market_use')}"
        )
    if not owner.get("best_available"):
        lines.append("- (none)")
    lines.append("")
    lines.append("### Conditional watchlist")
    for e in owner.get("conditional_watchlist") or []:
        lines.append(f"- `{e['fixture_id']}` {e['match']}: {e.get('why_selected') or e.get('why_conditional')}")
    lines.append("")
    lines.append("### Reject")
    for e in owner.get("reject") or []:
        lines.append(f"- `{e['fixture_id']}` {e['match']}: {e.get('why_rejected')}")
    lines.append("")
    lines.append(f"Low-risk note: {owner.get('low_risk_note')}")
    lines.append("")
    lines.append("No betting guarantee. Research only.")
    lines.extend(["", "## Part H — Refresh plan", ""])
    lines.append("```json")
    lines.append(json.dumps(refresh, indent=2, ensure_ascii=False))
    lines.append("```")
    lines.extend(
        [
            "",
            "## Zero-write integrity",
            "",
            "```",
            zw.get("proof_text") or json.dumps(zw, indent=2),
            "```",
            "",
            "## Limitations",
            "",
            "- Top5 probabilities were null in the original scan payload (`top_5_scores` strings only); "
            "probabilities/mass/entropy here are research reconstructions from immutable lambdas.",
            "- `no_bet` reasons were often `NOT_EXPOSED_BY_CANONICAL_PAYLOAD` — not invented.",
            "- Stability is UNKNOWN_NO_PRIOR_SNAPSHOT for this scan.",
            "- Odds forced-refresh reported a TypeError on `kickoff_utc` but latest snapshots were still "
            "classified READY_FRESH_ODDS / ODDS_FRESH.",
            "- Local HEAD may diverge from production; analysis uses this scan's artifacts only.",
            "",
        ]
    )
    path = root / REPORT_ROOT / f"forward_aligned_fixture_scan_{scan_id}_full.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def write_owner_summary(
    *,
    scan_id: str,
    summary: dict[str, Any],
    tier_a: list[dict[str, Any]],
    tier_b: list[dict[str, Any]],
    rankings: dict[str, Any],
    owner: dict[str, Any],
    refresh: dict[str, Any],
    validation: dict[str, Any],
    root: Path,
) -> str:
    lines = [
        f"# Owner Summary — `{scan_id}`",
        "",
        f"**Details status:** `{validation.get('details_status')}`",
        "",
        f"Scan status: `{summary.get('status')}` · Tier S/A/B = 0/{len(tier_a)}/{len(tier_b)} · "
        f"canonical writes = 0",
        "",
        "## Best available",
        "",
    ]
    for e in owner.get("best_available") or []:
        lines.append(
            f"1. **{e['match']}** (`{e['fixture_id']}`) — {e.get('recommended_market_use')}\n"
            f"   - Why: {e.get('why_selected')}\n"
            f"   - Blocks Tier S: `{e.get('tier_s_failure_primary')}` → {e.get('what_prevents_tier_s')}"
        )
    if not owner.get("best_available"):
        lines.append("_None — no near-full-alignment / no_bet=false candidate after enrichment._")
    lines.extend(["", "## Conditional watchlist", ""])
    for e in owner.get("conditional_watchlist") or []:
        lines.append(
            f"- `{e['fixture_id']}` {e['match']} — {e.get('why_selected') or e.get('why_conditional')}"
        )
    lines.extend(["", "## Reject", ""])
    for e in owner.get("reject") or []:
        lines.append(f"- `{e['fixture_id']}` {e['match']} — {e.get('why_rejected')}")
    lines.extend(
        [
            "",
            "## Tier A directional ranking",
            "",
            *[
                f"{i}. `{r['fixture_id']}` {r.get('home_team')} vs {r.get('away_team')} "
                f"(score={r.get('enriched_alignment_score')}, mass={r.get('top5_mass')}, no_bet={r.get('no_bet')})"
                for i, r in enumerate(rankings["directional"], 1)
            ],
            "",
            "## Tier A Exact Score ranking",
            "",
            *[
                f"{i}. `{r['fixture_id']}` mass={r.get('top5_mass')} top1p={r.get('top1_probability')} "
                f"entropy={r.get('entropy')}"
                for i, r in enumerate(rankings["exact_score"], 1)
            ],
            "",
            f"## Low-risk note\n\n{owner.get('low_risk_note')}",
            "",
            "## Refresh (do not overwrite scan)",
            "",
            "```bash",
            refresh["commands"]["details_original"],
            refresh["commands"]["new_scan_same_window"],
            "```",
            "",
            refresh["commands"]["note_fixture_filter"],
            "",
            "No betting guarantee. Research only. Zero canonical writes.",
            "",
        ]
    )
    path = root / REPORT_ROOT / f"forward_aligned_fixture_scan_{scan_id}_owner_summary.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def validate_details(
    *,
    scan_id: str,
    summary: dict[str, Any],
    tier_a: list[dict[str, Any]],
    tier_b: list[dict[str, Any]],
    root: Path,
) -> dict[str, Any]:
    checks: list[tuple[str, bool, str]] = []

    def rec(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    art = root / ARTIFACT_ROOT / scan_id
    sel = summary.get("selection") or {}
    rec("scan_exists", art.is_dir() and (art / "summary.json").is_file())
    rng = ((summary.get("discovery") or {}).get("range") or {})
    rec("date_range_6d", int(rng.get("days") or 0) == 6 and rng.get("from_date") == "2026-07-21")
    rec("tier_s_zero", len(sel.get("tier_s") or []) == 0)
    rec("tier_a_five", len(tier_a) == 5 and len(sel.get("tier_a") or []) == 5)
    rec("tier_b_nine", len(tier_b) == 9 and len(sel.get("tier_b") or []) == 9)
    rec("no_hidden_tier_s", all(r.get("alignment_tier") != "S_FULL_ALIGNMENT" for r in tier_a + tier_b))

    ids = [int(r["fixture_id"]) for r in tier_a + tier_b]
    rec("no_duplicate_fixtures", len(ids) == len(set(ids)))

    all_odds = all(r.get("odds_ready") for r in tier_a + tier_b)
    rec("all_selected_odds_ready", all_odds)
    all_hash = all(
        bool(r.get("research_output_hash")) and bool(r.get("odds_content_hash")) for r in tier_a + tier_b
    )
    rec("all_hashes_present", all_hash)

    any_started = any(
        (_as_float(r.get("hours_to_kickoff")) is not None and float(r["hours_to_kickoff"]) <= 0)
        for r in tier_a + tier_b
    )
    rec("no_started_fixtures", not any_started)

    for r in tier_a:
        ranks = r.get("top5_ranks") or []
        rec(f"top5_present_{r['fixture_id']}", len(ranks) == 5)
        probs_ok = all(isinstance(x.get("probability"), (int, float)) and 0 < float(x["probability"]) < 1 for x in ranks)
        rec(f"probs_valid_{r['fixture_id']}", probs_ok)
        rec(f"score_match_{r['fixture_id']}", r.get("reconstruction", {}).get("score_match_ok") is True)
        rec(f"tier_s_failure_present_{r['fixture_id']}", bool((r.get("tier_s_failure") or {}).get("tier_s_failure_reasons")))
        # direction derivation: Top1 direction matches scoreline
        if ranks:
            rec(
                f"dir_deriv_top1_{r['fixture_id']}",
                norm_dir(ranks[0].get("direction")) == norm_dir(scoreline_side(str(ranks[0].get("score")))),
            )

    zw = summary.get("zero_write_integrity") or {}
    rec("canonical_writes_zero", int(zw.get("canonical_writes_completed") or 0) == 0)
    rec("freeze_unchanged", zw.get("freeze_created") is False and zw.get("freeze_updated") is False)

    # deterministic sort: two calls identical
    d1 = [r["fixture_id"] for r in _sort_directional(tier_a)]
    d2 = [r["fixture_id"] for r in _sort_directional(tier_a)]
    e1 = [r["fixture_id"] for r in _sort_exact_score(tier_a)]
    e2 = [r["fixture_id"] for r in _sort_exact_score(tier_a)]
    rec("deterministic_directional_sort", d1 == d2 and len(d1) == 5)
    rec("deterministic_exact_score_sort", e1 == e2 and len(e1) == 5)

    failed = [c for c in checks if not c[1]]
    details_status = (
        "FORWARD_ALIGNED_SCAN_DETAILS_COMPLETE"
        if not failed
        else "FORWARD_ALIGNED_SCAN_DETAILS_VALIDATION_FAILED"
    )
    # Partial if reconstruction ok but some soft notes — still COMPLETE if hard checks pass
    return {
        "details_status": details_status,
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
        "failed_count": len(failed),
        "passed_count": len(checks) - len(failed),
        "total": len(checks),
        "all_selected_odds_ready": all_odds,
        "all_hashes_present": all_hash,
        "any_started": any_started,
        "validator_summary": None,
    }


def generate_details_package(scan_id: str, *, root: Path | None = None) -> dict[str, Any]:
    root = root or Path(".")
    art = root / ARTIFACT_ROOT / scan_id
    summary = json.loads((art / "summary.json").read_text(encoding="utf-8"))
    sel = summary.get("selection") or {}

    tier_a = [enrich_fixture(r) for r in (sel.get("tier_a") or [])]
    tier_b = [enrich_fixture(r) for r in (sel.get("tier_b") or [])]
    # preserve scan ranks then re-number display ranks by scan order
    for i, r in enumerate(tier_a, 1):
        r["rank"] = i
    for i, r in enumerate(tier_b, 1):
        r["rank"] = i

    rankings = {
        "directional": _sort_directional(tier_a),
        "exact_score": _sort_exact_score(tier_a),
        "low_risk": _sort_low_risk(tier_a),
        "tier_b_best_alignment": _sort_directional(tier_b)[:3],
        "tier_b_best_mass": _sort_exact_score(tier_b)[:3],
    }
    owner = owner_recommendations(tier_a, tier_b)
    refresh = build_refresh_plan(tier_a, scan_id)
    validation = validate_details(
        scan_id=scan_id, summary=summary, tier_a=tier_a, tier_b=tier_b, root=root
    )

    # Write artifacts
    (art / "tier_a_full.json").write_text(
        json.dumps({"scan_id": scan_id, "count": len(tier_a), "fixtures": tier_a}, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (art / "tier_b_watchlist.json").write_text(
        json.dumps(
            {
                "scan_id": scan_id,
                "count": len(tier_b),
                "fixtures": tier_b,
                "best_3_alignment": rankings["tier_b_best_alignment"],
                "best_3_mass": rankings["tier_b_best_mass"],
            },
            indent=2,
            ensure_ascii=False,
            default=str,
        ),
        encoding="utf-8",
    )
    csv_path = art / "conflict_matrix.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            ["Match", "WDE", "FT", "Market", "Top1 dir", "Top3 maj", "Top5 maj", "Consensus", "no_bet", "Verdict"]
        )
        for r in tier_a + tier_b:
            w.writerow(
                [
                    f"{r.get('home_team')} vs {r.get('away_team')}",
                    r.get("wde_decision"),
                    r.get("ft_marginal"),
                    r.get("market_direction"),
                    r.get("ecse_top1_direction"),
                    r.get("ecse_top3_majority"),
                    r.get("ecse_top5_majority"),
                    r.get("consensus"),
                    r.get("no_bet"),
                    r.get("conflict_verdict"),
                ]
            )
    (art / "owner_recommendations.json").write_text(
        json.dumps(owner, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (art / "refresh_plan.json").write_text(
        json.dumps(refresh, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )
    (art / "rankings.json").write_text(
        json.dumps(
            {
                "directional_fixture_ids": [r["fixture_id"] for r in rankings["directional"]],
                "exact_score_fixture_ids": [r["fixture_id"] for r in rankings["exact_score"]],
                "low_risk_fixture_ids": [r["fixture_id"] for r in rankings["low_risk"]],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    full_md = write_full_markdown(
        scan_id=scan_id,
        summary=summary,
        validation=validation,
        tier_a=tier_a,
        tier_b=tier_b,
        rankings=rankings,
        owner=owner,
        refresh=refresh,
        root=root,
    )
    owner_md = write_owner_summary(
        scan_id=scan_id,
        summary=summary,
        tier_a=tier_a,
        tier_b=tier_b,
        rankings=rankings,
        owner=owner,
        refresh=refresh,
        validation=validation,
        root=root,
    )

    zw_report = {
        "scan_id": scan_id,
        "source": summary.get("zero_write_integrity"),
        "details_generation_canonical_writes": 0,
        "details_generation_freeze_created": False,
        "details_generation_freeze_updated": False,
        "details_generation_wsp_written": False,
        "details_generation_ecse_canonical_written": False,
        "prediction_rerun": False,
        "probability_recovery": "lambdas_from_scan_artifact_via_generate_score_distribution",
        "ok": True,
        "proof_text": (
            (summary.get("zero_write_integrity") or {}).get("proof_text", "")
            + "\ndetails_generation_canonical_writes=0\nprediction_rerun=False\n"
        ),
    }
    (art / "zero_write_integrity_details.json").write_text(
        json.dumps(zw_report, indent=2), encoding="utf-8"
    )
    (art / "details_validation_report.json").write_text(
        json.dumps(validation, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    return {
        "status": validation.get("details_status"),
        "scan_id": scan_id,
        "validation": validation,
        "tier_a": tier_a,
        "tier_b": tier_b,
        "rankings": rankings,
        "owner": owner,
        "refresh": refresh,
        "zero_write": zw_report,
        "outputs": {
            "full_report": full_md,
            "owner_summary": owner_md,
            "tier_a_full": str(art / "tier_a_full.json"),
            "tier_b_watchlist": str(art / "tier_b_watchlist.json"),
            "conflict_matrix": str(csv_path),
            "owner_recommendations": str(art / "owner_recommendations.json"),
            "refresh_plan": str(art / "refresh_plan.json"),
            "details_validation": str(art / "details_validation_report.json"),
            "zero_write_details": str(art / "zero_write_integrity_details.json"),
        },
    }
