"""Phase 30A/30C — structured prediction output: detailed markets + ranked recommendations."""

from __future__ import annotations

import json
from typing import Any, Literal

from worldcup_predictor.api.market_ranking_engine import (
    build_market_ranking,
    ranked_to_recommended_bets,
)
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.prediction.extended_markets import (
    build_extended_markets,
    load_extended_markets_from_prediction,
)

SelectionStatus = Literal["recommended", "no_bet", "informational"]

_SELECTION_LABELS: dict[str, str] = {
    "home_win": "Home Win",
    "draw": "Draw",
    "away_win": "Away Win",
    "home": "Home Win",
    "away": "Away Win",
    "over_2_5": "Over 2.5",
    "under_2_5": "Under 2.5",
    "yes": "BTTS Yes",
    "no": "BTTS No",
}

_MIN_CONFIDENCE = 55.0
_MIN_DATA_QUALITY = 45.0


def _pct(value: float | None, *, as_fraction: bool = False) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if as_fraction or num <= 1.0:
        return round(num * 100, 1)
    return round(num, 1)


def _label(selection: str) -> str:
    return _SELECTION_LABELS.get(selection, selection.replace("_", " ").title())


def _map_1x2_api(selection: str) -> str:
    mapping = {"home_win": "home", "draw": "draw", "away_win": "away"}
    return mapping.get(selection, selection)


def _risk_level(prediction: MatchPrediction) -> str:
    return str(prediction.risk_level or "medium")


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


def _source_agents(specialist_summary: dict[str, Any] | None) -> list[str]:
    agents = (specialist_summary or {}).get("agents") or {}
    names: list[str] = []
    if (specialist_summary or {}).get("aggregated_score") is not None:
        names.append("Specialists")
    domain_map = {
        "odds": "Odds",
        "form": "Form",
        "lineup": "Lineup",
        "injury": "Injuries",
        "tactics": "Tactics",
        "weather": "Weather",
    }
    for key, label in domain_map.items():
        block = agents.get(key) if isinstance(agents, dict) else None
        if isinstance(block, dict) and str(block.get("status", "")).lower() in ("available", "partial"):
            names.append(label)
    if "WDE" not in names:
        names.insert(0, "WDE")
    return names[:6]


def _ft_probabilities(prediction: MatchPrediction) -> dict[str, float]:
    raw_ft = (prediction.metadata or {}).get("extended_markets_ft_1x2")
    if raw_ft:
        try:
            ft = json.loads(raw_ft) if isinstance(raw_ft, str) else raw_ft
            if isinstance(ft, dict) and "home" in ft:
                return {
                    "home_win": _pct(ft["home"], as_fraction=True) or 0.0,
                    "draw": _pct(ft["draw"], as_fraction=True) or 0.0,
                    "away_win": _pct(ft["away"], as_fraction=True) or 0.0,
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    raw_ext = (prediction.metadata or {}).get("extended_markets")
    if raw_ext:
        try:
            data = json.loads(raw_ext) if isinstance(raw_ext, str) else raw_ext
            ft = (data or {}).get("full_time_1x2") or {}
            if ft:
                return {
                    "home_win": _pct(ft.get("home"), as_fraction=True) or 0.0,
                    "draw": _pct(ft.get("draw"), as_fraction=True) or 0.0,
                    "away_win": _pct(ft.get("away"), as_fraction=True) or 0.0,
                }
        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    sel = prediction.one_x_two.selection
    prob = float(prediction.one_x_two.probability or 0.33)
    base = max(prob, 0.33)
    remainder = max(0.0, 1.0 - base)
    if sel == "home_win":
        return {
            "home_win": _pct(base, as_fraction=True) or 0.0,
            "draw": _pct(remainder / 2, as_fraction=True) or 0.0,
            "away_win": _pct(remainder / 2, as_fraction=True) or 0.0,
        }
    if sel == "away_win":
        return {
            "home_win": _pct(remainder / 2, as_fraction=True) or 0.0,
            "draw": _pct(remainder / 2, as_fraction=True) or 0.0,
            "away_win": _pct(base, as_fraction=True) or 0.0,
        }
    return {
        "home_win": _pct(remainder / 2, as_fraction=True) or 0.0,
        "draw": _pct(base, as_fraction=True) or 0.0,
        "away_win": _pct(remainder / 2, as_fraction=True) or 0.0,
    }


def build_detailed_markets(
    prediction: MatchPrediction,
    *,
    ft_probs: dict[str, float] | None = None,
) -> dict[str, Any]:
    snap = load_extended_markets_from_prediction(prediction) or build_extended_markets(prediction, None)
    ft = ft_probs or _ft_probabilities(prediction)

    ou_sel = prediction.over_under.selection
    ou_prob = float(prediction.over_under.probability or 0.55)
    if ou_sel == "over_2_5":
        over_pct, under_pct = _pct(ou_prob, as_fraction=True) or 0.0, _pct(1 - ou_prob, as_fraction=True) or 0.0
    else:
        under_pct, over_pct = _pct(ou_prob, as_fraction=True) or 0.0, _pct(1 - ou_prob, as_fraction=True) or 0.0

    if snap:
        ou_a, ou_b = snap.over_under_2_5.as_percent()
        over_pct, under_pct = ou_a, ou_b
        btts_yes, btts_no = snap.btts.as_percent()
        ht_pct = snap.halftime_1x2.as_percent()
        ht_probs = {"home_win": ht_pct["home"], "draw": ht_pct["draw"], "away_win": ht_pct["away"]}
    else:
        btts_yes, btts_no = 50.0, 50.0
        ht_probs = {"home_win": 33.0, "draw": 34.0, "away_win": 33.0}

    btts_sel = "yes" if btts_yes >= btts_no else "no"
    btts_prob = max(btts_yes, btts_no) / 100.0

    ht_leader = max(ht_probs, key=lambda k: ht_probs.get(k, 0))
    ht_map = {"home_win": "home_win", "draw": "draw", "away_win": "away_win"}

    first_goal_team = prediction.first_goal.team or None
    first_goal_player = prediction.first_goal.player if not prediction.first_goal.player_data_unavailable else None
    minute_range = prediction.first_goal.minute_range or (
        snap.first_goal_time.minute_band if snap else None
    )

    goalscorer = None
    if snap and snap.has_player_data and snap.top_scorer.player:
        goalscorer = {
            "player": snap.top_scorer.player,
            "team": snap.top_scorer.team,
            "confidence": snap.top_scorer.confidence,
            "available": True,
        }
    elif first_goal_player:
        goalscorer = {
            "player": first_goal_player,
            "team": first_goal_team,
            "confidence": None,
            "available": True,
        }
    else:
        goalscorer = {"available": False, "player": None, "team": None}

    ou_selection = "over_2_5" if over_pct >= under_pct else "under_2_5"

    return {
        "match_winner": {
            "selection": prediction.one_x_two.selection,
            "display": _label(prediction.one_x_two.selection),
            "probabilities": ft,
            "confidence": _pct(prediction.one_x_two.probability, as_fraction=True),
        },
        "over_under_25": {
            "selection": ou_selection,
            "display": _label(ou_selection),
            "probability": max(over_pct, under_pct) / 100.0,
            "probabilities": {"over_2_5": over_pct, "under_2_5": under_pct},
        },
        "btts": {
            "selection": btts_sel,
            "display": _label(btts_sel),
            "probability": btts_prob,
            "probabilities": {"yes": btts_yes, "no": btts_no},
        },
        "halftime": {
            "selection": ht_map.get(ht_leader, ht_leader),
            "display": _label(ht_map.get(ht_leader, ht_leader)),
            "probabilities": ht_probs,
        },
        "first_goal": {
            "team": first_goal_team,
            "player": first_goal_player,
            "minute_range": minute_range,
            "expected_minute": snap.first_goal_time.expected_minute if snap else None,
        },
        "goalscorer": goalscorer,
        "first_half_team_to_score": {
            "note": "Derived from halftime xG model",
            "leader": _label(ht_map.get(ht_leader, ht_leader)),
            "probabilities": ht_probs,
        },
        "double_chance": _double_chance(ft),
        "correct_scores": list(snap.correct_scores if snap else [])[:3],
    }


def _double_chance(ft: dict[str, float]) -> dict[str, Any]:
    home = float(ft.get("home_win") or 0)
    draw = float(ft.get("draw") or 0)
    away = float(ft.get("away_win") or 0)
    return {
        "home_or_draw": round(home + draw, 1),
        "home_or_away": round(home + away, 1),
        "draw_or_away": round(draw + away, 1),
    }


def build_recommended_bets(
    prediction: MatchPrediction,
    detailed_markets: dict[str, Any],
    *,
    specialist_summary: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Backward-compatible recommended_bets — delegates to Phase 30C ranking."""
    risk = _risk_level(prediction)
    sources = _source_agents(specialist_summary)
    ranking = build_market_ranking(
        prediction,
        detailed_markets,
        specialist_summary=specialist_summary,
        source_agents=sources,
        risk_level=risk,
    )
    return ranked_to_recommended_bets(
        ranking,
        source_agents=sources,
        prediction=prediction,
        risk_level=risk,
    )


def build_probabilities_block(
    prediction: MatchPrediction,
    detailed_markets: dict[str, Any],
) -> dict[str, Any]:
    """Backward-compatible probabilities dict — always includes O/U."""
    ft = (detailed_markets.get("match_winner") or {}).get("probabilities") or _ft_probabilities(prediction)
    ou = detailed_markets.get("over_under_25") or {}
    btts = detailed_markets.get("btts") or {}
    return {
        "home_win": ft.get("home_win"),
        "draw": ft.get("draw"),
        "away_win": ft.get("away_win"),
        "over_under_2_5": {
            "selection": ou.get("selection") or prediction.over_under.selection,
            "probability": ou.get("probability") if ou.get("probability") is not None else prediction.over_under.probability,
            "probabilities": ou.get("probabilities"),
        },
        "btts": {
            "selection": btts.get("selection"),
            "probability": btts.get("probability"),
            "probabilities": btts.get("probabilities"),
        },
    }


def build_prediction_output(
    prediction: MatchPrediction,
    *,
    specialist_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    detailed = build_detailed_markets(prediction)
    risk = _risk_level(prediction)
    sources = _source_agents(specialist_summary)
    ranking = build_market_ranking(
        prediction,
        detailed,
        specialist_summary=specialist_summary,
        source_agents=sources,
        risk_level=risk,
    )
    recommended = ranked_to_recommended_bets(
        ranking,
        source_agents=sources,
        prediction=prediction,
        risk_level=risk,
    )
    tracking = dict(ranking.get("accuracy_tracking") or {})
    tracking["recommended_bets_slots"] = [
        {
            "market_key": bet.get("market_key") or bet.get("market", "").lower().replace("/", "_"),
            "selection": bet.get("selection") or bet.get("pick"),
            "bucket": bet.get("bucket"),
        }
        for bet in recommended
        if bet.get("status") == "recommended"
    ]
    return {
        "recommended_bets": recommended,
        "detailed_markets": detailed,
        "probabilities": build_probabilities_block(prediction, detailed),
        "risk_level": risk,
        "no_bet": recommended[0].get("status") == "no_bet" if recommended else True,
        "primary_recommendation": recommended[0] if recommended else None,
        "market_ranking": ranking.get("market_ranking") or [],
        "safe_pick": ranking.get("safe_pick"),
        "value_pick": ranking.get("value_pick"),
        "aggressive_pick": ranking.get("aggressive_pick"),
        "accuracy_tracking": tracking,
    }


def enrich_cached_prediction_output(payload: dict[str, Any]) -> dict[str, Any]:
    """Backfill Phase 30A/30C fields on cached payloads missing ranking or recommendations."""
    has_legacy = payload.get("recommended_bets") and payload.get("detailed_markets")
    if has_legacy and "market_ranking" in payload:
        return payload
    try:
        from worldcup_predictor.domain.prediction import (
            ConfidenceLevel,
            FirstGoalPrediction,
            HalftimePrediction,
            MarketPrediction,
            MatchPrediction,
            PredictionConfidenceBreakdown,
        )

        sel_map = {"home": "home_win", "draw": "draw", "away": "away_win"}
        raw_sel = str(payload.get("prediction") or "home")
        one_x_two_sel = sel_map.get(raw_sel, raw_sel)
        probs = payload.get("probabilities") or {}
        ou = probs.get("over_under_2_5") or {}

        prediction = MatchPrediction(
            fixture_id=int(payload.get("fixture_id") or 0),
            competition_key="world_cup_2026",
            match_name=f"{payload.get('home_team', 'Home')} vs {payload.get('away_team', 'Away')}",
            one_x_two=MarketPrediction("1x2", one_x_two_sel, float(probs.get("home_win", 50)) / 100 if raw_sel == "home" else 0.5),
            over_under=MarketPrediction(
                "over_under_2_5",
                str(ou.get("selection") or "under_2_5"),
                float(ou.get("probability") or 0.5),
            ),
            halftime=HalftimePrediction(estimated_total_goals=2.5),
            first_goal=FirstGoalPrediction(team=""),
            confidence_score=float(payload.get("confidence") or 0),
            confidence_level=ConfidenceLevel.MEDIUM,
            confidence_breakdown=PredictionConfidenceBreakdown(
                form_score=50, h2h_score=50, injuries_score=50, lineups_score=50,
                odds_score=50, data_quality_score=float(payload.get("data_quality") or 50), total=50,
            ),
            risk_level=str(payload.get("risk_level") or "medium"),
            no_bet_flag=bool(payload.get("no_bet", False)),
            metadata={},
        )
        if payload.get("extended_markets"):
            prediction.metadata["extended_markets"] = payload["extended_markets"]
        block = build_prediction_output(prediction, specialist_summary=payload.get("specialist_summary"))
        out = dict(payload)
        out.update(block)
        return out
    except Exception:
        return payload
