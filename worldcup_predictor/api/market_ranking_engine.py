"""Phase 30C — cross-market ranking engine for safe / value / aggressive picks."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from worldcup_predictor.domain.prediction import MatchPrediction

Bucket = Literal["safe", "value", "aggressive"]

_MIN_CONFIDENCE = 55.0
_MIN_DATA_QUALITY = 45.0
_MIN_SAFE_PROB = 0.52
_MIN_VALUE_PROB = 0.55
_MIN_AGGRESSIVE_PROB = 0.32

_DC_LABELS = {
    "home_or_draw": "Home or Draw",
    "home_or_away": "Home or Away",
    "draw_or_away": "Draw or Away",
}

_1X2_LABELS = {
    "home_win": "Home Win",
    "draw": "Draw",
    "away_win": "Away Win",
}


@dataclass
class MarketCandidate:
    market_key: str
    market: str
    pick: str
    selection: str
    probability: float
    bucket: Bucket
    correlated_selections: frozenset[str] = field(default_factory=frozenset)
    rank_inputs: dict[str, float] = field(default_factory=dict)


def _norm_prob(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        num = float(value)
    except (TypeError, ValueError):
        return 0.0
    return num / 100.0 if num > 1.0 else num


def _data_quality(prediction: MatchPrediction) -> float:
    if prediction.confidence_breakdown is not None:
        score = float(prediction.confidence_breakdown.data_quality_score)
        return score * 100 if score <= 1.0 else score
    raw = (prediction.metadata or {}).get("data_quality_pct")
    if raw is not None:
        try:
            val = float(raw)
            return val * 100 if val <= 1.0 else val
        except (TypeError, ValueError):
            pass
    return float(prediction.prediction_quality_score or 0.0)


def _specialist_score(specialist_summary: dict[str, Any] | None) -> float | None:
    raw = (specialist_summary or {}).get("aggregated_score")
    if raw is None:
        return None
    try:
        val = float(raw)
        return val / 100.0 if val > 1.0 else val
    except (TypeError, ValueError):
        return None


def _consistency_factor(prediction: MatchPrediction) -> float:
    meta = prediction.metadata or {}
    passed = str(meta.get("consistency_passed", "true")).lower()
    if passed == "false" or prediction.consistency_notes:
        return 0.88
    return 1.0


def _odds_consensus_factor(specialist_summary: dict[str, Any] | None) -> float:
    agents = (specialist_summary or {}).get("agents") or {}
    mc = agents.get("market_consensus_agent") if isinstance(agents, dict) else None
    if not isinstance(mc, dict):
        return 0.0
    agreement = str((mc.get("signals") or {}).get("model_market_agreement", "")).lower()
    if agreement == "high":
        return 0.05
    if agreement == "low":
        return -0.05
    return 0.0


def _first_goal_team_prob(ft_pct: dict[str, float], team_name: str | None, home_team: str, away_team: str) -> float:
    if not team_name:
        return 0.0
    h = _norm_prob(ft_pct.get("home_win"))
    d = _norm_prob(ft_pct.get("draw"))
    a = _norm_prob(ft_pct.get("away_win"))
    team_lower = team_name.strip().lower()
    if team_lower == home_team.strip().lower():
        return min(1.0, h + d * 0.45)
    if team_lower == away_team.strip().lower():
        return min(1.0, a + d * 0.45)
    return max(h, a)


def _split_teams(match_name: str) -> tuple[str, str]:
    if " vs " in match_name:
        home, away = match_name.split(" vs ", 1)
        return home.strip(), away.strip()
    return match_name.strip(), "Away"


def build_market_candidates(
    prediction: MatchPrediction,
    detailed_markets: dict[str, Any],
) -> list[MarketCandidate]:
    """Unified candidate list — skips unavailable markets safely."""
    candidates: list[MarketCandidate] = []
    home_team, away_team = _split_teams(prediction.match_name)

    mw = detailed_markets.get("match_winner") or {}
    ft = mw.get("probabilities") or {}
    one_x_two_sel = str(mw.get("selection") or prediction.one_x_two.selection)
    one_x_two_prob = _norm_prob(ft.get(one_x_two_sel))
    if one_x_two_prob <= 0:
        one_x_two_prob = _norm_prob(prediction.one_x_two.probability)
    if one_x_two_prob > 0:
        candidates.append(
            MarketCandidate(
                market_key="1x2",
                market="1X2",
                pick=_1X2_LABELS.get(one_x_two_sel, one_x_two_sel.replace("_", " ").title()),
                selection=one_x_two_sel,
                probability=one_x_two_prob,
                bucket="safe",
                correlated_selections=frozenset({one_x_two_sel}),
            )
        )

    dc = detailed_markets.get("double_chance") or {}
    if dc:
        dc_options = {
            "home_or_draw": float(dc.get("home_or_draw") or 0),
            "home_or_away": float(dc.get("home_or_away") or 0),
            "draw_or_away": float(dc.get("draw_or_away") or 0),
        }
        best_dc_key = max(dc_options, key=lambda k: dc_options[k])
        best_dc_prob = _norm_prob(dc_options[best_dc_key])
        if best_dc_prob > 0:
            corr = {best_dc_key}
            if best_dc_key == "home_or_draw":
                corr.update({"home_win", "draw"})
            elif best_dc_key == "home_or_away":
                corr.update({"home_win", "away_win"})
            else:
                corr.update({"draw", "away_win"})
            candidates.append(
                MarketCandidate(
                    market_key="double_chance",
                    market="Double Chance",
                    pick=_DC_LABELS[best_dc_key],
                    selection=best_dc_key,
                    probability=best_dc_prob,
                    bucket="safe",
                    correlated_selections=frozenset(corr),
                )
            )

    ou = detailed_markets.get("over_under_25") or {}
    ou_sel = str(ou.get("selection") or "")
    ou_prob = _norm_prob(ou.get("probability"))
    if ou_prob > 0 and ou_sel:
        display = "Over 2.5" if "over" in ou_sel else "Under 2.5"
        candidates.append(
            MarketCandidate(
                market_key="over_under_2_5",
                market="Over/Under 2.5",
                pick=display,
                selection=ou_sel,
                probability=ou_prob,
                bucket="value",
                correlated_selections=frozenset({ou_sel}),
            )
        )

    btts = detailed_markets.get("btts") or {}
    btts_sel = str(btts.get("selection") or "")
    btts_prob = _norm_prob(btts.get("probability"))
    if btts_prob > 0 and btts_sel:
        display = "BTTS Yes" if btts_sel == "yes" else "BTTS No"
        candidates.append(
            MarketCandidate(
                market_key="btts",
                market="BTTS",
                pick=display,
                selection=btts_sel,
                probability=btts_prob,
                bucket="value",
                correlated_selections=frozenset({f"btts_{btts_sel}"}),
            )
        )

    ht = detailed_markets.get("halftime") or {}
    ht_probs = ht.get("probabilities") or {}
    if ht_probs:
        ht_leader = max(ht_probs, key=lambda k: float(ht_probs.get(k) or 0))
        ht_prob = _norm_prob(ht_probs.get(ht_leader))
        if ht_prob > 0:
            candidates.append(
                MarketCandidate(
                    market_key="ht_result",
                    market="HT Result",
                    pick=_1X2_LABELS.get(ht_leader, ht_leader.replace("_", " ").title()),
                    selection=ht_leader,
                    probability=ht_prob,
                    bucket="aggressive",
                    correlated_selections=frozenset({f"ht_{ht_leader}"}),
                )
            )

    fg = detailed_markets.get("first_goal") or {}
    fg_team = fg.get("team")
    if fg_team:
        fg_prob = _first_goal_team_prob(ft, str(fg_team), home_team, away_team)
        if fg_prob > 0:
            candidates.append(
                MarketCandidate(
                    market_key="first_goal_team",
                    market="First Team To Score",
                    pick=str(fg_team),
                    selection=f"first_goal_{fg_team}",
                    probability=fg_prob,
                    bucket="aggressive",
                    correlated_selections=frozenset({f"first_goal_{fg_team}"}),
                )
            )

    fh = detailed_markets.get("first_half_team_to_score") or {}
    fh_leader = fh.get("leader")
    fh_probs = fh.get("probabilities") or ht_probs
    if fh_leader and fh_probs:
        fh_key = next(
            (k for k, label in _1X2_LABELS.items() if label == fh_leader or k == fh_leader),
            None,
        )
        if fh_key:
            fh_prob = _norm_prob(fh_probs.get(fh_key))
            if fh_prob > 0:
                candidates.append(
                    MarketCandidate(
                        market_key="first_half_team_to_score",
                        market="Team To Score First Half",
                        pick=fh_leader,
                        selection=f"fh_score_{fh_key}",
                        probability=fh_prob,
                        bucket="aggressive",
                        correlated_selections=frozenset({f"fh_score_{fh_key}"}),
                    )
                )

    scores = detailed_markets.get("correct_scores") or []
    if scores and isinstance(scores, list):
        top = scores[0]
        if isinstance(top, dict):
            scoreline = str(top.get("scoreline") or top.get("score") or "")
            score_prob = _norm_prob(top.get("probability"))
            if scoreline and score_prob > 0:
                candidates.append(
                    MarketCandidate(
                        market_key="correct_score",
                        market="Correct Score",
                        pick=scoreline,
                        selection=f"score_{scoreline.replace('-', '_')}",
                        probability=score_prob,
                        bucket="aggressive",
                        correlated_selections=frozenset({f"score_{scoreline}"}),
                    )
                )

    gs = detailed_markets.get("goalscorer") or {}
    if gs.get("available") and gs.get("player"):
        gs_conf = gs.get("confidence")
        gs_prob = _norm_prob(gs_conf) if gs_conf is not None else 0.28
        candidates.append(
            MarketCandidate(
                market_key="goalscorer",
                market="Goalscorer",
                pick=str(gs["player"]),
                selection=f"scorer_{gs['player']}",
                probability=max(0.15, min(gs_prob, 0.55)),
                bucket="aggressive",
                correlated_selections=frozenset({f"scorer_{gs['player']}"}),
            )
        )

    minute_range = fg.get("minute_range")
    if minute_range and str(minute_range) not in {"—", "-", ""}:
        fg_time = detailed_markets.get("first_goal") or {}
        minute_conf = _norm_prob(fg_time.get("confidence")) if fg_time.get("confidence") else 0.38
        candidates.append(
            MarketCandidate(
                market_key="first_goal_minute",
                market="First Goal Minute",
                pick=str(minute_range),
                selection=f"minute_{str(minute_range).replace('-', '_')}",
                probability=max(0.18, min(minute_conf, 0.50)),
                bucket="aggressive",
                correlated_selections=frozenset({f"minute_{minute_range}"}),
            )
        )

    return candidates


def compute_market_rank_score(
    candidate: MarketCandidate,
    *,
    prediction: MatchPrediction,
    specialist_summary: dict[str, Any] | None,
) -> tuple[float, str]:
    """Return (market_rank_score 0..1, human explanation)."""
    wde = min(1.0, max(0.0, float(prediction.confidence_score or 0) / 100.0))
    dq = min(1.0, max(0.0, _data_quality(prediction) / 100.0))
    specialist = _specialist_score(specialist_summary)
    specialist_norm = specialist if specialist is not None else 0.55
    consistency = _consistency_factor(prediction)
    odds_adj = _odds_consensus_factor(specialist_summary)

    bucket_mult = {"safe": 1.0, "value": 0.96, "aggressive": 0.84}[candidate.bucket]

    raw = (
        0.48 * candidate.probability
        + 0.18 * wde
        + 0.14 * dq
        + 0.12 * specialist_norm
        + 0.08 * consistency
    )
    score = min(1.0, max(0.0, (raw + odds_adj) * bucket_mult))

    candidate.rank_inputs = {
        "probability": round(candidate.probability, 4),
        "wde_confidence": round(wde, 4),
        "data_quality": round(dq, 4),
        "specialist_agreement": round(specialist_norm, 4),
        "consistency_factor": round(consistency, 4),
        "odds_consensus_adj": round(odds_adj, 4),
        "bucket_multiplier": bucket_mult,
    }

    parts = [
        f"model probability {candidate.probability * 100:.1f}%",
        f"WDE confidence {wde * 100:.0f}%",
        f"data quality {dq * 100:.0f}%",
    ]
    if specialist is not None:
        parts.append(f"specialist agreement {specialist_norm * 100:.0f}%")
    if odds_adj:
        parts.append(f"odds consensus {'boost' if odds_adj > 0 else 'penalty'}")
    parts.append(f"{candidate.bucket} bucket")
    explanation = "; ".join(parts)
    return round(score, 4), explanation


def _is_correlated(a: MarketCandidate, b: MarketCandidate) -> bool:
    if a.market_key == b.market_key:
        return True
    if a.correlated_selections & b.correlated_selections:
        return True
    for sel in a.correlated_selections:
        if sel in b.correlated_selections:
            return True
    one_x_two = {"home_win", "draw", "away_win"}
    if a.market_key == "double_chance" and b.market_key == "1x2":
        if b.selection in a.correlated_selections:
            return True
    if b.market_key == "double_chance" and a.market_key == "1x2":
        if a.selection in b.correlated_selections:
            return True
    if a.market_key == "1x2" and b.market_key == "ht_result" and a.selection == b.selection:
        return True
    if a.market_key == "first_goal_team" and b.market_key == "1x2":
        return False
    _ = one_x_two
    return False


def _candidate_to_pick_dict(
    candidate: MarketCandidate,
    *,
    market_rank_score: float,
    explanation: str,
    risk_level: str,
    source_agents: list[str],
) -> dict[str, Any]:
    return {
        "market": candidate.market,
        "market_key": candidate.market_key,
        "pick": candidate.pick,
        "selection": candidate.selection,
        "display_text": f"{candidate.market}: {candidate.pick}",
        "probability": round(candidate.probability, 4),
        "confidence": round(candidate.probability, 4),
        "market_rank_score": market_rank_score,
        "bucket": candidate.bucket.upper(),
        "risk_level": risk_level,
        "reasoning": explanation,
        "source_agents": source_agents,
        "rank_inputs": dict(candidate.rank_inputs),
        "status": "recommended",
    }


def _meets_bucket_threshold(candidate: MarketCandidate) -> bool:
    if candidate.bucket == "safe":
        return candidate.probability >= _MIN_SAFE_PROB
    if candidate.bucket == "value":
        return candidate.probability >= _MIN_VALUE_PROB
    return candidate.probability >= _MIN_AGGRESSIVE_PROB


def build_market_ranking(
    prediction: MatchPrediction,
    detailed_markets: dict[str, Any],
    *,
    specialist_summary: dict[str, Any] | None = None,
    source_agents: list[str] | None = None,
    risk_level: str = "medium",
) -> dict[str, Any]:
    """Rank all candidates and assign safe / value / aggressive picks."""
    agents = list(source_agents or [])
    confidence = float(prediction.confidence_score or 0.0)
    data_quality = _data_quality(prediction)

    no_bet = (
        prediction.no_bet_flag
        or confidence < _MIN_CONFIDENCE
        or data_quality < _MIN_DATA_QUALITY
    )

    empty = {
        "market_ranking": [],
        "safe_pick": None,
        "value_pick": None,
        "aggressive_pick": None,
        "accuracy_tracking": _accuracy_tracking(None, None, None, no_bet=no_bet),
        "no_bet": no_bet,
    }
    if no_bet:
        return empty

    candidates = build_market_candidates(prediction, detailed_markets)
    ranked: list[tuple[MarketCandidate, float, str]] = []
    for cand in candidates:
        score, explanation = compute_market_rank_score(
            cand,
            prediction=prediction,
            specialist_summary=specialist_summary,
        )
        if _meets_bucket_threshold(cand):
            ranked.append((cand, score, explanation))

    ranked.sort(key=lambda row: row[1], reverse=True)

    market_ranking = [
        _candidate_to_pick_dict(
            cand,
            market_rank_score=score,
            explanation=explanation,
            risk_level=risk_level,
            source_agents=agents,
        )
        for cand, score, explanation in ranked
    ]

    safe_pick: dict[str, Any] | None = None
    value_pick: dict[str, Any] | None = None
    aggressive_pick: dict[str, Any] | None = None
    used: list[MarketCandidate] = []

    for cand, score, explanation in ranked:
        if cand.bucket != "safe" or safe_pick is not None:
            continue
        if any(_is_correlated(cand, u) for u in used):
            continue
        safe_pick = _candidate_to_pick_dict(
            cand, market_rank_score=score, explanation=explanation,
            risk_level=risk_level, source_agents=agents,
        )
        used.append(cand)

    for cand, score, explanation in ranked:
        if cand.bucket != "value" or value_pick is not None:
            continue
        if any(_is_correlated(cand, u) for u in used):
            continue
        value_pick = _candidate_to_pick_dict(
            cand, market_rank_score=score, explanation=explanation,
            risk_level=risk_level, source_agents=agents,
        )
        used.append(cand)

    for cand, score, explanation in ranked:
        if cand.bucket != "aggressive" or aggressive_pick is not None:
            continue
        if any(_is_correlated(cand, u) for u in used):
            continue
        aggressive_pick = _candidate_to_pick_dict(
            cand, market_rank_score=score, explanation=explanation,
            risk_level=risk_level, source_agents=agents,
        )
        used.append(cand)

    return {
        "market_ranking": market_ranking,
        "safe_pick": safe_pick,
        "value_pick": value_pick,
        "aggressive_pick": aggressive_pick,
        "accuracy_tracking": _accuracy_tracking(safe_pick, value_pick, aggressive_pick, no_bet=False),
        "no_bet": False,
    }


def _accuracy_tracking(
    safe: dict[str, Any] | None,
    value: dict[str, Any] | None,
    aggressive: dict[str, Any] | None,
    *,
    no_bet: bool,
) -> dict[str, Any]:
    """Future-proof structure for winrate evaluation — not wired to history yet."""

    def _slot(pick: dict[str, Any] | None) -> dict[str, Any] | None:
        if not pick:
            return None
        return {
            "market_key": pick.get("market_key"),
            "market": pick.get("market"),
            "selection": pick.get("selection"),
            "pick": pick.get("pick"),
            "probability": pick.get("probability"),
            "market_rank_score": pick.get("market_rank_score"),
            "bucket": pick.get("bucket"),
        }

    return {
        "schema_version": "1.0",
        "no_bet": no_bet,
        "safe_pick": _slot(safe),
        "value_pick": _slot(value),
        "aggressive_pick": _slot(aggressive),
        "recommended_bets_slots": [],
    }


def ranked_to_recommended_bets(
    ranking: dict[str, Any],
    *,
    source_agents: list[str] | None = None,
    prediction: MatchPrediction | None = None,
    risk_level: str = "medium",
) -> list[dict[str, Any]]:
    """Build backward-compatible recommended_bets from ranked picks."""
    agents = list(source_agents or [])

    if ranking.get("no_bet"):
        confidence = float(prediction.confidence_score or 0.0) if prediction else 0.0
        reason = "Model flagged elevated uncertainty (no-bet review)."
        if prediction and not prediction.no_bet_flag:
            reason = "Confidence or data quality below threshold for a clear bet recommendation."
        return [
            {
                "market": "none",
                "pick": "No Bet",
                "display_text": "No Bet — confidence or data quality too low",
                "confidence": round(confidence / 100.0, 3) if confidence > 1 else round(confidence, 3),
                "risk_level": risk_level,
                "reasoning": reason,
                "source_agents": agents,
                "status": "no_bet",
            }
        ]

    picks: list[dict[str, Any]] = []
    for key in ("safe_pick", "value_pick"):
        pick = ranking.get(key)
        if not pick:
            continue
        picks.append(
            {
                "market": pick["market"],
                "pick": pick["pick"],
                "display_text": f"Bet on {pick['pick']}",
                "confidence": pick["confidence"],
                "risk_level": pick.get("risk_level", risk_level),
                "reasoning": pick.get("reasoning", "Cross-market ranking signal."),
                "source_agents": pick.get("source_agents") or agents,
                "status": "recommended",
                "market_rank_score": pick.get("market_rank_score"),
                "bucket": pick.get("bucket"),
            }
        )
        if len(picks) >= 2:
            break

    if not picks:
        return ranked_to_recommended_bets(
            {"no_bet": True},
            source_agents=agents,
            prediction=prediction,
            risk_level=risk_level,
        )

    tracking = ranking.get("accuracy_tracking") or {}
    tracking["recommended_bets_slots"] = [
        {"market_key": p.get("market_key"), "selection": p.get("selection"), "bucket": p.get("bucket")}
        for p in (ranking.get("safe_pick"), ranking.get("value_pick"))
        if p
    ]
    return picks
