"""Phase 12B — Specialist Lambda Bridge shadow simulation replay and report."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
import runpy

runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "PHASE_12B_SIMULATION_REPORT.md"
SHADOW_REPLAY_PATH = ROOT / "data" / "shadow" / "phase12b_replay.jsonl"
HISTORICAL_CSV = ROOT / "data" / "historical" / "worldcup_sample.csv"
MIN_FIXTURES = 50


@dataclass
class SimulationRow:
    fixture_id: int
    match_name: str
    source: str
    actual_1x2: str | None
    wde_selection: str
    production_prediction: str
    shadow_prediction: str
    production_scoreline: str
    shadow_scoreline: str
    production_lambda_home: float
    production_lambda_away: float
    shadow_lambda_home: float
    shadow_lambda_away: float
    production_conflict: bool
    shadow_conflict: bool
    conflict_change: str
    production_correct: bool | None
    shadow_correct: bool | None
    bridge_contributors: list[dict]
    global_cap_applied: bool
    data_quality_scale: float
    errors: list[str] = field(default_factory=list)


def _reset_settings(**env: str) -> None:
    for key, value in env.items():
        os.environ[key] = value
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


def load_db_historical_rows(*, competition_key: str = "bundesliga", limit: int = 45) -> list:
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
    return rows


def load_live_fixture_ids() -> list[int]:
    ids: set[int] = set()
    results_path = ROOT / "data" / "results" / "match_results.jsonl"
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ids.add(int(json.loads(line)["fixture_id"]))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue

    history_path = ROOT / "data" / "predictions" / "prediction_history.jsonl"
    if history_path.exists():
        for line in history_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                ids.add(int(json.loads(line)["fixture_id"]))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return sorted(ids)


def simulate_offline_row(row, *, source: str) -> SimulationRow | None:
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.backtesting.historical_loader import build_form_history, build_intelligence_report
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine
    from worldcup_predictor.domain.specialist import MatchSpecialistReport
    from worldcup_predictor.prediction.lambda_bridge.bridge import SpecialistLambdaBridge
    from worldcup_predictor.prediction.lambda_bridge.shadow_runner import (
        build_shadow_prediction,
        compute_shadow_scoreline,
    )
    from worldcup_predictor.prediction.scoreline_engine import _expected_goals_from_report
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    settings = get_settings()
    engine = ScoringEngine()
    wde = WeightedDecisionEngine()
    bridge = SpecialistLambdaBridge(config_version=settings.lambda_bridge_config_version)

    form_history = build_form_history([row])
    home_form, away_form = form_history.get(row.fixture_id, ([], []))
    report = build_intelligence_report(row, home_form=home_form, away_form=away_form)

    context = AgentContext(
        settings=settings,
        competition_key=report.fixture.competition_key if report.fixture else "world_cup_2026",
        locale="en",
    )
    context.shared["intelligence_reports"] = {row.fixture_id: report}

    specialist: MatchSpecialistReport | None = None
    orchestrator = SpecialistOrchestrator(context)
    specialist_result = orchestrator.run(fixture_id=row.fixture_id)
    if specialist_result.success and isinstance(specialist_result.data, MatchSpecialistReport):
        specialist = specialist_result.data
        report.specialist_report = specialist

    baseline = engine.predict(report, specialist_report=specialist, use_weighted_decision=False)
    decision = wde.decide(
        DecisionInput(baseline=baseline, report=report, specialist_report=specialist)
    )
    merged = wde.apply_decision(baseline, decision)
    wde_selection = merged.one_x_two.selection
    home_name = report.home_team.team_name
    away_name = report.away_team.team_name

    production = engine._finalize_prediction(
        merged,
        report,
        home_name,
        away_name,
        specialist_report=specialist,
    )

    lambda_base_h, lambda_base_a = _expected_goals_from_report(report)
    bridge_result = bridge.compute(
        report=report,
        specialist_report=specialist,
        lambda_base_home=lambda_base_h,
        lambda_base_away=lambda_base_a,
        mode="full",
    )
    shadow_scoreline_str, sh, sa = compute_shadow_scoreline(
        report,
        lambda_home=bridge_result.lambda_adjusted_home,
        lambda_away=bridge_result.lambda_adjusted_away,
    )
    shadow_pred = build_shadow_prediction(
        production,
        home_name=home_name,
        away_name=away_name,
        shadow_h=sh,
        shadow_a=sa,
    )

    prod_sel = production.one_x_two.selection
    shadow_sel = shadow_pred.one_x_two.selection
    pub_conflict = wde_selection != prod_sel
    shadow_conflict = wde_selection != shadow_sel
    if pub_conflict and not shadow_conflict:
        change = "improved"
    elif not pub_conflict and shadow_conflict:
        change = "worsened"
    else:
        change = "unchanged"

    prod_scoreline = "—"
    if production.scoreline:
        prod_scoreline = (
            f"{int(round(production.scoreline.home_goals))}-"
            f"{int(round(production.scoreline.away_goals))}"
        )

    actual = row.actual_1x2
    return SimulationRow(
        fixture_id=row.fixture_id,
        match_name=production.match_name,
        source=source,
        actual_1x2=actual,
        wde_selection=wde_selection,
        production_prediction=prod_sel,
        shadow_prediction=shadow_sel,
        production_scoreline=prod_scoreline,
        shadow_scoreline=shadow_scoreline_str,
        production_lambda_home=round(lambda_base_h, 4),
        production_lambda_away=round(lambda_base_a, 4),
        shadow_lambda_home=round(bridge_result.lambda_adjusted_home, 4),
        shadow_lambda_away=round(bridge_result.lambda_adjusted_away, 4),
        production_conflict=pub_conflict,
        shadow_conflict=shadow_conflict,
        conflict_change=change,
        production_correct=prod_sel == actual if actual else None,
        shadow_correct=shadow_sel == actual if actual else None,
        bridge_contributors=[c.to_dict() for c in bridge_result.contributions],
        global_cap_applied=bridge_result.global_cap_applied,
        data_quality_scale=bridge_result.data_quality_scale,
    )


def simulate_live_fixture(fixture_id: int, results_by_id: dict) -> SimulationRow | None:
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine
    from worldcup_predictor.domain.specialist import MatchSpecialistReport
    from worldcup_predictor.prediction.lambda_bridge.bridge import SpecialistLambdaBridge
    from worldcup_predictor.prediction.lambda_bridge.shadow_runner import (
        build_shadow_prediction,
        compute_shadow_scoreline,
    )
    from worldcup_predictor.prediction.scoreline_engine import _expected_goals_from_report
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine
    from worldcup_predictor.schedule.context_loader import load_tournament_context

    settings = get_settings()
    context = AgentContext(settings=settings, competition_key="world_cup_2026", locale="en")
    context.shared["smart_prediction_fetch"] = True
    load_tournament_context(context)

    collector = DataCollectorAgent(context)
    if not collector.run(fixture_id=fixture_id).success:
        return None
    report = (context.shared.get("intelligence_reports") or {}).get(fixture_id)
    if report is None:
        return None

    specialist: MatchSpecialistReport | None = None
    specialist_result = SpecialistOrchestrator(context).run(fixture_id=fixture_id)
    if specialist_result.success and isinstance(specialist_result.data, MatchSpecialistReport):
        specialist = specialist_result.data
        report.specialist_report = specialist

    engine = ScoringEngine()
    wde = WeightedDecisionEngine()
    bridge = SpecialistLambdaBridge(config_version=settings.lambda_bridge_config_version)

    baseline = engine.predict(report, specialist_report=specialist, use_weighted_decision=False)
    merged = wde.apply_decision(
        baseline,
        wde.decide(DecisionInput(baseline=baseline, report=report, specialist_report=specialist)),
    )
    wde_selection = merged.one_x_two.selection
    home_name = report.home_team.team_name
    away_name = report.away_team.team_name
    production = engine._finalize_prediction(
        merged, report, home_name, away_name, specialist_report=specialist
    )
    prod_sel = production.one_x_two.selection

    lambda_base_h, lambda_base_a = _expected_goals_from_report(report)
    bridge_result = bridge.compute(
        report=report,
        specialist_report=specialist,
        lambda_base_home=lambda_base_h,
        lambda_base_away=lambda_base_a,
        mode="full",
    )
    shadow_scoreline_str, sh, sa = compute_shadow_scoreline(
        report,
        lambda_home=bridge_result.lambda_adjusted_home,
        lambda_away=bridge_result.lambda_adjusted_away,
    )
    shadow_pred = build_shadow_prediction(
        production,
        home_name=home_name,
        away_name=away_name,
        shadow_h=sh,
        shadow_a=sa,
    )
    shadow_sel = shadow_pred.one_x_two.selection

    pub_conflict = wde_selection != prod_sel
    shadow_conflict = wde_selection != shadow_sel
    if pub_conflict and not shadow_conflict:
        change = "improved"
    elif not pub_conflict and shadow_conflict:
        change = "worsened"
    else:
        change = "unchanged"

    prod_scoreline = "—"
    if production.scoreline:
        prod_scoreline = (
            f"{int(round(production.scoreline.home_goals))}-"
            f"{int(round(production.scoreline.away_goals))}"
        )

    actual = None
    rec = results_by_id.get(fixture_id)
    if rec:
        actual = rec.winner

    return SimulationRow(
        fixture_id=fixture_id,
        match_name=production.match_name,
        source="live_cache",
        actual_1x2=actual,
        wde_selection=wde_selection,
        production_prediction=prod_sel,
        shadow_prediction=shadow_sel,
        production_scoreline=prod_scoreline,
        shadow_scoreline=shadow_scoreline_str,
        production_lambda_home=round(lambda_base_h, 4),
        production_lambda_away=round(lambda_base_a, 4),
        shadow_lambda_home=round(bridge_result.lambda_adjusted_home, 4),
        shadow_lambda_away=round(bridge_result.lambda_adjusted_away, 4),
        production_conflict=pub_conflict,
        shadow_conflict=shadow_conflict,
        conflict_change=change,
        production_correct=prod_sel == actual if actual else None,
        shadow_correct=shadow_sel == actual if actual else None,
        bridge_contributors=[c.to_dict() for c in bridge_result.contributions],
        global_cap_applied=bridge_result.global_cap_applied,
        data_quality_scale=bridge_result.data_quality_scale,
    )


def aggregate_metrics(rows: list[SimulationRow]) -> dict:
    n = len(rows)
    if n == 0:
        return {}

    prod_conflicts = sum(1 for r in rows if r.production_conflict)
    shadow_conflicts = sum(1 for r in rows if r.shadow_conflict)
    improved = sum(1 for r in rows if r.conflict_change == "improved")
    worsened = sum(1 for r in rows if r.conflict_change == "worsened")

    evaluated = [r for r in rows if r.production_correct is not None]
    prod_acc = sum(1 for r in evaluated if r.production_correct) / len(evaluated) if evaluated else 0.0
    shadow_acc = sum(1 for r in evaluated if r.shadow_correct) / len(evaluated) if evaluated else 0.0

    prod_draws = sum(1 for r in rows if r.production_prediction == "draw")
    shadow_draws = sum(1 for r in rows if r.shadow_prediction == "draw")
    prod_home = sum(1 for r in rows if r.production_prediction == "home_win")
    prod_away = sum(1 for r in rows if r.production_prediction == "away_win")
    shadow_home = sum(1 for r in rows if r.shadow_prediction == "home_win")
    shadow_away = sum(1 for r in rows if r.shadow_prediction == "away_win")

    agent_delta: dict[str, list[float]] = defaultdict(list)
    agent_improve: dict[str, int] = defaultdict(int)
    agent_worsen: dict[str, int] = defaultdict(int)

    for row in rows:
        for contrib in row.bridge_contributors:
            if not contrib.get("included"):
                continue
            agent = contrib.get("agent", "unknown")
            mag = abs(contrib.get("delta_home", 0)) + abs(contrib.get("delta_away", 0))
            agent_delta[agent].append(mag)
            if row.conflict_change == "improved":
                agent_improve[agent] += 1
            elif row.conflict_change == "worsened":
                agent_worsen[agent] += 1

    agent_avg = {
        agent: round(sum(vals) / len(vals), 4) for agent, vals in agent_delta.items() if vals
    }
    best_agents = sorted(agent_avg.items(), key=lambda x: x[1], reverse=True)[:5]
    worst_agents = sorted(agent_avg.items(), key=lambda x: x[1])[:5]

    cap_rate = sum(1 for r in rows if r.global_cap_applied) / n
    dq_scaled = sum(1 for r in rows if r.data_quality_scale < 0.99) / n

    return {
        "fixture_count": n,
        "evaluated_count": len(evaluated),
        "production_conflict_rate": round(prod_conflicts / n, 4),
        "shadow_conflict_rate": round(shadow_conflicts / n, 4),
        "conflict_improved": improved,
        "conflict_worsened": worsened,
        "production_accuracy": round(prod_acc, 4),
        "shadow_accuracy": round(shadow_acc, 4),
        "production_draw_rate": round(prod_draws / n, 4),
        "shadow_draw_rate": round(shadow_draws / n, 4),
        "production_home_rate": round(prod_home / n, 4),
        "production_away_rate": round(prod_away / n, 4),
        "shadow_home_rate": round(shadow_home / n, 4),
        "shadow_away_rate": round(shadow_away / n, 4),
        "global_cap_rate": round(cap_rate, 4),
        "dq_scaling_rate": round(dq_scaled, 4),
        "best_agents": best_agents,
        "worst_agents": worst_agents,
        "agent_improve": dict(agent_improve),
        "agent_worsen": dict(agent_worsen),
    }


def write_report(rows: list[SimulationRow], metrics: dict) -> None:
    prod_cr = metrics.get("production_conflict_rate", 0)
    shadow_cr = metrics.get("shadow_conflict_rate", 0)
    prod_acc = metrics.get("production_accuracy", 0)
    shadow_acc = metrics.get("shadow_accuracy", 0)
    conflict_down = shadow_cr < prod_cr
    acc_ok = shadow_acc >= prod_acc - 0.01

    if conflict_down and acc_ok:
        recommendation = "Proceed to Phase 12C"
        verdict = "PASS"
    elif shadow_acc < prod_acc - 0.01:
        recommendation = "Recalibrate (accuracy degradation detected)"
        verdict = "FAIL — RECALIBRATE"
    else:
        recommendation = "Recalibrate (insufficient conflict reduction)"
        verdict = "FAIL — RECALIBRATE"

    lines = [
        "# Phase 12B — Specialist Lambda Bridge Simulation Report",
        "",
        f"Generated: {datetime.utcnow().isoformat()}Z",
        "",
        "## Mode",
        "",
        "- **Bridge mode:** SHADOW (simulation only)",
        "- **Production pipeline:** unchanged",
        "- **Deploy:** NO",
        "",
        "## Summary",
        "",
        f"| Metric | Production | Shadow |",
        f"|--------|------------|--------|",
        f"| Fixtures simulated | {metrics.get('fixture_count', 0)} | {metrics.get('fixture_count', 0)} |",
        f"| Evaluated (with results) | {metrics.get('evaluated_count', 0)} | {metrics.get('evaluated_count', 0)} |",
        f"| Conflict rate | {prod_cr:.1%} | {shadow_cr:.1%} |",
        f"| 1X2 accuracy | {prod_acc:.1%} | {shadow_acc:.1%} |",
        f"| Draw prediction rate | {metrics.get('production_draw_rate', 0):.1%} | {metrics.get('shadow_draw_rate', 0):.1%} |",
        f"| Home win rate | {metrics.get('production_home_rate', 0):.1%} | {metrics.get('shadow_home_rate', 0):.1%} |",
        f"| Away win rate | {metrics.get('production_away_rate', 0):.1%} | {metrics.get('shadow_away_rate', 0):.1%} |",
        "",
        f"**Conflict improved:** {metrics.get('conflict_improved', 0)} fixtures  ",
        f"**Conflict worsened:** {metrics.get('conflict_worsened', 0)} fixtures  ",
        f"**Global cap applied:** {metrics.get('global_cap_rate', 0):.1%} of fixtures  ",
        f"**DQ scaling applied:** {metrics.get('dq_scaling_rate', 0):.1%} of fixtures  ",
        "",
        "## Bridge contribution analysis",
        "",
        "### Strongest specialist λ signals (avg |Δλ|)",
        "",
    ]
    for agent, avg in metrics.get("best_agents", []):
        lines.append(f"- `{agent}`: {avg:.4f}")
    lines.extend(["", "### Weakest specialist λ signals", ""])
    for agent, avg in metrics.get("worst_agents", []):
        lines.append(f"- `{agent}`: {avg:.4f}")

    lines.extend(
        [
            "",
            "## Success criteria",
            "",
            f"- Conflict reduction: {'YES' if conflict_down else 'NO'} ({prod_cr:.1%} → {shadow_cr:.1%})",
            f"- Accuracy preserved: {'YES' if acc_ok else 'NO'} ({prod_acc:.1%} → {shadow_acc:.1%})",
            "",
            f"## Verdict: **{verdict}**",
            "",
            f"## Recommendation: **{recommendation}**",
            "",
            "## Safety",
            "",
            "- Bridge runs in parallel shadow path only",
            "- Production λ, scoreline, harmonization unchanged",
            "- Fail-closed: bridge errors do not affect production",
            "- No API/UI/deploy changes in this phase",
            "",
            "## Sample conflicts resolved",
            "",
        ]
    )
    improved_samples = [r for r in rows if r.conflict_change == "improved"][:8]
    for sample in improved_samples:
        lines.append(
            f"- Fixture {sample.fixture_id} ({sample.match_name}): "
            f"WDE `{sample.wde_selection}` → prod `{sample.production_prediction}` "
            f"→ shadow `{sample.shadow_prediction}` (λ {sample.production_lambda_home}/{sample.production_lambda_away} "
            f"→ {sample.shadow_lambda_home}/{sample.shadow_lambda_away})"
        )
    if not improved_samples:
        lines.append("- No conflict improvements observed in this replay window.")

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def persist_replay(rows: list[SimulationRow]) -> None:
    SHADOW_REPLAY_PATH.parent.mkdir(parents=True, exist_ok=True)
    with SHADOW_REPLAY_PATH.open("w", encoding="utf-8") as handle:
        for row in rows:
            payload = {
                "fixture_id": row.fixture_id,
                "match_name": row.match_name,
                "source": row.source,
                "production_prediction": row.production_prediction,
                "shadow_prediction": row.shadow_prediction,
                "production_lambda_home": row.production_lambda_home,
                "production_lambda_away": row.production_lambda_away,
                "shadow_lambda_home": row.shadow_lambda_home,
                "shadow_lambda_away": row.shadow_lambda_away,
                "bridge_contributors": row.bridge_contributors,
                "conflict_status": {
                    "production_conflict": row.production_conflict,
                    "shadow_conflict": row.shadow_conflict,
                    "conflict_change": row.conflict_change,
                },
                "global_cap_applied": row.global_cap_applied,
                "data_quality_scale": row.data_quality_scale,
                "wde_selection": row.wde_selection,
                "actual_1x2": row.actual_1x2,
            }
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def main() -> int:
    _reset_settings(LAMBDA_BRIDGE_MODE="off")

    from worldcup_predictor.backtesting.historical_loader import HistoricalLoader
    from worldcup_predictor.results.match_results_store import MatchResultsStore

    rows: list[SimulationRow] = []
    results_by_id = MatchResultsStore().by_fixture_id()

    if HISTORICAL_CSV.exists():
        loader = HistoricalLoader(HISTORICAL_CSV)
        for match_row in loader.load(create_sample_if_missing=False):
            try:
                sim = simulate_offline_row(match_row, source="historical_csv")
                if sim:
                    rows.append(sim)
            except Exception as exc:  # noqa: BLE001
                print(f"historical {match_row.fixture_id} failed: {exc}", file=sys.stderr)

    for match_row in load_db_historical_rows(competition_key="bundesliga", limit=45):
        try:
            sim = simulate_offline_row(match_row, source="db_bundesliga")
            if sim:
                rows.append(sim)
        except Exception as exc:  # noqa: BLE001
            print(f"db {match_row.fixture_id} failed: {exc}", file=sys.stderr)

    live_ids = load_live_fixture_ids()
    for fixture_id in live_ids:
        try:
            sim = simulate_live_fixture(fixture_id, results_by_id)
            if sim:
                rows.append(sim)
        except Exception as exc:  # noqa: BLE001
            print(f"live {fixture_id} failed: {exc}", file=sys.stderr)

    seen: set[int] = set()
    deduped: list[SimulationRow] = []
    for row in rows:
        if row.fixture_id in seen:
            continue
        seen.add(row.fixture_id)
        deduped.append(row)

    if len(deduped) < MIN_FIXTURES:
        print(
            f"WARNING: only {len(deduped)} fixtures simulated (target {MIN_FIXTURES})",
            file=sys.stderr,
        )

    metrics = aggregate_metrics(deduped)
    persist_replay(deduped)
    write_report(deduped, metrics)

    print(f"Phase 12B replay: {len(deduped)} fixtures")
    print(f"Production conflict: {metrics.get('production_conflict_rate', 0):.1%}")
    print(f"Shadow conflict: {metrics.get('shadow_conflict_rate', 0):.1%}")
    print(f"Production accuracy: {metrics.get('production_accuracy', 0):.1%}")
    print(f"Shadow accuracy: {metrics.get('shadow_accuracy', 0):.1%}")
    print(f"Report: {REPORT_PATH}")
    return 0 if deduped else 1


if __name__ == "__main__":
    raise SystemExit(main())
