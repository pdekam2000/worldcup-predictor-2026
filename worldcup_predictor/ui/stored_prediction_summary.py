"""Read-only stored prediction summaries for match cards — Phase 34A."""

from __future__ import annotations

import html
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import streamlit as st

from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.accuracy.models import EvaluatedPrediction, PredictionHistoryRecord
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.domain.prediction import MatchPrediction
from worldcup_predictor.prediction.extended_markets import is_reliable_player_name
from worldcup_predictor.schedule.match_center import classify_status
from worldcup_predictor.ui.gui_i18n import gui_t

try:
    from worldcup_predictor.accuracy.evaluator import evaluate_prediction as _evaluate_prediction
except ImportError:
    _evaluate_prediction = None  # type: ignore[misc, assignment]

_CACHE_KEY = "_stored_prediction_cache_v1"

_VERSION_LABELS = {
    "manual": "Manual",
    "early_24h": "Early 24h",
    "pre_6h": "Pre 6h",
    "final_lineup": "Final lineup",
}


def obj_get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


@dataclass(frozen=True)
class StoredPredictionEvaluation:
    """Safe evaluation wrapper — never raises."""

    status: Literal["pending", "evaluated", "unavailable"]
    markets: list[tuple[str, str, str, str]]
    raw: EvaluatedPrediction | None = None


def invalidate_stored_prediction_cache() -> None:
    st.session_state.pop(_CACHE_KEY, None)


@dataclass(frozen=True)
class StoredPredictionView:
    fixture_id: int
    home_team: str
    away_team: str
    predicted_1x2: str
    predicted_over_under: str
    predicted_scoreline: str | None
    predicted_first_goal_team: str | None
    confidence_score: float
    prediction_quality: float | None
    data_quality_score: float
    prediction_version: str
    created_at: str
    lineups_available: bool
    is_preliminary: bool
    predicted_first_goal_scorer: str | None = None
    source: str = "stored"
    verifications: tuple[dict[str, str], ...] = ()
    extended_markets_json: str | None = None

    @property
    def match_name(self) -> str:
        return f"{self.home_team} vs {self.away_team}"

    @classmethod
    def from_jsonl(cls, record: PredictionHistoryRecord) -> StoredPredictionView:
        return cls(
            fixture_id=record.fixture_id,
            home_team=record.home_team,
            away_team=record.away_team,
            predicted_1x2=record.predicted_1x2,
            predicted_over_under=record.predicted_over_under_2_5,
            predicted_scoreline=record.predicted_scoreline,
            predicted_first_goal_team=record.predicted_first_goal_team,
            confidence_score=record.confidence_score,
            prediction_quality=None,
            data_quality_score=record.data_quality_score,
            prediction_version=record.prediction_version,
            created_at=record.created_at,
            lineups_available=record.lineups_available,
            is_preliminary=record.is_preliminary,
            predicted_first_goal_scorer=getattr(record, "predicted_first_goal_scorer", None),
            source=record.source,
            extended_markets_json=getattr(record, "extended_markets_json", None),
        )

    @classmethod
    def from_db(cls, payload: dict[str, Any]) -> StoredPredictionView:
        pred = payload["prediction"]
        markets = payload.get("markets") or {}
        verifications = tuple(payload.get("verifications") or ())
        pq = pred.get("prediction_quality")
        return cls(
            fixture_id=int(pred["fixture_id"]),
            home_team=str(pred["home_team"]),
            away_team=str(pred["away_team"]),
            predicted_1x2=str(markets.get("1x2") or "draw"),
            predicted_over_under=str(markets.get("over_under_2_5") or "under_2_5"),
            predicted_scoreline=markets.get("scoreline_exact") or None,
            predicted_first_goal_team=markets.get("first_goal_team"),
            confidence_score=float(pred.get("confidence") or 0),
            prediction_quality=float(pq) if pq is not None else None,
            data_quality_score=float(pred.get("data_quality") or 0),
            prediction_version=str(pred.get("prediction_version") or "manual"),
            created_at=str(pred.get("created_at") or ""),
            lineups_available=bool(pred.get("lineups_available")),
            is_preliminary=bool(pred.get("is_preliminary")),
            predicted_first_goal_scorer=markets.get("first_goal_scorer") or markets.get("likely_scorer"),
            source=str(pred.get("source") or "live"),
            verifications=verifications,
            extended_markets_json=markets.get("extended_markets_json") or pred.get("extended_markets_json"),
        )


def _fetch_latest(fixture_id: int) -> StoredPredictionView | None:
    fid = int(fixture_id)
    try:
        repo = FootballIntelligenceRepository()
        payload = repo.latest_prediction_for_fixture(fid)
        repo.close()
        if payload:
            return StoredPredictionView.from_db(payload)
    except Exception:
        pass
    record = PredictionHistoryStore().latest_for_fixture(fid)
    if record:
        return StoredPredictionView.from_jsonl(record)
    return None


def get_latest_stored_prediction(fixture_id: int) -> StoredPredictionView | None:
    cache: dict[int, StoredPredictionView | None] = st.session_state.setdefault(_CACHE_KEY, {})
    fid = int(fixture_id)
    if fid not in cache:
        cache[fid] = _fetch_latest(fid)
    return cache[fid]


def has_stored_prediction(fixture_id: int) -> bool:
    return get_latest_stored_prediction(fixture_id) is not None


def _parse_created_at(iso_ts: str) -> datetime | None:
    if not iso_ts:
        return None
    try:
        text = iso_ts.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def format_time_ago(iso_ts: str) -> str:
    created = _parse_created_at(iso_ts)
    if created is None:
        return ""
    delta = datetime.now(timezone.utc) - created.astimezone(timezone.utc)
    seconds = max(0, int(delta.total_seconds()))
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 48:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _live_prediction_for_fixture(fixture_id: int) -> MatchPrediction | None:
    """In-session live prediction if user ran Predict on this fixture."""
    try:
        cache = st.session_state.get("match_center_action_cache", {}).get(str(int(fixture_id)), {})
        pred_result = cache.get("predict")
        if pred_result and getattr(pred_result, "success", False):
            p = getattr(pred_result, "prediction", None)
            if p and int(getattr(p, "fixture_id", 0)) == int(fixture_id):
                return p
        last = st.session_state.get("gui_last_prediction")
        if last and getattr(last, "success", False):
            p = getattr(last, "prediction", None)
            if p and int(getattr(p, "fixture_id", 0)) == int(fixture_id):
                return p
    except Exception:
        pass
    return None


def _minimal_prediction_from_stored(stored: StoredPredictionView) -> MatchPrediction:
    """Rebuild a lightweight MatchPrediction so extended markets can be computed for old saves."""
    from worldcup_predictor.domain.prediction import (
        ConfidenceLevel,
        FirstGoalPrediction,
        HalftimePrediction,
        MarketPrediction,
        MatchPrediction,
        PredictionConfidenceBreakdown,
        ScorelineCandidate,
    )

    home, away = stored.home_team, stored.away_team
    dq = stored.data_quality_score
    if dq <= 1.0:
        dq *= 100.0
    candidates: list[ScorelineCandidate] = []
    if stored.predicted_scoreline:
        parts = stored.predicted_scoreline.replace(":", "-").split("-")
        if len(parts) == 2:
            try:
                candidates = [ScorelineCandidate(int(parts[0]), int(parts[1]), 0.22)]
            except ValueError:
                pass
    return MatchPrediction(
        fixture_id=stored.fixture_id,
        competition_key="world_cup_2026",
        match_name=f"{home} vs {away}",
        one_x_two=MarketPrediction("1x2", stored.predicted_1x2, stored.confidence_score / 100.0),
        over_under=MarketPrediction("over_under_2_5", stored.predicted_over_under, 0.55),
        halftime=HalftimePrediction(estimated_total_goals=1.05),
        first_goal=FirstGoalPrediction(
            team=stored.predicted_first_goal_team or home,
            player=stored.predicted_first_goal_scorer,
            minute_range="16-30",
        ),
        confidence_score=stored.confidence_score,
        confidence_level=ConfidenceLevel.MEDIUM,
        confidence_breakdown=PredictionConfidenceBreakdown(
            form_score=50.0,
            h2h_score=50.0,
            injuries_score=50.0,
            lineups_score=50.0,
            odds_score=50.0,
            data_quality_score=dq,
            total=stored.confidence_score,
        ),
        risk_level="medium",
        scoreline_candidates=candidates,
        is_placeholder=False,
        metadata={"extended_markets": stored.extended_markets_json or ""},
    )


def _load_extended_snapshot(
    stored: StoredPredictionView,
    live_prediction: MatchPrediction | None = None,
) -> Any | None:
    from worldcup_predictor.prediction.extended_markets import (
        ExtendedMarketsSnapshot,
        FirstGoalTimeEstimate,
        GoalscorerPick,
        ThreeWayProbabilities,
        TwoWayProbabilities,
        build_extended_markets,
        load_extended_markets_from_prediction,
    )

    if live_prediction is not None:
        try:
            return load_extended_markets_from_prediction(live_prediction) or build_extended_markets(
                live_prediction, None
            )
        except Exception:
            pass
    raw = stored.extended_markets_json
    if raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
            return ExtendedMarketsSnapshot(
                full_time_1x2=ThreeWayProbabilities(**(data.get("full_time_1x2") or {})),
                over_under_2_5=TwoWayProbabilities(**(data.get("over_under_2_5") or {})),
                btts=TwoWayProbabilities(**(data.get("btts") or {})),
                halftime_1x2=ThreeWayProbabilities(**(data.get("halftime_1x2") or {})),
                first_goal_time=FirstGoalTimeEstimate(**(data.get("first_goal_time") or {})),
                top_scorer=GoalscorerPick(**(data.get("top_scorer") or {})),
                home_scorer=GoalscorerPick(**(data.get("home_scorer") or {})),
                away_scorer=GoalscorerPick(**(data.get("away_scorer") or {})),
                correct_scores=list(data.get("correct_scores") or []),
                confidence_score=float(data.get("confidence_score") or 0),
                data_quality_score=float(data.get("data_quality_score") or 0),
                has_player_data=bool(data.get("has_player_data")),
            )
        except Exception:
            pass
    try:
        rebuilt = _minimal_prediction_from_stored(stored)
        return build_extended_markets(rebuilt, None)
    except Exception:
        pass
    return None


def _ht_pick_label(ht: Any, home: str, away: str, locale: Locale) -> str:
    if ht is None:
        return "—"
    try:
        probs = ht.as_percent()
        best = max(probs, key=probs.get)
        pct = probs[best]
        if best == "home":
            return f"{home} {pct:.0f}%"
        if best == "away":
            return f"{away} {pct:.0f}%"
        return f"{gui_t('markets.draw', locale)} {pct:.0f}%"
    except Exception:
        return "—"


def _scorer_display(snap: Any, stored: StoredPredictionView, locale: Locale) -> str:
    fallback = gui_t("markets.not_enough_player_data", locale)
    if snap is not None:
        try:
            if is_reliable_player_name(getattr(snap.top_scorer, "player", None)):
                name = str(snap.top_scorer.player)
                team = snap.top_scorer.team
                return f"{name} ({team})" if team else name
            if snap.has_player_data:
                for pick in (snap.home_scorer, snap.away_scorer):
                    if is_reliable_player_name(getattr(pick, "player", None)):
                        name = str(pick.player)
                        team = pick.team
                        return f"{name} ({team})" if team else name
        except Exception:
            pass
    if is_reliable_player_name(stored.predicted_first_goal_scorer):
        return str(stored.predicted_first_goal_scorer)
    return fallback


def _ou_confidence(snap: Any | None, stored: StoredPredictionView) -> str:
    if snap is None:
        return "—"
    try:
        sel = (stored.predicted_over_under or "").lower()
        a, b = snap.over_under_2_5.as_percent()
        pct = a if "over" in sel else b
        return f"{pct:.0f}%"
    except Exception:
        return "—"


def _score_confidence(snap: Any | None, stored: StoredPredictionView) -> str:
    if snap is None or not stored.predicted_scoreline:
        return "—"
    try:
        target = stored.predicted_scoreline.replace(":", "-")
        for row in snap.correct_scores or []:
            if str(row.get("label", "")).replace(":", "-") == target:
                return f"{float(row.get('probability', 0)):.0f}%"
        if snap.correct_scores:
            return f"{float(snap.correct_scores[0].get('probability', 0)):.0f}%"
    except Exception:
        pass
    return "—"


def _market_grid_cells(
    stored: StoredPredictionView,
    snap: Any | None,
    *,
    home: str,
    away: str,
    locale: Locale,
    conf: str,
) -> list[tuple[str, str, str]]:
    """Label, value, confidence line for each prediction market card."""
    x2 = _format_1x2(stored.predicted_1x2, home, away)
    ou = _format_ou(stored.predicted_over_under)
    score = _format_scoreline(stored.predicted_scoreline)

    btts_val = "—"
    ht_val = "—"
    fg_val = gui_t("markets.fg_time_unavailable", locale)
    scorer_val = _scorer_display(None, stored, locale)
    ou_conf = "—"
    score_conf = "—"

    if snap is not None:
        try:
            yes_pct, no_pct = snap.btts.as_percent()
            btts_val = f"{gui_t('markets.yes', locale)} {yes_pct:.0f}% / {gui_t('markets.no', locale)} {no_pct:.0f}%"
            ht_val = _ht_pick_label(snap.halftime_1x2, home, away, locale)
            fg = snap.first_goal_time
            minute = fg.expected_minute
            band = fg.minute_band or "—"
            if minute and band not in {"—", ""}:
                fg_val = f"{gui_t('markets.minute_label', locale).format(minute=minute)} ({band})"
            elif band not in {"—", ""}:
                fg_val = str(band)
            scorer_val = _scorer_display(snap, stored, locale)
            ou_conf = _ou_confidence(snap, stored)
            score_conf = _score_confidence(snap, stored)
        except Exception:
            pass

    return [
        ("1X2", x2, f"{gui_t('stored.confidence', locale)} {conf}"),
        ("O/U 2.5", ou, f"{gui_t('stored.confidence', locale)} {ou_conf}"),
        (gui_t("markets.btts", locale), btts_val, ""),
        (gui_t("markets.ht_result", locale), ht_val, ""),
        (gui_t("markets.first_goal_time", locale), fg_val, ""),
        (gui_t("markets.likely_scorer", locale), scorer_val, ""),
        (gui_t("stored.correct_score", locale), score, f"{gui_t('stored.confidence', locale)} {score_conf}"),
    ]


def _render_market_grid_html(
    cells: list[tuple[str, str, str]],
    *,
    correctness: dict[str, bool | None] | None = None,
) -> str:
    parts: list[str] = ['<div class="stored-pred-grid stored-pred-grid-extended">']
    for label, value, meta in cells:
        safe_label = html.escape(str(label))
        safe_value = html.escape(str(value))
        safe_meta = html.escape(str(meta)) if meta else ""
        meta_html = f'<div class="stored-pred-conf">{safe_meta}</div>' if meta else ""
        cell_class = "stored-pred-cell"
        result_html = ""
        if correctness and label in correctness:
            verdict = correctness[label]
            if verdict is True:
                cell_class += " stored-pred-cell-correct"
                result_html = '<span class="stored-pred-verdict stored-pred-verdict-ok">✓</span>'
            elif verdict is False:
                cell_class += " stored-pred-cell-wrong"
                result_html = '<span class="stored-pred-verdict stored-pred-verdict-bad">✗</span>'
        parts.append(
            f'<div class="{cell_class}">'
            f'<div class="stored-pred-label">{safe_label}</div>'
            f'<div class="stored-pred-value">{safe_value}{result_html}</div>'
            f"{meta_html}"
            f"</div>"
        )
    parts.append("</div>")
    return "".join(parts)


def _format_1x2(selection: str, home: str, away: str) -> str:
    key = (selection or "").lower().replace(" ", "_")
    if key == "home_win":
        return f"{home} Win"
    if key == "away_win":
        return f"{away} Win"
    if key == "draw":
        return "Draw"
    return selection.replace("_", " ").title()


def _format_ou(selection: str) -> str:
    key = (selection or "").lower().replace(" ", "_")
    if "over" in key:
        return "Over 2.5"
    if "under" in key:
        return "Under 2.5"
    return selection.replace("_", " ").title()


def _format_scoreline(value: str | None) -> str:
    if not value:
        return "—"
    return value.replace(":", "-")


def _version_label(version: str) -> str:
    return _VERSION_LABELS.get(version, version.replace("_", " "))


def _is_match_started(fixture: Any | None) -> bool:
    if fixture is None:
        return False
    status = getattr(fixture, "status", None) or ""
    bucket = classify_status(str(status))
    return bucket in {"live", "finished"}


def _outdated_warning(stored: StoredPredictionView, fixture: Any | None, locale: Locale) -> str | None:
    if _is_match_started(fixture):
        return None
    created = _parse_created_at(stored.created_at)
    if created is None:
        return None
    age_hours = (datetime.now(timezone.utc) - created.astimezone(timezone.utc)).total_seconds() / 3600
    if age_hours >= 12:
        return gui_t("stored.outdated", locale)
    return None


def _lineup_warning(stored: StoredPredictionView) -> str | None:
    if stored.is_preliminary or not stored.lineups_available:
        return "stored.lineups_changed"
    return None


def _result_badge(correct: bool | None) -> str:
    if correct is True:
        return "✅"
    if correct is False:
        return "❌"
    return "—"


def _evaluated_prediction(
    evaluation: EvaluatedPrediction | StoredPredictionEvaluation | None,
) -> EvaluatedPrediction | None:
    if evaluation is None:
        return None
    if isinstance(evaluation, StoredPredictionEvaluation):
        return evaluation.raw if evaluation.status == "evaluated" else None
    return evaluation


def _market_correctness(
    ev: EvaluatedPrediction,
    snap: Any | None,
    locale: Locale,
) -> dict[str, bool | None]:
    """Map market grid labels to correct / wrong / not evaluated."""
    mapping: dict[str, bool | None] = {
        "1X2": ev.one_x_two_correct,
        "O/U 2.5": ev.over_under_correct,
        gui_t("stored.correct_score", locale): (
            ev.scoreline_exact_correct if ev.predicted_scoreline else None
        ),
    }
    if ev.halftime_evaluated:
        mapping[gui_t("markets.ht_result", locale)] = ev.halftime_bucket_correct
    if ev.first_goal_evaluated and not ev.first_goal_skipped:
        mapping[gui_t("markets.likely_scorer", locale)] = ev.first_goal_correct

    if ev.final_score and "-" in str(ev.final_score):
        try:
            home_g, away_g = [int(x.strip()) for x in str(ev.final_score).split("-", 1)]
            actual_btts = home_g > 0 and away_g > 0
            if snap is not None:
                yes_pct, no_pct = snap.btts.as_percent()
                pred_yes = yes_pct >= no_pct
                mapping[gui_t("markets.btts", locale)] = pred_yes == actual_btts
        except (TypeError, ValueError):
            pass
    return mapping


def _evaluation_rows(
    evaluation: EvaluatedPrediction,
) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    rows.append(
        (
            "1X2",
            _format_1x2(evaluation.predicted_1x2, evaluation.home_team, evaluation.away_team),
            evaluation.actual_1x2.replace("_", " ").title(),
            _result_badge(evaluation.one_x_two_correct),
        )
    )
    rows.append(
        (
            "O/U 2.5",
            _format_ou(evaluation.predicted_over_under),
            evaluation.actual_over_under.replace("_", " ").title(),
            _result_badge(evaluation.over_under_correct),
        )
    )
    if evaluation.predicted_scoreline or evaluation.actual_scoreline:
        rows.append(
            (
                "Scoreline",
                _format_scoreline(evaluation.predicted_scoreline),
                _format_scoreline(evaluation.actual_scoreline),
                _result_badge(evaluation.scoreline_exact_correct),
            )
        )
    if evaluation.first_goal_evaluated and not evaluation.first_goal_skipped:
        rows.append(
            (
                "First goal",
                evaluation.predicted_first_goal_team or "—",
                evaluation.actual_first_goal_team or "—",
                _result_badge(evaluation.first_goal_correct),
            )
        )
    return rows


def _stored_to_record(stored: StoredPredictionView | dict[str, Any]) -> PredictionHistoryRecord:
    """Build PredictionHistoryRecord from StoredPredictionView or dict."""
    if isinstance(stored, StoredPredictionView):
        return PredictionHistoryRecord(
            fixture_id=stored.fixture_id,
            date="",
            home_team=stored.home_team,
            away_team=stored.away_team,
            predicted_1x2=stored.predicted_1x2,
            predicted_over_under_2_5=stored.predicted_over_under,
            predicted_halftime_goals=0.0,
            predicted_first_goal_team=stored.predicted_first_goal_team or "",
            confidence_score=stored.confidence_score,
            risk_level="medium",
            no_bet_flag=False,
            data_quality_score=stored.data_quality_score,
            source=stored.source,
            created_at=stored.created_at,
            predicted_scoreline=stored.predicted_scoreline,
        )
    return PredictionHistoryRecord(
        fixture_id=int(obj_get(stored, "fixture_id", 0)),
        date=str(obj_get(stored, "date", "")),
        home_team=str(obj_get(stored, "home_team", "")),
        away_team=str(obj_get(stored, "away_team", "")),
        predicted_1x2=str(obj_get(stored, "predicted_1x2", "draw")),
        predicted_over_under_2_5=str(
            obj_get(stored, "predicted_over_under_2_5", obj_get(stored, "predicted_over_under", "under_2_5"))
        ),
        predicted_halftime_goals=float(obj_get(stored, "predicted_halftime_goals", 0.0) or 0.0),
        predicted_first_goal_team=str(obj_get(stored, "predicted_first_goal_team", "")),
        confidence_score=float(obj_get(stored, "confidence_score", 0) or 0),
        risk_level=str(obj_get(stored, "risk_level", "medium")),
        no_bet_flag=bool(obj_get(stored, "no_bet_flag", False)),
        data_quality_score=float(obj_get(stored, "data_quality_score", 0) or 0),
        source=str(obj_get(stored, "source", "stored")),
        created_at=str(obj_get(stored, "created_at", "")),
        predicted_scoreline=obj_get(stored, "predicted_scoreline"),
    )


def _local_evaluate(stored: StoredPredictionView, fixture: Any) -> EvaluatedPrediction | None:
    """Fallback evaluator — read-only, no API calls."""
    home_goals = obj_get(fixture, "home_goals")
    away_goals = obj_get(fixture, "away_goals")
    if home_goals is None or away_goals is None:
        return None
    try:
        home = int(home_goals)
        away = int(away_goals)
    except (TypeError, ValueError):
        return None

    if home > away:
        actual_x2 = "home_win"
    elif home < away:
        actual_x2 = "away_win"
    else:
        actual_x2 = "draw"
    actual_ou = "over_2_5" if (home + away) > 2 else "under_2_5"
    actual_scoreline = f"{home}-{away}"

    pred_x2 = str(stored.predicted_1x2 or "").lower().replace(" ", "_")
    pred_ou = str(stored.predicted_over_under or "").lower().replace(" ", "_")
    pred_sl = (stored.predicted_scoreline or "").replace(":", "-").strip() or None

    goal_scorers = obj_get(fixture, "goal_scorers") or []
    actual_fg: str | None = None
    if goal_scorers and isinstance(goal_scorers, list):
        first = str(goal_scorers[0])
        if "(" in first and ")" in first:
            team_name = first.split("(")[-1].rstrip(")").strip()
            if team_name.lower() == stored.home_team.lower():
                actual_fg = stored.home_team
            elif team_name.lower() == stored.away_team.lower():
                actual_fg = stored.away_team
            else:
                actual_fg = team_name

    fg_correct: bool | None = None
    fg_evaluated = bool(stored.predicted_first_goal_team) and actual_fg is not None
    if fg_evaluated:
        fg_correct = stored.predicted_first_goal_team.lower() == actual_fg.lower()

    scoreline_correct: bool | None = None
    if pred_sl:
        scoreline_correct = pred_sl == actual_scoreline

    return EvaluatedPrediction(
        fixture_id=stored.fixture_id,
        match_name=f"{stored.home_team} vs {stored.away_team}",
        date="",
        home_team=stored.home_team,
        away_team=stored.away_team,
        predicted_1x2=stored.predicted_1x2,
        actual_1x2=actual_x2,
        one_x_two_correct=pred_x2 == actual_x2,
        predicted_over_under=stored.predicted_over_under,
        actual_over_under=actual_ou,
        over_under_correct=pred_ou == actual_ou,
        predicted_halftime_bucket=None,
        actual_halftime_bucket=None,
        halftime_bucket_correct=None,
        halftime_evaluated=False,
        first_goal_skipped=not fg_evaluated,
        confidence_score=stored.confidence_score,
        no_bet_flag=False,
        data_quality_score=stored.data_quality_score,
        source=stored.source,
        prediction_created_at=stored.created_at,
        evaluated_at=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
        final_score=actual_scoreline,
        predicted_scoreline=pred_sl,
        actual_scoreline=actual_scoreline,
        scoreline_exact_correct=scoreline_correct,
        predicted_first_goal_team=stored.predicted_first_goal_team,
        actual_first_goal_team=actual_fg,
        first_goal_correct=fg_correct,
        first_goal_evaluated=fg_evaluated,
    )


def evaluate_stored_prediction(
    fixture_id: int,
    fixture: Any,
) -> StoredPredictionEvaluation:
    """Evaluate stored prediction against fixture result — never raises."""
    try:
        status = classify_status(str(obj_get(fixture, "status", "") or ""))
        if status != "finished":
            return StoredPredictionEvaluation(status="pending", markets=[])

        stored = get_latest_stored_prediction(fixture_id)
        if stored is None:
            return StoredPredictionEvaluation(status="unavailable", markets=[])

        home_goals = obj_get(fixture, "home_goals")
        away_goals = obj_get(fixture, "away_goals")
        if home_goals is None or away_goals is None:
            return StoredPredictionEvaluation(status="unavailable", markets=[])

        record = _stored_to_record(stored)
        evaluated: EvaluatedPrediction | None = None

        if _evaluate_prediction is not None:
            try:
                evaluated = _evaluate_prediction(record, fixture)  # type: ignore[arg-type]
            except Exception:
                evaluated = None

        if evaluated is None:
            evaluated = _local_evaluate(stored, fixture)

        if evaluated is None:
            return StoredPredictionEvaluation(status="unavailable", markets=[])

        return StoredPredictionEvaluation(
            status="evaluated",
            markets=_evaluation_rows(evaluated),
            raw=evaluated,
        )
    except Exception:
        return StoredPredictionEvaluation(status="unavailable", markets=[])


def render_stored_prediction_summary(
    fixture_id: int,
    locale: Locale,
    *,
    compact: bool = False,
    fixture: Any | None = None,
    evaluation: EvaluatedPrediction | StoredPredictionEvaluation | None = None,
) -> bool:
    """Render summary card. Returns True if a stored prediction was shown."""
    stored = get_latest_stored_prediction(fixture_id)
    if stored is None:
        return False

    if evaluation is None and fixture is not None:
        try:
            evaluation = evaluate_stored_prediction(fixture_id, fixture)
        except Exception:
            evaluation = StoredPredictionEvaluation(status="unavailable", markets=[])

    home = obj_get(fixture, "home_team", None) or stored.home_team
    away = obj_get(fixture, "away_team", None) or stored.away_team
    updated = format_time_ago(stored.created_at)
    x2 = _format_1x2(stored.predicted_1x2, home, away)
    ou = _format_ou(stored.predicted_over_under)
    score = _format_scoreline(stored.predicted_scoreline)
    conf = f"{stored.confidence_score:.0f}/100"
    pq = stored.prediction_quality
    version = _version_label(stored.prediction_version)

    warnings: list[str] = []
    outdated = _outdated_warning(stored, fixture, locale)
    if outdated:
        warnings.append(outdated)
    lineup_key = _lineup_warning(stored)
    if lineup_key and not _is_match_started(fixture):
        warnings.append(gui_t(lineup_key, locale))

    eval_rows: list[tuple[str, str, str, str]] = []
    evaluated_raw = _evaluated_prediction(evaluation)
    if evaluation is not None:
        if isinstance(evaluation, StoredPredictionEvaluation):
            if evaluation.status == "evaluated":
                eval_rows = evaluation.markets
        elif isinstance(evaluation, EvaluatedPrediction):
            eval_rows = _evaluation_rows(evaluation)

    live_pred = _live_prediction_for_fixture(fixture_id)
    snap = _load_extended_snapshot(stored, live_pred)
    correctness = (
        _market_correctness(evaluated_raw, snap, locale) if evaluated_raw is not None else None
    )
    has_verdicts = bool(correctness and any(v is not None for v in correctness.values()))

    summary_class = "stored-prediction-summary"
    if compact:
        summary_class += " stored-prediction-compact"
    if has_verdicts:
        summary_class += " stored-prediction-evaluated"

    title_icon = "📊" if has_verdicts else "✅"
    final_score_html = ""
    if evaluated_raw and evaluated_raw.final_score:
        final_score_html = (
            f'<span class="stored-pred-final-score">'
            f'{gui_t("stored.actual_result", locale)}: {html.escape(evaluated_raw.final_score)}'
            f"</span>"
        )

    st.markdown(
        f"""
<div class="{summary_class}">
  <div class="stored-pred-header">
    <div class="stored-pred-title">{title_icon} {gui_t('stored.title', locale)}</div>
    <div class="stored-pred-meta">
      <span class="stored-pred-badge">{gui_t('card.prediction_stored', locale)}</span>
      {final_score_html}
      {f'<span class="stored-pred-updated">{gui_t("stored.updated", locale)}: {updated}</span>' if updated and not has_verdicts else ''}
    </div>
  </div>
""",
        unsafe_allow_html=True,
    )

    if eval_rows and not compact and not has_verdicts:
        for market, predicted, actual, badge in eval_rows:
            row_class = "stored-pred-eval-row"
            if badge == "✅":
                row_class += " stored-pred-eval-row-correct"
            elif badge == "❌":
                row_class += " stored-pred-eval-row-wrong"
            st.markdown(
                f"""
<div class="{row_class}">
  <span class="stored-pred-market">{market}</span>
  <span class="stored-pred-predicted">{predicted} {badge}</span>
  <span class="stored-pred-actual">{gui_t("stored.actual", locale)}: {actual}</span>
</div>
""",
                unsafe_allow_html=True,
            )
    else:
        cells = _market_grid_cells(stored, snap, home=home, away=away, locale=locale, conf=conf)
        if snap is not None and not stored.extended_markets_json and live_pred is None:
            st.caption(gui_t("stored.markets_estimated", locale))
        quality_html = ""
        if pq is not None and not compact and not has_verdicts:
            quality_html = (
                f'<div class="stored-pred-quality">'
                f'{gui_t("stored.prediction_quality", locale)}: {pq:.0f}/100</div>'
            )
        st.markdown(
            _render_market_grid_html(cells, correctness=correctness if has_verdicts else None)
            + quality_html
            + (
                f'<div class="stored-pred-version">{gui_t("stored.version", locale)}: {version}</div>'
                if not has_verdicts
                else ""
            ),
            unsafe_allow_html=True,
        )

    for warning in warnings:
        st.markdown(f'<div class="stored-pred-warning">⚠ {warning}</div>', unsafe_allow_html=True)

    if not compact:
        st.markdown(
            f'<div class="stored-pred-footer">{gui_t("stored.footer", locale)}</div>',
            unsafe_allow_html=True,
        )

    st.markdown("</div>", unsafe_allow_html=True)
    return True


def predict_button_label(fixture_id: int, locale: Locale) -> tuple[str, str, str]:
    """Return (label, button_type, help_text) for Predict / Refresh button."""
    if has_stored_prediction(fixture_id):
        return (
            gui_t("btn.refresh_prediction", locale),
            "primary",
            gui_t("stored.refresh_help", locale),
        )
    return (
        gui_t("btn.predict_match", locale),
        "primary",
        "",
    )
