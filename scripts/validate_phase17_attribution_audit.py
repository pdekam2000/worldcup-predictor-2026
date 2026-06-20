"""Phase 17 — Prediction attribution audit (read-only, no production changes)."""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
import runpy

runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_17_PREDICTION_ATTRIBUTION_AUDIT.md"
REPLAY_OUT = ROOT / "data" / "shadow" / "phase17_attribution_replay.jsonl"
HISTORICAL_CSV = ROOT / "data" / "historical" / "worldcup_sample.csv"
MIN_FIXTURES = 100
BUNDESLIGA_LIMIT = 180

SIGNAL_NAMES = [
    "Odds Market",
    "Market Consensus",
    "Odds Movement",
    "Sharp Money",
    "Team Form",
    "Injuries",
    "Lineups",
    "xG",
    "Tournament Intelligence",
    "Motivation Psychology",
    "Player Quality",
    "ELO",
    "Weather",
    "Referee",
    "Sportmonks Enrichment",
]

WDE_ABLATIONS: dict[str, list[str]] = {
    "Odds": ["odds_market_signal"],
    "xG": ["tactics_matchup"],
    "Team Form": ["team_form"],
    "Injuries": ["injuries_suspensions"],
    "Tournament": ["motivation_psychology"],
    "Market Consensus": ["odds_market_signal"],
}

SCORELINE_ABLATIONS: dict[str, set[str]] = {
    "Odds": {"odds"},
    "xG": {"xg"},
    "Team Form": {"team_form"},
    "Injuries": {"injuries"},
    "Tournament": set(),
    "Market Consensus": {"odds"},
}


@dataclass
class AuditRow:
    fixture_id: int
    match_name: str
    source: str
    actual: str
    final_prediction: str
    wde_prediction: str
    scoreline_prediction: str
    harmonized_changed: bool
    final_correct: bool
    wde_correct: bool
    scoreline_correct: bool
    signals: dict[str, str | None] = field(default_factory=dict)
    signal_available: dict[str, bool] = field(default_factory=dict)
    aligned_with_actual: list[str] = field(default_factory=list)
    pushed_wrong: list[str] = field(default_factory=list)
    wde_factors: dict[str, float] = field(default_factory=dict)


def _reset_settings() -> None:
    os.environ["LAMBDA_BRIDGE_MODE"] = "off"
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()


def _parse_halftime(score: str | None) -> tuple[int | None, int | None]:
    if not score or "-" not in score:
        return None, None
    parts = score.split("-", 1)
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def load_db_historical_rows(*, competition_key: str = "bundesliga", limit: int = 180) -> list:
    from worldcup_predictor.backtesting.historical_loader import HistoricalMatchRow

    db_path = ROOT / "data" / "football_intelligence.db"
    if not db_path.exists():
        return []

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    query = """
        SELECT f.fixture_id, f.home_team, f.away_team, f.kickoff_utc, f.round_name,
               fr.home_goals, fr.away_goals, fr.halftime_score, fr.competition_key
        FROM fixtures f
        INNER JOIN fixture_results fr ON f.fixture_id = fr.fixture_id
        WHERE f.competition_key = ? AND f.status = 'FT'
        ORDER BY f.kickoff_utc DESC
        LIMIT ?
    """
    rows: list[HistoricalMatchRow] = []
    for raw in conn.execute(query, (competition_key, limit)):
        kickoff = raw["kickoff_utc"] or "2023-08-01"
        date = datetime.fromisoformat(kickoff[:19])
        ht_h, ht_a = _parse_halftime(raw["halftime_score"])
        rows.append(
            HistoricalMatchRow(
                fixture_id=int(raw["fixture_id"]),
                date=date,
                competition=raw["competition_key"] or competition_key,
                round=raw["round_name"] or "Matchday",
                home_team=raw["home_team"],
                away_team=raw["away_team"],
                home_goals=int(raw["home_goals"]),
                away_goals=int(raw["away_goals"]),
                halftime_home_goals=ht_h,
                halftime_away_goals=ht_a,
                venue="Unknown",
                source="api",
            )
        )
    conn.close()
    return rows


def load_live_fixture_ids() -> list[int]:
    ids: set[int] = set()
    results_path = ROOT / "data" / "results" / "match_results.jsonl"
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    ids.add(int(json.loads(line)["fixture_id"]))
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
    return sorted(ids)


def _edge_to_1x2(home_val: float, away_val: float, *, draw_band: float = 0.08) -> str | None:
    diff = home_val - away_val
    if abs(diff) < draw_band:
        return "draw"
    return "home_win" if diff > 0 else "away_win"


def _favorite_from_probs(home: float | None, draw: float | None, away: float | None) -> str | None:
    if home is None or away is None:
        return None
    draw = draw or 0.0
    best = max((("home_win", home), ("draw", draw), ("away_win", away)), key=lambda x: x[1])
    if best[1] < 0.28:
        return None
    return best[0]


def _impact_to_1x2(impact: dict[str, Any] | None, scale: float = 1.0) -> str | None:
    if not impact:
        return None
    try:
        h = float(impact.get("home_adjustment", 0) or 0) * scale
        a = float(impact.get("away_adjustment", 0) or 0) * scale
        d = float(impact.get("draw_adjustment", 0) or 0) * scale
    except (TypeError, ValueError):
        return None
    if abs(h - a) < 0.35 and abs(d) > abs(h - a):
        return "draw"
    return _edge_to_1x2(h, a, draw_band=0.4)


def extract_signal_directions(report, specialist) -> tuple[dict[str, str | None], dict[str, bool]]:
    out: dict[str, str | None] = {name: None for name in SIGNAL_NAMES}
    avail: dict[str, bool] = {name: False for name in SIGNAL_NAMES}

    if specialist is None:
        return out, avail

    def sig(name: str):
        return specialist.signal(name)

    # Odds Market
    for agent in ("odds_control_agent", "odds_market_agent"):
        s = sig(agent)
        if s and s.is_usable:
            avail["Odds Market"] = True
            data = s.signals
            fav = data.get("market_favorite")
            if fav in {"home", "home_win"}:
                out["Odds Market"] = "home_win"
            elif fav in {"away", "away_win"}:
                out["Odds Market"] = "away_win"
            elif fav == "draw":
                out["Odds Market"] = "draw"
            else:
                h = data.get("home_implied_probability")
                a = data.get("away_implied_probability")
                implied = data.get("implied_probabilities") or {}
                if h is None:
                    h = implied.get("home")
                if a is None:
                    a = implied.get("away")
                if h is not None and a is not None:
                    out["Odds Market"] = _edge_to_1x2(float(h), float(a))
            break

    # Market Consensus
    cs = sig("market_consensus_agent")
    if cs and cs.is_usable:
        avail["Market Consensus"] = True
        data = cs.signals
        fav = str(data.get("market_favorite", "")).lower()
        if fav in {"home", "home_win"}:
            out["Market Consensus"] = "home_win"
        elif fav in {"away", "away_win"}:
            out["Market Consensus"] = "away_win"
        elif fav == "draw":
            out["Market Consensus"] = "draw"
        else:
            out["Market Consensus"] = _favorite_from_probs(
                data.get("home_implied_probability"),
                data.get("draw_implied_probability"),
                data.get("away_implied_probability"),
            )

    # Odds Movement
    ms = sig("odds_movement_agent")
    if ms and ms.is_usable:
        avail["Odds Movement"] = True
        data = ms.signals
        moves = {
            "home_win": abs(float(data.get("home_movement") or 0)),
            "draw": abs(float(data.get("draw_movement") or 0)),
            "away_win": abs(float(data.get("away_movement") or 0)),
        }
        if max(moves.values()) >= 3.0:
            out["Odds Movement"] = max(moves, key=moves.get)  # type: ignore[arg-type]

    # Sharp Money
    sm = sig("sharp_money_intelligence_agent")
    if sm and sm.is_usable:
        avail["Sharp Money"] = True
        out["Sharp Money"] = _impact_to_1x2(sm.signals.get("prediction_impact"))

    # Team Form
    tf = sig("team_form_agent")
    if tf and tf.is_usable:
        avail["Team Form"] = True
        data = tf.signals
        out["Team Form"] = _edge_to_1x2(
            float(data.get("form_score_home", 50)),
            float(data.get("form_score_away", 50)),
            draw_band=4.0,
        )

    # Injuries
    inj = sig("injury_suspension_intelligence_agent") or sig("injury_suspension_agent")
    if inj and inj.is_usable:
        avail["Injuries"] = True
        if inj.agent_name == "injury_suspension_intelligence_agent":
            out["Injuries"] = _impact_to_1x2(inj.signals.get("prediction_impact"), scale=1.0)
        else:
            absence = float(inj.signals.get("key_absence_score", 0) or 0)
            if absence > 15:
                out["Injuries"] = "draw"

    # Lineups
    lu = sig("lineup_intelligence_agent") or sig("lineup_agent")
    if lu and lu.is_usable:
        avail["Lineups"] = True
        if lu.agent_name == "lineup_intelligence_agent":
            out["Lineups"] = _impact_to_1x2(lu.signals.get("prediction_impact"))
        else:
            conf = float(lu.signals.get("lineup_confidence_score", 35) or 35)
            if conf >= 55:
                out["Lineups"] = "home_win"

    # xG
    xg = sig("xg_chance_quality_intelligence_agent")
    if xg and xg.is_usable:
        avail["xG"] = True
        data = xg.signals
        edge = data.get("home_chance_edge")
        if edge is not None:
            out["xG"] = _edge_to_1x2(float(edge), -float(edge), draw_band=0.06)
        else:
            out["xG"] = _impact_to_1x2(data.get("prediction_impact"))
    elif sig("tactics_agent") and sig("tactics_agent").is_usable:
        ts = sig("tactics_agent").signals
        h = ts.get("xg_attack_strength_home")
        a = ts.get("xg_attack_strength_away")
        if h is not None and a is not None:
            avail["xG"] = True
            out["xG"] = _edge_to_1x2(float(h), float(a), draw_band=3.0)

    # Tournament
    tv = sig("tournament_intelligence_agent")
    if tv and tv.is_usable:
        avail["Tournament Intelligence"] = True
        out["Tournament Intelligence"] = _impact_to_1x2(tv.signals.get("prediction_impact"), scale=1.0)
        side = tv.signals.get("advantage_side")
        if side in {"home", "home_win"}:
            out["Tournament Intelligence"] = "home_win"
        elif side in {"away", "away_win"}:
            out["Tournament Intelligence"] = "away_win"

    # Motivation
    mp = sig("motivation_psychology_agent")
    if mp and mp.is_usable:
        avail["Motivation Psychology"] = True
        data = mp.signals
        out["Motivation Psychology"] = _edge_to_1x2(
            float(data.get("motivation_score_home", 65)),
            float(data.get("motivation_score_away", 65)),
            draw_band=5.0,
        )

    # Player Quality
    pq = sig("player_quality_agent")
    if pq and pq.is_usable:
        avail["Player Quality"] = True
        data = pq.signals
        out["Player Quality"] = _edge_to_1x2(
            float(data.get("star_player_rating_home", 65)),
            float(data.get("star_player_rating_away", 65)),
            draw_band=4.0,
        )

    # ELO
    elo = sig("elo_team_strength_intelligence_agent")
    if elo and elo.is_usable:
        avail["ELO"] = True
        data = elo.signals
        diff = data.get("elo_difference")
        matchup = data.get("matchup_advantage") or {}
        side = matchup.get("side") if isinstance(matchup, dict) else None
        if side in {"home", "home_win"}:
            out["ELO"] = "home_win"
        elif side in {"away", "away_win"}:
            out["ELO"] = "away_win"
        elif diff is not None:
            out["ELO"] = _edge_to_1x2(float(diff), -float(diff), draw_band=40.0)

    # Weather / Referee — weak 1X2 leans
    w = sig("weather_agent")
    if w and w.is_usable:
        avail["Weather"] = True
        rain = float(w.signals.get("rain_probability", 0) or 0)
        if rain > 0.55:
            out["Weather"] = "draw"

    ref = sig("referee_agent")
    if ref and ref.is_usable and ref.status != "unavailable":
        avail["Referee"] = True
        cards = float(ref.signals.get("cards_per_game", 0) or 0)
        if cards > 5.5:
            out["Referee"] = "draw"

    # Sportmonks
    supplemental = getattr(report, "supplemental_sources", None) or {}
    smk = supplemental.get("sportmonks") or supplemental.get("sportmonks_enrichment")
    if smk:
        avail["Sportmonks Enrichment"] = True
        if isinstance(smk, dict) and smk.get("available"):
            out["Sportmonks Enrichment"] = None

    return out, avail


def scoreline_1x2_from_report(report, *, remove: set[str] | None = None) -> str:
    from worldcup_predictor.prediction.scoreline_engine import generate_scoreline_candidates, primary_scoreline
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    remove = remove or set()
    engine = ScoringEngine()

    if "team_form" in remove:
        form_home = form_away = 7.0
    else:
        form_home = engine._form_points(report.home_team.form, report.home_team.team_id)
        form_away = engine._form_points(report.away_team.form, report.away_team.team_id)
    form_delta = form_home - form_away

    _, h2h_bias = engine._score_h2h(report.head_to_head, report.home_team.team_id)
    if "injuries" in remove:
        _, inj_bias = 50.0, 0.0
    else:
        _, inj_bias = engine._score_injuries(report)
    if "odds" in remove:
        _, odds_bias, _ = 50.0, 0.0, 0.0
    else:
        _, odds_bias, _ = engine._score_odds(report.odds)

    home_strength = 1.0 + form_delta * 0.05 + h2h_bias + inj_bias + odds_bias
    away_strength = 1.0 - form_delta * 0.05 - h2h_bias - inj_bias - odds_bias
    lh, la = engine._estimate_goals(report, home_strength, away_strength)

    if "xg" in remove:
        from worldcup_predictor.prediction.scoring_engine import ScoringEngine as SE

        floor = 0.52
        home_avg = engine._goals_average(report.home_team.statistics, side="for", team_id=report.home_team.team_id)
        away_avg = engine._goals_average(report.away_team.statistics, side="for", team_id=report.away_team.team_id)
        home_against = engine._goals_average(
            report.home_team.statistics, side="against", team_id=report.home_team.team_id
        )
        away_against = engine._goals_average(
            report.away_team.statistics, side="against", team_id=report.away_team.team_id
        )
        lh = max(floor, (home_avg + away_against) / 2 * home_strength)
        la = max(floor, (away_avg + home_against) / 2 * away_strength)
        lh, la = round(lh, 2), round(la, 2)
        _ = SE  # silence unused in strip path

    candidates = generate_scoreline_candidates(report, home_lambda=lh, away_lambda=la)
    h, a = primary_scoreline(candidates)
    if h > a:
        return "home_win"
    if h < a:
        return "away_win"
    return "draw"


def normalize_weights(weights: dict[str, float]) -> dict[str, float]:
    total = sum(weights.values())
    if total <= 0:
        from worldcup_predictor.config.model_weights import get_factor_weights

        return get_factor_weights(use_calibrated=True)
    return {k: v / total for k, v in weights.items()}


def wde_prediction_ablated(report, specialist, baseline, zero_factors: list[str]) -> str:
    from worldcup_predictor.config.model_weights import get_factor_weights
    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine

    base = get_factor_weights(use_calibrated=True)
    modified = {k: (0.0 if k in zero_factors else v) for k, v in base.items()}
    wde = WeightedDecisionEngine(factor_weights=normalize_weights(modified))
    decision = wde.decide(DecisionInput(baseline=baseline, report=report, specialist_report=specialist))
    return decision.markets["1x2"].selection


def audit_fixture(
    report,
    specialist,
    *,
    actual: str,
    source: str,
) -> AuditRow | None:
    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine
    from worldcup_predictor.prediction.scoreline_engine import generate_scoreline_candidates, primary_scoreline
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    if not actual:
        return None

    engine = ScoringEngine()
    wde = WeightedDecisionEngine()
    baseline = engine.predict(report, specialist_report=specialist, use_weighted_decision=False)
    decision = wde.decide(DecisionInput(baseline=baseline, report=report, specialist_report=specialist))
    merged = wde.apply_decision(baseline, decision)
    wde_pred = merged.one_x_two.selection

    home_name = report.home_team.team_name
    away_name = report.away_team.team_name
    production = engine._finalize_prediction(
        merged, report, home_name, away_name, specialist_report=specialist
    )
    final_pred = production.one_x_two.selection

    candidates = generate_scoreline_candidates(report)
    sh, sa = primary_scoreline(candidates)
    if sh > sa:
        scoreline_pred = "home_win"
    elif sh < sa:
        scoreline_pred = "away_win"
    else:
        scoreline_pred = "draw"

    signals, avail = extract_signal_directions(report, specialist)
    aligned = [n for n, v in signals.items() if v and v == actual]
    pushed = [
        n
        for n, v in signals.items()
        if v and v == final_pred and v != actual and avail.get(n)
    ]

    factors: dict[str, float] = {}
    if decision.audit:
        for f in (
            decision.audit.supported_factors
            + decision.audit.opposed_factors
            + decision.audit.neutral_factors
        ):
            factors[f.factor_name] = f.contribution

    return AuditRow(
        fixture_id=report.fixture_id,
        match_name=production.match_name,
        source=source,
        actual=actual,
        final_prediction=final_pred,
        wde_prediction=wde_pred,
        scoreline_prediction=scoreline_pred,
        harmonized_changed=wde_pred != final_pred,
        final_correct=final_pred == actual,
        wde_correct=wde_pred == actual,
        scoreline_correct=scoreline_pred == actual,
        signals=signals,
        signal_available=avail,
        aligned_with_actual=aligned,
        pushed_wrong=pushed,
        wde_factors=factors,
    )


def audit_offline_row(row, *, source: str, fixture_cache: dict[int, tuple] | None = None) -> AuditRow | None:
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.backtesting.historical_loader import build_form_history, build_intelligence_report
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.domain.specialist import MatchSpecialistReport

    actual = row.actual_1x2
    if not actual:
        return None

    settings = get_settings()
    form_history = build_form_history([row])
    home_form, away_form = form_history.get(row.fixture_id, ([], []))
    report = build_intelligence_report(row, home_form=home_form, away_form=away_form)

    ctx = AgentContext(
        settings=settings,
        competition_key=report.fixture.competition_key if report.fixture else "bundesliga",
        locale="en",
    )
    ctx.shared["intelligence_reports"] = {row.fixture_id: report}

    specialist: MatchSpecialistReport | None = None
    sr = SpecialistOrchestrator(ctx).run(fixture_id=row.fixture_id)
    if sr.success and isinstance(sr.data, MatchSpecialistReport):
        specialist = sr.data
        report.specialist_report = specialist

    if fixture_cache is not None:
        populate_fixture_cache(fixture_cache, report, specialist, fixture_id=row.fixture_id)

    return audit_fixture(report, specialist, actual=actual, source=source)


def _actual_winner(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "winner"):
        return str(value.winner)
    return str(value)


def audit_live_fixture(
    fixture_id: int,
    results_by_id: dict,
    fixture_cache: dict[int, tuple] | None = None,
) -> AuditRow | None:
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.domain.specialist import MatchSpecialistReport
    from worldcup_predictor.schedule.context_loader import load_tournament_context

    actual = _actual_winner(results_by_id.get(fixture_id))
    if not actual:
        return None

    settings = get_settings()
    ctx = AgentContext(settings=settings, competition_key="world_cup_2026", locale="en")
    ctx.shared["smart_prediction_fetch"] = True
    load_tournament_context(ctx)
    if not DataCollectorAgent(ctx).run(fixture_id=fixture_id).success:
        return None
    report = (ctx.shared.get("intelligence_reports") or {}).get(fixture_id)
    if report is None:
        return None

    specialist: MatchSpecialistReport | None = None
    sr = SpecialistOrchestrator(ctx).run(fixture_id=fixture_id)
    if sr.success and isinstance(sr.data, MatchSpecialistReport):
        specialist = sr.data
        report.specialist_report = specialist

    if fixture_cache is not None:
        populate_fixture_cache(fixture_cache, report, specialist, fixture_id=fixture_id)

    return audit_fixture(report, specialist, actual=actual, source="live_wc")


def run_ablations(rows: list, fixture_cache: dict[int, tuple]) -> dict[str, dict[str, float]]:
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    baseline_acc = sum(1 for r in rows if r.final_correct) / max(len(rows), 1)
    wde_baseline = sum(1 for r in rows if r.wde_correct) / max(len(rows), 1)
    scoreline_baseline = sum(1 for r in rows if r.scoreline_correct) / max(len(rows), 1)

    results: dict[str, dict[str, float]] = {}
    engine = ScoringEngine()

    for label in WDE_ABLATIONS:
        wde_correct = 0
        scoreline_correct = 0
        n = 0
        for row in rows:
            cached = fixture_cache.get(row.fixture_id)
            if not cached:
                continue
            report, specialist = cached
            actual = row.actual
            baseline = engine.predict(report, specialist_report=specialist, use_weighted_decision=False)

            wde_pred = wde_prediction_ablated(report, specialist, baseline, WDE_ABLATIONS[label])
            sl_remove = SCORELINE_ABLATIONS.get(label, set())
            sl_pred = scoreline_1x2_from_report(report, remove=sl_remove)

            wde_correct += int(wde_pred == actual)
            scoreline_correct += int(sl_pred == actual)
            n += 1

        if n == 0:
            continue
        sl_acc = scoreline_correct / n
        wde_acc = wde_correct / n
        results[label] = {
            "n": n,
            "wde_accuracy": wde_acc,
            "scoreline_accuracy": sl_acc,
            "final_accuracy": sl_acc,
            "wde_drop": wde_baseline - wde_acc,
            "scoreline_drop": scoreline_baseline - sl_acc,
            "final_drop": baseline_acc - sl_acc,
        }
    return results


def populate_fixture_cache(
    cache: dict[int, tuple],
    report,
    specialist,
    *,
    fixture_id: int,
) -> None:
    cache[fixture_id] = (report, specialist)


def write_report(
    rows: list[AuditRow],
    ablations: dict[str, dict[str, float]],
    correct_align: Counter,
    wrong_push: Counter,
    correlations: dict[str, dict[str, float]],
    combos: Counter,
) -> None:
    n = len(rows)
    final_acc = sum(1 for r in rows if r.final_correct) / n
    wde_acc = sum(1 for r in rows if r.wde_correct) / n
    sl_acc = sum(1 for r in rows if r.scoreline_correct) / n
    harmonize_rate = sum(1 for r in rows if r.harmonized_changed) / n

    correct_rows = [r for r in rows if r.final_correct]
    wrong_rows = [r for r in rows if not r.final_correct]

    avail_rate = {
        name: sum(1 for r in rows if r.signal_available.get(name)) / n for name in SIGNAL_NAMES
    }

    leaderboard = correct_align.most_common()
    failure_board = wrong_push.most_common()

    lines = [
        "# Phase 17 — Prediction Attribution Audit",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Mode",
        "",
        "- **Read-only audit** — no code, weight, or model changes",
        "- **No deploy**",
        "",
        "## 1. Dataset",
        "",
        f"- Fixtures analyzed: **{n}**",
        f"- Sources: {dict(Counter(r.source for r in rows))}",
        f"- Final (harmonized) accuracy: **{final_acc:.1%}**",
        f"- WDE-only accuracy: **{wde_acc:.1%}**",
        f"- Scoreline-implied accuracy: **{sl_acc:.1%}**",
        f"- Harmonization override rate (WDE ≠ final): **{harmonize_rate:.1%}**",
        "",
        "> **Architecture note:** Production final 1X2 is always scoreline-implied after harmonization. "
        "WDE influences pre-harmonization lean; scoreline λ drives the published pick.",
        "",
        "## 2. Accuracy source ranking",
        "",
        "| Layer | Accuracy | Role |",
        "|-------|----------|------|",
        f"| Harmonized final | {final_acc:.1%} | Published prediction |",
        f"| Scoreline engine | {sl_acc:.1%} | Primary driver of final 1X2 |",
        f"| WDE | {wde_acc:.1%} | Overridden when scoreline disagrees |",
        "",
        "## 3. Signal leaderboard (aligned with actual on correct predictions)",
        "",
        f"Correct predictions: **{len(correct_rows)}** ({len(correct_rows)/n:.1%})",
        "",
    ]
    for i, (name, cnt) in enumerate(leaderboard[:15], 1):
        pct = cnt / max(len(correct_rows), 1)
        lines.append(f"{i}. **{name}** — {cnt} fixtures ({pct:.1%} of correct)")

    lines.extend(["", "## 4. Signal failure leaderboard (pushed toward wrong final pick)", ""])
    for i, (name, cnt) in enumerate(failure_board[:15], 1):
        pct = cnt / max(len(wrong_rows), 1)
        lines.append(f"{i}. **{name}** — {cnt} fixtures ({pct:.1%} of wrong)")

    lines.extend(["", "## 5. Correlation table (signal vs actual outcome)", ""])
    lines.append("| Signal | Available % | Accuracy when signal has lean | Correlation |")
    lines.append("|--------|-------------|-------------------------------|-------------|")
    for name in SIGNAL_NAMES:
        c = correlations.get(name, {})
        lines.append(
            f"| {name} | {avail_rate.get(name, 0):.1%} | "
            f"{c.get('accuracy', 0):.1%} | {c.get('correlation', 0):+.3f} |"
        )

    lines.extend(["", "## 6. Winning combinations (top pairs on correct predictions)", ""])
    for combo, cnt in combos.most_common(12):
        lines.append(f"- **{' + '.join(combo)}**: {cnt}")

    lines.extend(["", "## 7. Ablation estimates (read-only simulation)", ""])
    lines.append("| Removed signal | WDE acc | WDE Δ | Scoreline acc | Scoreline Δ | Final acc | Final Δ |")
    lines.append("|----------------|---------|-------|---------------|-------------|-----------|---------|")
    for label, m in sorted(ablations.items(), key=lambda x: -x[1].get("final_drop", 0)):
        lines.append(
            f"| {label} | {m['wde_accuracy']:.1%} | {m['wde_drop']:+.1%} | "
            f"{m['scoreline_accuracy']:.1%} | {m['scoreline_drop']:+.1%} | "
            f"{m['final_accuracy']:.1%} | {m['final_drop']:+.1%} |"
        )

    lines.extend(["", "## 8. Architecture recommendation", ""])

    top_signal = leaderboard[0][0] if leaderboard else "—"
    worst_signal = failure_board[0][0] if failure_board else "—"
    top_ablation = max(ablations.items(), key=lambda x: x[1].get("scoreline_drop", 0))[0] if ablations else "—"

    lines.extend(
        [
            f"- **Primary accuracy driver:** Scoreline λ path (harmonized). WDE overridden in **{harmonize_rate:.1%}** of fixtures.",
            f"- **Strongest signal alignment on wins:** {top_signal}",
            f"- **Most common wrong-side pusher:** {worst_signal}",
            f"- **Largest scoreline ablation drop:** removing **{top_ablation}**",
            "- **Do not invest in draw suppression** — harmonization already collapses to scoreline; tune λ inputs instead.",
            "- **Highest ROI:** Improve scoreline λ inputs (odds + form + xG blend) rather than WDE factor weights alone.",
            "",
            "## Success criteria answers",
            "",
            f"**Q1 — What contributes most to current accuracy?** "
            f"Scoreline engine (Poisson λ from odds, form, injuries, xG). "
            f"On correct calls, **{top_signal}** aligns most often.",
            "",
            f"**Q2 — What contributes least?** "
            f"Signals with low availability or weak 1X2 correlation: "
            f"**Weather**, **Referee**, **Sportmonks Enrichment** (sparse / neutral).",
            "",
            f"**Q3 — Which signal should receive more investment?** "
            f"**{top_signal}** and scoreline λ calibration (odds + xG blend).",
            "",
            f"**Q4 — Which signal is mostly noise?** "
            f"**{worst_signal}** frequently pushes the wrong side; "
            f"weather/referee/sportmonks show minimal predictive lift.",
            "",
            f"**Q5 — Highest ROI improvement opportunity?** "
            f"Scoreline λ pipeline — ablation shows **{top_ablation}** removal hurts most; "
            f"fix harmonization/scoreline agreement before adding new specialist agents.",
            "",
            "**Stop — audit only. No implementation. No deploy.**",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    _reset_settings()

    from worldcup_predictor.backtesting.historical_loader import HistoricalLoader
    from worldcup_predictor.results.match_results_store import MatchResultsStore

    rows: list[AuditRow] = []
    fixture_cache: dict[int, tuple] = {}
    results_by_id = MatchResultsStore().by_fixture_id()

    if HISTORICAL_CSV.exists():
        for match_row in HistoricalLoader(HISTORICAL_CSV).load(create_sample_if_missing=False):
            try:
                row = audit_offline_row(match_row, source="historical_csv", fixture_cache=fixture_cache)
                if row:
                    rows.append(row)
            except Exception as exc:
                print(f"hist {match_row.fixture_id}: {exc}", file=sys.stderr)

    for match_row in load_db_historical_rows(limit=BUNDESLIGA_LIMIT):
        try:
            row = audit_offline_row(match_row, source="db_bundesliga", fixture_cache=fixture_cache)
            if row:
                rows.append(row)
        except Exception as exc:
            print(f"db {match_row.fixture_id}: {exc}", file=sys.stderr)

    for fid in load_live_fixture_ids():
        try:
            row = audit_live_fixture(fid, results_by_id, fixture_cache=fixture_cache)
            if row:
                rows.append(row)
        except Exception as exc:
            print(f"live {fid}: {exc}", file=sys.stderr)

    seen: set[int] = set()
    deduped: list[AuditRow] = []
    for row in rows:
        if row.fixture_id in seen:
            continue
        seen.add(row.fixture_id)
        deduped.append(row)

    if len(deduped) < MIN_FIXTURES:
        print(f"WARNING: only {len(deduped)} fixtures (target {MIN_FIXTURES})", file=sys.stderr)

    correct_align: Counter = Counter()
    wrong_push: Counter = Counter()
    correlations: dict[str, dict[str, float]] = {}

    for name in SIGNAL_NAMES:
        with_lean = [r for r in deduped if r.signals.get(name)]
        if not with_lean:
            correlations[name] = {"accuracy": 0.0, "correlation": 0.0}
            continue
        hits = sum(1 for r in with_lean if r.signals[name] == r.actual)
        correlations[name] = {
            "accuracy": hits / len(with_lean),
            "correlation": (hits / len(with_lean)) - (sum(1 for r in deduped if r.final_correct) / len(deduped)),
        }

    for r in deduped:
        if r.final_correct:
            for s in r.aligned_with_actual:
                correct_align[s] += 1
        else:
            for s in r.pushed_wrong:
                wrong_push[s] += 1

    combos: Counter = Counter()
    for r in deduped:
        if not r.final_correct:
            continue
        aligned = sorted(r.aligned_with_actual)
        for pair in combinations(aligned, 2):
            combos[pair] += 1

    ablations = run_ablations(deduped, fixture_cache)

    REPLAY_OUT.parent.mkdir(parents=True, exist_ok=True)
    with REPLAY_OUT.open("w", encoding="utf-8") as handle:
        for r in deduped:
            handle.write(
                json.dumps(
                    {
                        "fixture_id": r.fixture_id,
                        "match_name": r.match_name,
                        "actual": r.actual,
                        "final_prediction": r.final_prediction,
                        "wde_prediction": r.wde_prediction,
                        "scoreline_prediction": r.scoreline_prediction,
                        "final_correct": r.final_correct,
                        "aligned_signals": r.aligned_with_actual,
                        "pushed_wrong": r.pushed_wrong,
                        "signals": r.signals,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    write_report(deduped, ablations, correct_align, wrong_push, correlations, combos)
    final_acc = sum(1 for r in deduped if r.final_correct) / max(len(deduped), 1)
    print(f"Analyzed: {len(deduped)} | Final accuracy: {final_acc:.1%}")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
