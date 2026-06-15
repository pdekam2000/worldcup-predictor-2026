"""Read-only stored prediction summaries for match cards — Phase 34A."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

import streamlit as st

from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.accuracy.models import EvaluatedPrediction, PredictionHistoryRecord
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.database.repository import FootballIntelligenceRepository
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
    source: str = "stored"
    verifications: tuple[dict[str, str], ...] = ()

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
            source=record.source,
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
            source=str(pred.get("source") or "live"),
            verifications=verifications,
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

    st.markdown(
        f"""
<div class="stored-prediction-summary{' stored-prediction-compact' if compact else ''}">
  <div class="stored-pred-header">
    <div class="stored-pred-title">✅ {gui_t('stored.title', locale)}</div>
    <div class="stored-pred-meta">
      <span class="stored-pred-badge">{gui_t('card.prediction_stored', locale)}</span>
      {f'<span class="stored-pred-updated">{gui_t("stored.updated", locale)}: {updated}</span>' if updated else ''}
    </div>
  </div>
""",
        unsafe_allow_html=True,
    )

    eval_rows: list[tuple[str, str, str, str]] = []
    if evaluation is not None:
        if isinstance(evaluation, StoredPredictionEvaluation):
            if evaluation.status == "evaluated":
                eval_rows = evaluation.markets
        elif isinstance(evaluation, EvaluatedPrediction):
            eval_rows = _evaluation_rows(evaluation)

    if eval_rows and not compact:
        for market, predicted, actual, badge in eval_rows:
            st.markdown(
                f"""
<div class="stored-pred-eval-row">
  <span class="stored-pred-market">{market}</span>
  <span class="stored-pred-predicted">{predicted} {badge}</span>
  <span class="stored-pred-actual">Actual: {actual}</span>
</div>
""",
                unsafe_allow_html=True,
            )
    else:
        quality_html = ""
        if pq is not None and not compact:
            quality_html = (
                f'<div class="stored-pred-quality">'
                f'{gui_t("stored.prediction_quality", locale)}: {pq:.0f}/100</div>'
            )
        st.markdown(
            f"""
<div class="stored-pred-grid">
  <div class="stored-pred-cell">
    <div class="stored-pred-label">1X2</div>
    <div class="stored-pred-value">{x2}</div>
    <div class="stored-pred-conf">{gui_t('stored.confidence', locale)} {conf}</div>
  </div>
  <div class="stored-pred-cell">
    <div class="stored-pred-label">O/U 2.5</div>
    <div class="stored-pred-value">{ou}</div>
    <div class="stored-pred-conf">{gui_t('stored.confidence', locale)} —</div>
  </div>
  <div class="stored-pred-cell">
    <div class="stored-pred-label">{gui_t('stored.correct_score', locale)}</div>
    <div class="stored-pred-value">{score}</div>
    <div class="stored-pred-conf">{gui_t('stored.confidence', locale)} —</div>
  </div>
</div>
{quality_html}
<div class="stored-pred-version">{gui_t('stored.version', locale)}: {version}</div>
""",
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
