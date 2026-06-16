"""Extended prediction markets — BTTS, HT 1X2, goalscorers, correct score (helpers only)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from worldcup_predictor.domain.intelligence import MatchIntelligenceReport
from worldcup_predictor.domain.prediction import MatchPrediction, ScorelineCandidate
from worldcup_predictor.prediction.scoreline_engine import _expected_goals_from_report, _poisson_pmf


@dataclass
class ThreeWayProbabilities:
    home: float
    draw: float
    away: float

    def as_percent(self) -> dict[str, float]:
        return {
            "home": round(self.home * 100, 1),
            "draw": round(self.draw * 100, 1),
            "away": round(self.away * 100, 1),
        }


@dataclass
class TwoWayProbabilities:
    option_a: float
    option_b: float
    label_a: str = "a"
    label_b: str = "b"

    def as_percent(self) -> tuple[float, float]:
        return round(self.option_a * 100, 1), round(self.option_b * 100, 1)


@dataclass
class GoalscorerPick:
    player: str | None
    team: str | None
    confidence: float | None = None
    reason: str = ""


@dataclass
class FirstGoalTimeEstimate:
    minute_band: str
    expected_minute: int | None
    confidence: float | None = None


@dataclass
class ExtendedMarketsSnapshot:
    full_time_1x2: ThreeWayProbabilities
    over_under_2_5: TwoWayProbabilities
    btts: TwoWayProbabilities
    halftime_1x2: ThreeWayProbabilities
    first_goal_time: FirstGoalTimeEstimate
    top_scorer: GoalscorerPick
    home_scorer: GoalscorerPick
    away_scorer: GoalscorerPick
    correct_scores: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    data_quality_score: float = 0.0
    has_player_data: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_BAND_MIDPOINT: dict[str, int] = {
    "0-15": 8,
    "16-30": 23,
    "31-45": 38,
    "46-60": 53,
    "61-75": 68,
    "76-90": 83,
    "76-90+": 83,
    "no_goal": 0,
}


def _split_match_name(match_name: str) -> tuple[str, str]:
    if " vs " in match_name:
        home, away = match_name.split(" vs ", 1)
        return home.strip(), away.strip()
    return match_name, "Away"


def is_reliable_player_name(name: str | None) -> bool:
    """True only for real player names — never TBD / lineup placeholders."""
    if not name:
        return False
    text = str(name).strip()
    if not text or text in {"—", "-", "None", "none", "UNKNOWN", "unknown"}:
        return False
    lower = text.lower()
    if lower.startswith("tbd"):
        return False
    if "awaiting" in lower and "lineup" in lower:
        return False
    if lower in {"n/a", "na", "pending", "not available"}:
        return False
    return len(text) >= 2


def _poisson_three_way(home_lambda: float, away_lambda: float, *, max_goals: int = 5) -> ThreeWayProbabilities:
    home_lambda = max(0.15, min(home_lambda, 4.0))
    away_lambda = max(0.15, min(away_lambda, 4.0))
    p_home = p_draw = p_away = 0.0
    for h in range(max_goals + 1):
        for a in range(max_goals + 1):
            p = _poisson_pmf(h, home_lambda) * _poisson_pmf(a, away_lambda)
            if h > a:
                p_home += p
            elif h == a:
                p_draw += p
            else:
                p_away += p
    total = p_home + p_draw + p_away or 1.0
    return ThreeWayProbabilities(
        home=round(p_home / total, 4),
        draw=round(p_draw / total, 4),
        away=round(p_away / total, 4),
    )


def compute_btts_probabilities(home_lambda: float, away_lambda: float) -> TwoWayProbabilities:
    p_h = 1.0 - _poisson_pmf(0, max(home_lambda, 0.15))
    p_a = 1.0 - _poisson_pmf(0, max(away_lambda, 0.15))
    yes = max(0.0, min(1.0, p_h * p_a))
    return TwoWayProbabilities(option_a=yes, option_b=1.0 - yes, label_a="yes", label_b="no")


def compute_halftime_1x2(home_lambda: float, away_lambda: float) -> ThreeWayProbabilities:
    ht_factor = 0.45
    return _poisson_three_way(home_lambda * ht_factor, away_lambda * ht_factor)


def compute_over_under_probabilities(total_goals: float) -> TwoWayProbabilities:
    """Poisson total-goals approximation for O/U 2.5."""
    lam = max(0.5, min(total_goals, 5.0))
    p_under = sum(_poisson_pmf(k, lam) for k in range(0, 3))
    p_over = max(0.0, 1.0 - p_under)
    total = p_over + p_under or 1.0
    return TwoWayProbabilities(
        option_a=p_over / total,
        option_b=p_under / total,
        label_a="over_2_5",
        label_b="under_2_5",
    )


def extract_team_flag_url(team_name: str, fixture: Any | None, *, side: str) -> str | None:
    """API-Football logo from fixture if available."""
    if fixture is None:
        return None
    key = f"{side}_team_logo"
    url = getattr(fixture, key, None)
    if url and str(url).startswith("http"):
        return str(url)
    return None


def _ft_probs_from_prediction(
    prediction: MatchPrediction,
    report: MatchIntelligenceReport | None,
) -> ThreeWayProbabilities:
    raw = (prediction.metadata or {}).get("extended_markets_ft_1x2")
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return ThreeWayProbabilities(
                home=float(data["home"]),
                draw=float(data["draw"]),
                away=float(data["away"]),
            )
        except (TypeError, ValueError, KeyError, json.JSONDecodeError):
            pass
    if report is not None:
        try:
            h_lam, a_lam = _expected_goals_from_report(report)
            return _poisson_three_way(h_lam, a_lam)
        except Exception:
            pass
    sel = prediction.one_x_two.selection
    prob = float(prediction.one_x_two.probability or 0.55)
    prob = max(0.35, min(prob, 0.92))
    remainder = 1.0 - prob
    draw = remainder * 0.35
    other = remainder - draw
    if sel == "home_win":
        return ThreeWayProbabilities(home=prob, draw=draw, away=other)
    if sel == "away_win":
        return ThreeWayProbabilities(home=other, draw=draw, away=prob)
    return ThreeWayProbabilities(home=other * 0.5, draw=prob, away=other * 0.5)


def _first_goal_time(fg_v2: Any | None, prediction: MatchPrediction) -> FirstGoalTimeEstimate:
    band = "—"
    conf: float | None = None
    if fg_v2 is not None:
        band = getattr(fg_v2, "first_goal_minute_band", None) or band
        conf = getattr(fg_v2, "confidence", None)
    elif prediction.first_goal.minute_range:
        band = prediction.first_goal.minute_range
    display_band = band.replace("76-90", "76-90+") if band == "76-90" else band
    minute = _BAND_MIDPOINT.get(band) or _BAND_MIDPOINT.get(display_band.replace("+", ""))
    return FirstGoalTimeEstimate(minute_band=display_band, expected_minute=minute, confidence=conf)


def _scorer_picks(
    prediction: MatchPrediction,
    fg_v2: Any | None,
) -> tuple[GoalscorerPick, GoalscorerPick, GoalscorerPick, bool]:
    home_name, away_name = _split_match_name(prediction.match_name)
    candidates: list[Any] = []
    if fg_v2 and getattr(fg_v2, "likely_first_goal_scorers", None):
        candidates = list(fg_v2.likely_first_goal_scorers)
    elif prediction.first_goal.scorer_candidates:
        candidates = list(prediction.first_goal.scorer_candidates)

    def _to_pick(cand: Any | None) -> GoalscorerPick:
        if cand is None:
            return GoalscorerPick(player=None, team=None)
        if hasattr(cand, "player"):
            name = cand.player
            team = getattr(cand, "team", "") or ""
            conf = getattr(cand, "confidence", None) or getattr(cand, "score", None)
            reason = getattr(cand, "reason", "") or ""
        else:
            name = cand.get("player_name") or cand.get("player")
            team = cand.get("team", "")
            conf = cand.get("confidence") or cand.get("score")
            reason = cand.get("reason", "")
        pos = (getattr(cand, "position", "") or cand.get("position", "") if cand else "").upper()
        if pos in {"G", "GK", "GOALKEEPER"}:
            return GoalscorerPick(player=None, team=team)
        if not is_reliable_player_name(name):
            return GoalscorerPick(player=None, team=str(team) if team else None)
        return GoalscorerPick(
            player=str(name) if name else None,
            team=str(team) if team else None,
            confidence=float(conf) if conf is not None else None,
            reason=str(reason),
        )

    reliable_candidates = [c for c in candidates if is_reliable_player_name(_to_pick(c).player)]
    has_data = bool(reliable_candidates) or is_reliable_player_name(prediction.first_goal.player)

    top = _to_pick(reliable_candidates[0] if reliable_candidates else None)
    if not top.player and is_reliable_player_name(prediction.first_goal.player):
        top = GoalscorerPick(
            player=prediction.first_goal.player,
            team=prediction.first_goal.team,
        )

    home_c = next(
        (c for c in reliable_candidates if (_team_of(c) or "").lower() == home_name.lower()),
        None,
    )
    away_c = next(
        (c for c in reliable_candidates if (_team_of(c) or "").lower() == away_name.lower()),
        None,
    )
    return top, _to_pick(home_c), _to_pick(away_c), has_data


def _team_of(cand: Any) -> str:
    if hasattr(cand, "team"):
        return str(cand.team or "")
    return str(cand.get("team", "") if isinstance(cand, dict) else "")


def _correct_score_rows(candidates: list[ScorelineCandidate]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for cand in candidates[:3]:
        rows.append(
            {
                "label": cand.label,
                "probability": round(cand.probability * 100, 1),
            }
        )
    return rows


def build_extended_markets(
    prediction: MatchPrediction,
    report: MatchIntelligenceReport | None = None,
    *,
    fg_v2: Any | None = None,
) -> ExtendedMarketsSnapshot:
    """Build all extended market outputs — never raises."""
    home_lam, away_lam = 1.2, 1.0
    total_goals = 2.5
    try:
        if report is not None:
            home_lam, away_lam = _expected_goals_from_report(report)
            total_goals = home_lam + away_lam
        else:
            raw = (prediction.metadata or {}).get("expected_total_goals")
            if raw:
                total_goals = float(raw)
                home_lam = total_goals * 0.55
                away_lam = total_goals * 0.45
    except (TypeError, ValueError):
        pass

    ft = _ft_probs_from_prediction(prediction, report)
    ou_sel = prediction.over_under.selection
    ou_prob = float(prediction.over_under.probability or 0.55)
    ou_prob = max(0.35, min(ou_prob, 0.92))
    if ou_sel == "over_2_5":
        ou = TwoWayProbabilities(option_a=ou_prob, option_b=1.0 - ou_prob, label_a="over", label_b="under")
    else:
        ou = TwoWayProbabilities(option_a=1.0 - ou_prob, option_b=ou_prob, label_a="over", label_b="under")

    try:
        ou_model = compute_over_under_probabilities(total_goals)
        if abs(ou_model.option_a - ou.option_a) > 0.25:
            ou = ou_model
    except Exception:
        pass

    btts = compute_btts_probabilities(home_lam, away_lam)
    ht = compute_halftime_1x2(home_lam, away_lam)
    fg_time = _first_goal_time(fg_v2, prediction)
    top, home_sc, away_sc, has_players = _scorer_picks(prediction, fg_v2)
    dq = 0.0
    if prediction.confidence_breakdown:
        dq = prediction.confidence_breakdown.data_quality_score
        if dq <= 1.0:
            dq *= 100

    return ExtendedMarketsSnapshot(
        full_time_1x2=ft,
        over_under_2_5=ou,
        btts=btts,
        halftime_1x2=ht,
        first_goal_time=fg_time,
        top_scorer=top,
        home_scorer=home_sc,
        away_scorer=away_sc,
        correct_scores=_correct_score_rows(prediction.scoreline_candidates or []),
        confidence_score=float(prediction.confidence_score),
        data_quality_score=float(dq),
        has_player_data=has_players,
    )


def attach_extended_markets_to_prediction(
    prediction: MatchPrediction,
    report: MatchIntelligenceReport,
    *,
    fg_v2: Any | None = None,
) -> MatchPrediction:
    """Persist extended markets JSON in metadata — optional pipeline hook."""
    try:
        snap = build_extended_markets(prediction, report, fg_v2=fg_v2)
        ft = snap.full_time_1x2
        prediction.metadata = dict(prediction.metadata or {})
        prediction.metadata["extended_markets"] = json.dumps(snap.to_dict(), ensure_ascii=False)
        prediction.metadata["extended_markets_ft_1x2"] = json.dumps(
            {"home": ft.home, "draw": ft.draw, "away": ft.away}
        )
    except Exception:
        pass
    return prediction


def load_extended_markets_from_prediction(prediction: MatchPrediction) -> ExtendedMarketsSnapshot | None:
    raw = (prediction.metadata or {}).get("extended_markets")
    if not raw:
        return None
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        ft = data.get("full_time_1x2") or {}
        ou = data.get("over_under_2_5") or {}
        btts = data.get("btts") or {}
        ht = data.get("halftime_1x2") or {}
        fg = data.get("first_goal_time") or {}
        return ExtendedMarketsSnapshot(
            full_time_1x2=ThreeWayProbabilities(**ft),
            over_under_2_5=TwoWayProbabilities(**ou),
            btts=TwoWayProbabilities(**btts),
            halftime_1x2=ThreeWayProbabilities(**ht),
            first_goal_time=FirstGoalTimeEstimate(**fg),
            top_scorer=GoalscorerPick(**(data.get("top_scorer") or {})),
            home_scorer=GoalscorerPick(**(data.get("home_scorer") or {})),
            away_scorer=GoalscorerPick(**(data.get("away_scorer") or {})),
            correct_scores=list(data.get("correct_scores") or []),
            confidence_score=float(data.get("confidence_score") or 0),
            data_quality_score=float(data.get("data_quality_score") or 0),
            has_player_data=bool(data.get("has_player_data")),
        )
    except (TypeError, ValueError, KeyError, json.JSONDecodeError):
        return None
