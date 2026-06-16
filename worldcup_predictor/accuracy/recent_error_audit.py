"""Recent verified-prediction error audit — diagnostics only, no weight mutation."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.accuracy.models import EvaluatedPrediction
from worldcup_predictor.accuracy.service import AccuracyTrackerService
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.domain.schedule import TournamentFixture
from worldcup_predictor.schedule.competition_schedule import create_schedule_service
from worldcup_predictor.schedule.match_center import build_match_center

MIN_SAMPLE_WARNING = 30
WINDOWS = (20, 50, 100)

_AGENT_KEYS = (
    "team_form_agent",
    "elo_team_strength_intelligence_agent",
    "xg_chance_quality_intelligence_agent",
    "sharp_money_intelligence_agent",
    "lineup_intelligence_agent",
    "lineup_agent",
    "injury_suspension_intelligence_agent",
    "injury_suspension_agent",
    "player_quality_agent",
    "market_consensus_agent",
    "tactics_agent",
)


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        text = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (TypeError, ValueError):
        return None


def _rate(correct: int, total: int) -> float | None:
    if total == 0:
        return None
    return round(correct / total, 4)


def _pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value * 100:.1f}%"


@dataclass
class MarketWindowStats:
    window: int
    available: int
    one_x_two: float | None = None
    one_x_two_n: int = 0
    over_under: float | None = None
    over_under_n: int = 0
    scoreline: float | None = None
    scoreline_n: int = 0
    first_goal_team: float | None = None
    first_goal_n: int = 0
    avg_confidence: float = 0.0
    calibration_gap: float | None = None


@dataclass
class BiasFindings:
    home_pick_rate: float | None = None
    away_pick_rate: float | None = None
    draw_pick_rate: float | None = None
    draw_actual_rate: float | None = None
    draw_missed: int = 0
    favorite_wrong: int = 0
    over_predicted: int = 0
    under_predicted: int = 0
    over_actual: int = 0
    under_actual: int = 0
    overconfidence_cases: list[dict[str, Any]] = field(default_factory=list)
    wrong_high_confidence: list[dict[str, Any]] = field(default_factory=list)
    repeated_patterns: list[str] = field(default_factory=list)


@dataclass
class AgentAttributionRow:
    agent_key: str
    label: str
    supported_wrong: int = 0
    warned_correctly: int = 0
    ignored_warnings: int = 0
    neutral_wrong: int = 0


@dataclass
class RecentErrorAuditReport:
    generated_at_utc: str
    competition_key: str
    total_verified: int
    sample_adequate: bool
    warnings: list[str] = field(default_factory=list)
    windows: list[MarketWindowStats] = field(default_factory=list)
    bias: BiasFindings = field(default_factory=BiasFindings)
    agent_attribution: list[AgentAttributionRow] = field(default_factory=list)
    root_causes: list[str] = field(default_factory=list)
    wrong_predictions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _sort_evaluated(items: list[EvaluatedPrediction]) -> list[EvaluatedPrediction]:
    def key(item: EvaluatedPrediction) -> datetime:
        ts = _parse_ts(item.evaluated_at) or _parse_ts(item.prediction_created_at)
        return ts or datetime.min.replace(tzinfo=timezone.utc)

    return sorted(items, key=key, reverse=True)


def _window_stats(items: list[EvaluatedPrediction], window: int) -> MarketWindowStats:
    slice_ = items[:window]
    n = len(slice_)
    stats = MarketWindowStats(window=window, available=n)
    if n == 0:
        return stats

    x2_ok = sum(1 for r in slice_ if r.one_x_two_correct)
    ou_ok = sum(1 for r in slice_ if r.over_under_correct)
    sl_eval = [r for r in slice_ if r.scoreline_exact_correct is not None]
    sl_ok = sum(1 for r in sl_eval if r.scoreline_exact_correct)
    fg_eval = [r for r in slice_ if r.first_goal_evaluated]
    fg_ok = sum(1 for r in fg_eval if r.first_goal_correct)

    stats.one_x_two = _rate(x2_ok, n)
    stats.one_x_two_n = n
    stats.over_under = _rate(ou_ok, n)
    stats.over_under_n = n
    stats.scoreline = _rate(sl_ok, len(sl_eval)) if sl_eval else None
    stats.scoreline_n = len(sl_eval)
    stats.first_goal_team = _rate(fg_ok, len(fg_eval)) if fg_eval else None
    stats.first_goal_n = len(fg_eval)
    stats.avg_confidence = round(sum(r.confidence_score for r in slice_) / n, 1)

    high = [r for r in slice_ if r.confidence_score >= 70]
    if high:
        hit = sum(1 for r in high if r.one_x_two_correct) / len(high)
        implied = sum(r.confidence_score for r in high) / len(high) / 100.0
        stats.calibration_gap = round(hit - implied, 4)
    return stats


def _analyze_bias(items: list[EvaluatedPrediction]) -> BiasFindings:
    bias = BiasFindings()
    if not items:
        return bias

    n = len(items)
    picks = Counter(r.predicted_1x2 for r in items)
    actuals = Counter(r.actual_1x2 for r in items)
    bias.home_pick_rate = round(picks.get("home_win", 0) / n, 4)
    bias.away_pick_rate = round(picks.get("away_win", 0) / n, 4)
    bias.draw_pick_rate = round(picks.get("draw", 0) / n, 4)
    bias.draw_actual_rate = round(actuals.get("draw", 0) / n, 4)
    bias.draw_missed = sum(
        1 for r in items if r.actual_1x2 == "draw" and r.predicted_1x2 != "draw"
    )
    bias.favorite_wrong = sum(
        1
        for r in items
        if not r.one_x_two_correct
        and r.predicted_1x2 in {"home_win", "away_win"}
        and r.confidence_score >= 65
    )

    bias.over_predicted = sum(1 for r in items if r.predicted_over_under == "over_2_5")
    bias.under_predicted = sum(1 for r in items if r.predicted_over_under == "under_2_5")
    bias.over_actual = sum(1 for r in items if r.actual_over_under == "over_2_5")
    bias.under_actual = sum(1 for r in items if r.actual_over_under == "under_2_5")

    for r in items:
        if r.confidence_score >= 70 and not r.one_x_two_correct:
            bias.wrong_high_confidence.append(
                {
                    "fixture_id": r.fixture_id,
                    "match": r.match_name,
                    "confidence": r.confidence_score,
                    "predicted": r.predicted_1x2,
                    "actual": r.actual_1x2,
                }
            )
        if r.confidence_score >= 75:
            implied = r.confidence_score / 100.0
            hit = 1.0 if r.one_x_two_correct else 0.0
            if hit < implied - 0.15:
                bias.overconfidence_cases.append(
                    {
                        "fixture_id": r.fixture_id,
                        "match": r.match_name,
                        "confidence": r.confidence_score,
                        "gap": round(hit - implied, 3),
                    }
                )

    patterns: list[str] = []
    if bias.draw_missed >= 2 and (bias.draw_actual_rate or 0) > (bias.draw_pick_rate or 0) + 0.1:
        patterns.append("Draw underprediction — model picks side winner when result was draw.")
    if bias.favorite_wrong >= 2:
        patterns.append("Strong favorite lean wrong — high-confidence 1X2 misses.")
    ou_bias = (bias.over_predicted / n) - (bias.over_actual / n) if n else 0
    if ou_bias > 0.15:
        patterns.append("Over 2.5 bias — model leans over more than results support.")
    elif ou_bias < -0.15:
        patterns.append("Under 2.5 bias — model leans under more than results support.")
    if len(bias.overconfidence_cases) >= 2:
        patterns.append("Overconfidence — stated confidence exceeds recent hit rate in high band.")
    bias.repeated_patterns = patterns
    return bias


def _load_learning_by_fixture(competition_key: str) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    try:
        from worldcup_predictor.database.repository import FootballIntelligenceRepository

        repo = FootballIntelligenceRepository()
        rows = repo.fetch_learning_records_v2(competition_key=competition_key, limit=5000)
        if hasattr(repo, "close"):
            repo.close()
        for row in rows:
            fid = int(row.get("fixture_id") or 0)
            payload = row.get("payload") or {}
            out[fid] = payload
    except Exception:
        pass
    return out


def _actual_side_label(actual: str) -> str:
    if actual == "home_win":
        return "home"
    if actual == "away_win":
        return "away"
    if actual == "draw":
        return "draw"
    return "neutral"


def _predicted_side_label(predicted: str) -> str:
    return _actual_side_label(predicted)


def _attribute_agents(
    wrong_x2: list[EvaluatedPrediction],
    learning: dict[int, dict[str, Any]],
) -> list[AgentAttributionRow]:
    rows = {k: AgentAttributionRow(agent_key=k, label=k) for k in _AGENT_KEYS}
    labels = {
        "team_form_agent": "Form",
        "elo_team_strength_intelligence_agent": "ELO",
        "xg_chance_quality_intelligence_agent": "xG",
        "sharp_money_intelligence_agent": "Sharp Money",
        "lineup_intelligence_agent": "Lineup",
        "lineup_agent": "Lineup",
        "injury_suspension_intelligence_agent": "Injury",
        "injury_suspension_agent": "Injury",
        "player_quality_agent": "Player Quality",
        "market_consensus_agent": "Market",
        "tactics_agent": "Tactics",
    }
    for key, row in rows.items():
        row.label = labels.get(key, key)

    for ev in wrong_x2:
        payload = learning.get(ev.fixture_id) or {}
        specialists = payload.get("specialists") or {}
        actual_side = _actual_side_label(ev.actual_1x2)
        predicted_side = _predicted_side_label(ev.predicted_1x2)
        fusion = payload.get("fusion") or {}
        for agent_key, info in specialists.items():
            if agent_key not in rows:
                continue
            lean = (info.get("lean") or "neutral").lower()
            row = rows[agent_key]
            if lean == predicted_side and lean != "neutral":
                row.supported_wrong += 1
            elif lean == actual_side and lean != "neutral":
                row.warned_correctly += 1
            elif lean == "neutral":
                row.neutral_wrong += 1
            elif lean not in {predicted_side, actual_side, "neutral"}:
                row.ignored_warnings += 1

        if fusion.get("risk_flags"):
            fg_key = "fusion"
            if fg_key not in rows:
                rows[fg_key] = AgentAttributionRow(agent_key=fg_key, label="Fusion")
            if any("conflict" in str(f).lower() for f in fusion["risk_flags"]):
                rows[fg_key].warned_correctly += 1

    return sorted(rows.values(), key=lambda r: r.supported_wrong, reverse=True)


def _infer_root_causes(
    bias: BiasFindings,
    windows: list[MarketWindowStats],
    agents: list[AgentAttributionRow],
    total: int,
) -> list[str]:
    causes: list[str] = []
    if total < MIN_SAMPLE_WARNING:
        causes.append(f"Small verified sample ({total}) — treat all findings as exploratory.")
    w20 = next((w for w in windows if w.window == 20), None)
    if w20 and w20.calibration_gap is not None and w20.calibration_gap < -0.12:
        causes.append("High-confidence band overstates 1X2 hit rate — apply confidence correction.")
    if bias.draw_missed >= 2:
        causes.append("Draw outcomes missed — increase draw awareness in balanced matches.")
    if bias.favorite_wrong >= 2:
        causes.append("Confident favorite picks failing — avoid forcing win in close ELO/form matches.")
    top_wrong = [a for a in agents if a.supported_wrong >= 2][:3]
    for a in top_wrong:
        causes.append(f"Agent '{a.label}' supported wrong 1X2 side on {a.supported_wrong} miss(es).")
    top_warn = [a for a in agents if a.warned_correctly >= 2][:2]
    for a in top_warn:
        causes.append(f"Agent '{a.label}' leaned correctly on {a.warned_correctly} miss(es) — may be under-weighted.")
    if not causes and total > 0:
        causes.append("No dominant error pattern — maintain conservative calibration only.")
    return causes


def load_verified_evaluated(
    fixtures: list[TournamentFixture],
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> list[EvaluatedPrediction]:
    service = AccuracyTrackerService(settings or get_settings(), competition_key=competition_key)
    snapshot = service.refresh(fixtures)
    return _sort_evaluated(list(snapshot.evaluated))


def build_recent_error_audit(
    fixtures: list[TournamentFixture],
    *,
    competition_key: str = "world_cup_2026",
    settings: Settings | None = None,
) -> RecentErrorAuditReport:
    evaluated = load_verified_evaluated(fixtures, settings=settings, competition_key=competition_key)
    total = len(evaluated)
    warnings: list[str] = []
    if total == 0:
        warnings.append("No verified finished predictions — run predictions before kickoff, then refresh accuracy.")
    elif total < MIN_SAMPLE_WARNING:
        warnings.append(
            f"Only {total} verified match(es) — minimum {MIN_SAMPLE_WARNING} recommended before tuning."
        )

    windows = [_window_stats(evaluated, w) for w in WINDOWS if w <= max(total, 20) or w == 20]
    if total > 0 and total < 20:
        windows = [_window_stats(evaluated, total)]

    bias = _analyze_bias(evaluated[: min(total, 100)])
    wrong_x2 = [r for r in evaluated[:100] if not r.one_x_two_correct]
    learning = _load_learning_by_fixture(competition_key)
    agents = _attribute_agents(wrong_x2, learning)

    wrong_rows = [
        {
            "fixture_id": r.fixture_id,
            "match": r.match_name,
            "score": r.final_score,
            "predicted_1x2": r.predicted_1x2,
            "actual_1x2": r.actual_1x2,
            "predicted_ou": r.predicted_over_under,
            "actual_ou": r.actual_over_under,
            "confidence": r.confidence_score,
            "1x2_ok": r.one_x_two_correct,
            "ou_ok": r.over_under_correct,
        }
        for r in evaluated[:20]
    ]

    report = RecentErrorAuditReport(
        generated_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        competition_key=competition_key,
        total_verified=total,
        sample_adequate=total >= MIN_SAMPLE_WARNING,
        warnings=warnings,
        windows=windows,
        bias=bias,
        agent_attribution=agents,
        root_causes=_infer_root_causes(bias, windows, agents, total),
        wrong_predictions=wrong_rows,
    )
    return report


def write_recent_error_audit_markdown(report: RecentErrorAuditReport, path: Path | None = None) -> Path:
    target = path or Path("reports/recent_prediction_error_audit.md")
    target.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Recent Prediction Error Audit",
        "",
        f"Generated: {report.generated_at_utc}",
        f"**Competition:** `{report.competition_key}`",
        f"**Verified predictions:** {report.total_verified}",
        f"**Sample adequate (≥{MIN_SAMPLE_WARNING}):** {report.sample_adequate}",
        "",
    ]
    for w in report.warnings:
        lines.append(f"> ⚠ {w}")
    if report.warnings:
        lines.append("")

    lines.extend(["## Window accuracy", "", "| Window | 1X2 | O/U 2.5 | Scoreline | FG team | Avg conf | Cal. gap |", "| --- | --- | --- | --- | --- | ---: | ---: |"])
    for w in report.windows:
        lines.append(
            f"| Last {w.available} (≤{w.window}) | {_pct(w.one_x_two)} ({w.one_x_two_n}) | "
            f"{_pct(w.over_under)} ({w.over_under_n}) | {_pct(w.scoreline)} ({w.scoreline_n}) | "
            f"{_pct(w.first_goal_team)} ({w.first_goal_n}) | {w.avg_confidence:.0f} | "
            f"{w.calibration_gap if w.calibration_gap is not None else '—'} |"
        )

    b = report.bias
    lines.extend(
        [
            "",
            "## Bias & pattern findings",
            "",
            f"- Home pick rate: {_pct(b.home_pick_rate)} · Away: {_pct(b.away_pick_rate)} · Draw pick: {_pct(b.draw_pick_rate)}",
            f"- Draw actual rate: {_pct(b.draw_actual_rate)} · Draw missed: {b.draw_missed}",
            f"- High-confidence favorite wrong: {b.favorite_wrong}",
            f"- O/U picks — Over: {b.over_predicted} / Under: {b.under_predicted} · Actual Over: {b.over_actual} / Under: {b.under_actual}",
            "",
        ]
    )
    if b.repeated_patterns:
        lines.append("**Repeated patterns:**")
        for p in b.repeated_patterns:
            lines.append(f"- {p}")
        lines.append("")

    if b.wrong_high_confidence:
        lines.append("## Wrong strong predictions (confidence ≥ 70)")
        lines.append("")
        for row in b.wrong_high_confidence[:10]:
            lines.append(
                f"- {row['match']} — conf {row['confidence']:.0f}, "
                f"pred {row['predicted']} vs actual {row['actual']}"
            )
        lines.append("")

    lines.extend(["## Agent error attribution (wrong 1X2)", "", "| Agent | Supported wrong | Warned correctly | Ignored | Neutral |", "| --- | ---: | ---: | ---: | ---: |"])
    for a in report.agent_attribution:
        if a.supported_wrong or a.warned_correctly or a.ignored_warnings:
            lines.append(
                f"| {a.label} | {a.supported_wrong} | {a.warned_correctly} | {a.ignored_warnings} | {a.neutral_wrong} |"
            )

    lines.extend(["", "## Root causes", ""])
    for c in report.root_causes:
        lines.append(f"- {c}")

    lines.extend(["", "## Policy", "", "- Recommendations only — no automatic agent weight changes.", "- Prediction history preserved.", ""])
    target.write_text("\n".join(lines), encoding="utf-8")
    return target


def replay_recent_predictions(
    fixtures: list[TournamentFixture],
    *,
    limit: int = 50,
    competition_key: str = "world_cup_2026",
) -> list[dict[str, Any]]:
    """Diagnostic replay — does not rewrite stored predictions."""
    store = PredictionHistoryStore()
    fixture_map = {int(getattr(f, "fixture_id", 0) or getattr(f, "id", 0)): f for f in fixtures}
    latest = store.latest_by_fixture()
    rows: list[dict[str, Any]] = []
    for fid, record in sorted(latest.items(), key=lambda x: x[1].created_at, reverse=True)[:limit]:
        fx = fixture_map.get(int(fid))
        if fx is None:
            continue
        from worldcup_predictor.accuracy.evaluator import evaluate_prediction

        ev = evaluate_prediction(record, fx)
        if ev is None:
            continue
        rows.append(
            {
                "fixture_id": ev.fixture_id,
                "match": ev.match_name,
                "finished": True,
                "1x2_ok": ev.one_x_two_correct,
                "ou_ok": ev.over_under_correct,
                "confidence": ev.confidence_score,
            }
        )
    return rows


def fetch_fixtures_for_audit(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
) -> list[TournamentFixture]:
    settings = settings or get_settings()
    schedule = create_schedule_service(settings, competition_key=competition_key)
    center = build_match_center(schedule, settings, enrich_live=False, enrich_finished_limit=100)
    return center.finished + center.live + center.upcoming
