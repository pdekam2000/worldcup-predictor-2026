"""Phase 12B-R — Lambda bridge parameter sweep and ablation (simulation only)."""

from __future__ import annotations

import itertools
import json
import os
import pickle
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
import runpy

runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "PHASE_12B_R_RECALIBRATION_REPORT.md"
CACHE_PATH = ROOT / "data" / "shadow" / "phase12br_fixture_cache.pkl"
RESULTS_PATH = ROOT / "data" / "shadow" / "phase12br_sweep_results.jsonl"

# Reuse Phase 12B fixture loaders
from scripts.validate_phase12b_lambda_bridge import (  # noqa: E402
    HISTORICAL_CSV,
    aggregate_metrics,
    load_db_historical_rows,
    load_live_fixture_ids,
    simulate_live_fixture,
    simulate_offline_row,
)


@dataclass
class CachedFixture:
    fixture_id: int
    match_name: str
    report: object
    specialist: object | None
    production: object
    wde_selection: str
    prod_selection: str
    actual_1x2: str | None
    lambda_base_h: float
    lambda_base_a: float
    home_name: str
    away_name: str
    production_conflict: bool
    production_correct: bool | None


@dataclass
class CandidateResult:
    params_name: str
    params: dict
    fixture_count: int
    evaluated_count: int
    production_conflict_rate: float
    shadow_conflict_rate: float
    production_accuracy: float
    shadow_accuracy: float
    production_draw_rate: float
    shadow_draw_rate: float
    shadow_home_rate: float
    shadow_away_rate: float
    avg_abs_delta_lambda: float
    max_agent_share: float
    global_cap_rate: float
    dq_scaling_rate: float
    conflict_improved: int
    conflict_worsened: int
    passes: bool
    fail_reasons: list[str] = field(default_factory=list)
    worst_examples: list[dict] = field(default_factory=list)


def _reset_settings() -> None:
    os.environ["LAMBDA_BRIDGE_MODE"] = "off"
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()


def build_fixture_cache(*, force: bool = False) -> list[CachedFixture]:
    if CACHE_PATH.exists() and not force:
        try:
            with CACHE_PATH.open("rb") as handle:
                cached = pickle.load(handle)
            if cached:
                print(f"Loaded {len(cached)} fixtures from cache", file=sys.stderr)
                return cached
        except (OSError, pickle.PickleError):
            pass

    from worldcup_predictor.backtesting.historical_loader import HistoricalLoader
    from worldcup_predictor.results.match_results_store import MatchResultsStore

    _reset_settings()
    results_by_id = MatchResultsStore().by_fixture_id()
    cache = _collect_fixtures(results_by_id)

    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("wb") as handle:
        pickle.dump(cache, handle, protocol=pickle.HIGHEST_PROTOCOL)
    print(f"Cached {len(cache)} fixtures to {CACHE_PATH}", file=sys.stderr)
    return cache


def _collect_fixtures(results_by_id: dict) -> list[CachedFixture]:
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.backtesting.historical_loader import (
        HistoricalLoader,
        build_form_history,
        build_intelligence_report,
    )
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine
    from worldcup_predictor.domain.specialist import MatchSpecialistReport
    from worldcup_predictor.prediction.scoreline_engine import _expected_goals_from_report
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine
    from worldcup_predictor.schedule.context_loader import load_tournament_context

    settings = get_settings()
    engine = ScoringEngine()
    wde = WeightedDecisionEngine()
    out: list[CachedFixture] = []
    seen: set[int] = set()

    def add_from_report(
        report,
        specialist,
        *,
        actual: str | None,
        source: str,
    ) -> None:
        fid = report.fixture_id
        if fid in seen:
            return
        baseline = engine.predict(report, specialist_report=specialist, use_weighted_decision=False)
        merged = wde.apply_decision(
            baseline,
            wde.decide(DecisionInput(baseline=baseline, report=report, specialist_report=specialist)),
        )
        wde_sel = merged.one_x_two.selection
        home_name = report.home_team.team_name
        away_name = report.away_team.team_name
        production = engine._finalize_prediction(
            merged, report, home_name, away_name, specialist_report=specialist
        )
        lh, la = _expected_goals_from_report(report)
        prod_sel = production.one_x_two.selection
        out.append(
            CachedFixture(
                fixture_id=fid,
                match_name=production.match_name,
                report=report,
                specialist=specialist,
                production=production,
                wde_selection=wde_sel,
                prod_selection=prod_sel,
                actual_1x2=actual,
                lambda_base_h=lh,
                lambda_base_a=la,
                home_name=home_name,
                away_name=away_name,
                production_conflict=wde_sel != prod_sel,
                production_correct=prod_sel == actual if actual else None,
            )
        )
        seen.add(fid)

    def offline_row(row, actual: str) -> None:
        form_history = build_form_history([row])
        home_form, away_form = form_history.get(row.fixture_id, ([], []))
        report = build_intelligence_report(row, home_form=home_form, away_form=away_form)
        context = AgentContext(
            settings=settings,
            competition_key=report.fixture.competition_key if report.fixture else "world_cup_2026",
            locale="en",
        )
        context.shared["intelligence_reports"] = {row.fixture_id: report}
        specialist = None
        sr = SpecialistOrchestrator(context).run(fixture_id=row.fixture_id)
        if sr.success and isinstance(sr.data, MatchSpecialistReport):
            specialist = sr.data
            report.specialist_report = specialist
        add_from_report(report, specialist, actual=actual, source="offline")

    if HISTORICAL_CSV.exists():
        for row in HistoricalLoader(HISTORICAL_CSV).load(create_sample_if_missing=False):
            try:
                offline_row(row, row.actual_1x2)
            except Exception as exc:  # noqa: BLE001
                print(f"cache historical {row.fixture_id}: {exc}", file=sys.stderr)

    for row in load_db_historical_rows(competition_key="bundesliga", limit=45):
        try:
            offline_row(row, row.actual_1x2)
        except Exception as exc:  # noqa: BLE001
            print(f"cache db {row.fixture_id}: {exc}", file=sys.stderr)

    for fixture_id in load_live_fixture_ids():
        try:
            context = AgentContext(settings=settings, competition_key="world_cup_2026", locale="en")
            context.shared["smart_prediction_fetch"] = True
            load_tournament_context(context)
            if not DataCollectorAgent(context).run(fixture_id=fixture_id).success:
                continue
            report = (context.shared.get("intelligence_reports") or {}).get(fixture_id)
            if report is None:
                continue
            specialist = None
            sr = SpecialistOrchestrator(context).run(fixture_id=fixture_id)
            if sr.success and isinstance(sr.data, MatchSpecialistReport):
                specialist = sr.data
                report.specialist_report = specialist
            rec = results_by_id.get(fixture_id)
            actual = rec.winner if rec else None
            add_from_report(report, specialist, actual=actual, source="live")
        except Exception as exc:  # noqa: BLE001
            print(f"cache live {fixture_id}: {exc}", file=sys.stderr)

    return out


def evaluate_candidate(
    params,
    fixtures: list[CachedFixture],
    *,
    baseline: CandidateResult,
) -> CandidateResult:
    from worldcup_predictor.prediction.lambda_bridge.bridge import SpecialistLambdaBridge
    from worldcup_predictor.prediction.lambda_bridge.calibration import apply_sweep
    from worldcup_predictor.prediction.lambda_bridge.shadow_runner import (
        build_shadow_prediction,
        compute_shadow_scoreline,
    )

    bridge = SpecialistLambdaBridge(config_version="12br-sweep")
    sim_rows = []

    with apply_sweep(params):
        for fx in fixtures:
            bridge_result = bridge.compute(
                report=fx.report,
                specialist_report=fx.specialist,
                lambda_base_home=fx.lambda_base_h,
                lambda_base_away=fx.lambda_base_a,
                mode="full",
                active_agents_override=params.active_agents,
            )
            _, sh, sa = compute_shadow_scoreline(
                fx.report,
                lambda_home=bridge_result.lambda_adjusted_home,
                lambda_away=bridge_result.lambda_adjusted_away,
            )
            shadow_pred = build_shadow_prediction(
                fx.production,
                home_name=fx.home_name,
                away_name=fx.away_name,
                shadow_h=sh,
                shadow_a=sa,
            )
            shadow_sel = shadow_pred.one_x_two.selection
            shadow_conflict = fx.wde_selection != shadow_sel
            if fx.production_conflict and not shadow_conflict:
                change = "improved"
            elif not fx.production_conflict and shadow_conflict:
                change = "worsened"
            else:
                change = "unchanged"

            from scripts.validate_phase12b_lambda_bridge import SimulationRow

            sim_rows.append(
                SimulationRow(
                    fixture_id=fx.fixture_id,
                    match_name=fx.match_name,
                    source="cache",
                    actual_1x2=fx.actual_1x2,
                    wde_selection=fx.wde_selection,
                    production_prediction=fx.prod_selection,
                    shadow_prediction=shadow_sel,
                    production_scoreline="",
                    shadow_scoreline=f"{sh}-{sa}",
                    production_lambda_home=fx.lambda_base_h,
                    production_lambda_away=fx.lambda_base_a,
                    shadow_lambda_home=bridge_result.lambda_adjusted_home,
                    shadow_lambda_away=bridge_result.lambda_adjusted_away,
                    production_conflict=fx.production_conflict,
                    shadow_conflict=shadow_conflict,
                    conflict_change=change,
                    production_correct=fx.production_correct,
                    shadow_correct=shadow_sel == fx.actual_1x2 if fx.actual_1x2 else None,
                    bridge_contributors=[c.to_dict() for c in bridge_result.contributions],
                    global_cap_applied=bridge_result.global_cap_applied,
                    data_quality_scale=bridge_result.data_quality_scale,
                )
            )

    metrics = aggregate_metrics(sim_rows)
    agent_totals: dict[str, float] = defaultdict(float)
    total_delta = 0.0
    for row in sim_rows:
        for c in row.bridge_contributors:
            if not c.get("included"):
                continue
            mag = abs(c.get("delta_home", 0)) + abs(c.get("delta_away", 0))
            agent_totals[c.get("agent", "?")] += mag
            total_delta += mag

    max_share = 0.0
    if total_delta > 0:
        max_share = max(agent_totals.values()) / total_delta

    avg_delta = 0.0
    if sim_rows:
        deltas = [
            abs(r.shadow_lambda_home - r.production_lambda_home)
            + abs(r.shadow_lambda_away - r.production_lambda_away)
            for r in sim_rows
        ]
        avg_delta = sum(deltas) / len(deltas)

    worst = []
    for row in sim_rows:
        if row.conflict_change == "worsened" or (
            row.shadow_correct is False and row.production_correct is True
        ):
            worst.append(
                {
                    "fixture_id": row.fixture_id,
                    "match": row.match_name,
                    "wde": row.wde_selection,
                    "prod": row.production_prediction,
                    "shadow": row.shadow_prediction,
                    "actual": row.actual_1x2,
                    "lambda": f"{row.production_lambda_home:.3f}/{row.production_lambda_away:.3f}"
                    f"→{row.shadow_lambda_home:.3f}/{row.shadow_lambda_away:.3f}",
                }
            )

    fail_reasons: list[str] = []
    prod_acc = metrics["production_accuracy"]
    shadow_acc = metrics["shadow_accuracy"]
    prod_cr = metrics["production_conflict_rate"]
    shadow_cr = metrics["shadow_conflict_rate"]
    prod_dr = metrics["production_draw_rate"]
    shadow_dr = metrics["shadow_draw_rate"]
    cap_rate = metrics["global_cap_rate"]

    if shadow_acc < prod_acc:
        fail_reasons.append(f"accuracy {shadow_acc:.1%} < baseline {prod_acc:.1%}")
    if shadow_cr >= prod_cr:
        fail_reasons.append(f"conflict {shadow_cr:.1%} not below {prod_cr:.1%}")
    if shadow_dr >= prod_dr:
        fail_reasons.append(f"draw rate {shadow_dr:.1%} not below {prod_dr:.1%}")
    if max_share > 0.55:
        fail_reasons.append(f"single signal dominance {max_share:.1%} > 55%")
    if cap_rate > 0.40:
        fail_reasons.append(f"global cap rate {cap_rate:.1%} too high (>40%)")

    params_dict = {
        "global_cap": params.global_cap,
        "market_cap": params.market_cap,
        "injury_cap": params.injury_cap,
        "lineup_cap": params.lineup_cap,
        "tournament_cap": params.tournament_cap,
        "dq_disable_below": params.dq_disable_below,
        "active_agents": sorted(params.active_agents) if params.active_agents else None,
    }

    return CandidateResult(
        params_name=params.name,
        params=params_dict,
        fixture_count=metrics["fixture_count"],
        evaluated_count=metrics["evaluated_count"],
        production_conflict_rate=prod_cr,
        shadow_conflict_rate=shadow_cr,
        production_accuracy=prod_acc,
        shadow_accuracy=shadow_acc,
        production_draw_rate=prod_dr,
        shadow_draw_rate=shadow_dr,
        shadow_home_rate=metrics["shadow_home_rate"],
        shadow_away_rate=metrics["shadow_away_rate"],
        avg_abs_delta_lambda=round(avg_delta, 4),
        max_agent_share=round(max_share, 4),
        global_cap_rate=cap_rate,
        dq_scaling_rate=metrics["dq_scaling_rate"],
        conflict_improved=metrics["conflict_improved"],
        conflict_worsened=metrics["conflict_worsened"],
        passes=len(fail_reasons) == 0,
        fail_reasons=fail_reasons,
        worst_examples=worst[:5],
    )


def baseline_candidate(fixtures: list[CachedFixture]) -> CandidateResult:
    from worldcup_predictor.prediction.lambda_bridge.calibration import BridgeSweepParams

    n = len(fixtures)
    evaluated = [f for f in fixtures if f.production_correct is not None]
    prod_acc = sum(1 for f in evaluated if f.production_correct) / len(evaluated) if evaluated else 0.0
    prod_cr = sum(1 for f in fixtures if f.production_conflict) / n if n else 0.0
    prod_dr = sum(1 for f in fixtures if f.prod_selection == "draw") / n if n else 0.0
    return CandidateResult(
        params_name="production_baseline",
        params={},
        fixture_count=n,
        evaluated_count=len(evaluated),
        production_conflict_rate=round(prod_cr, 4),
        shadow_conflict_rate=round(prod_cr, 4),
        production_accuracy=round(prod_acc, 4),
        shadow_accuracy=round(prod_acc, 4),
        production_draw_rate=round(prod_dr, 4),
        shadow_draw_rate=round(prod_dr, 4),
        shadow_home_rate=round(sum(1 for f in fixtures if f.prod_selection == "home_win") / n, 4) if n else 0,
        shadow_away_rate=round(sum(1 for f in fixtures if f.prod_selection == "away_win") / n, 4) if n else 0,
        avg_abs_delta_lambda=0.0,
        max_agent_share=0.0,
        global_cap_rate=0.0,
        dq_scaling_rate=0.0,
        conflict_improved=0,
        conflict_worsened=0,
        passes=True,
    )


def iter_grid_params():
    from worldcup_predictor.prediction.lambda_bridge.calibration import (
        SWEEP_DQ_CUTOFFS,
        SWEEP_GLOBAL_CAPS,
        SWEEP_INJURY_CAPS,
        SWEEP_LINEUP_CAPS,
        SWEEP_MARKET_CAPS,
        SWEEP_TOURNAMENT_CAPS,
        BridgeSweepParams,
    )

    idx = 0
    for g, m, inj, lin, tour, dq in itertools.product(
        SWEEP_GLOBAL_CAPS,
        SWEEP_MARKET_CAPS,
        SWEEP_INJURY_CAPS,
        SWEEP_LINEUP_CAPS,
        SWEEP_TOURNAMENT_CAPS,
        SWEEP_DQ_CUTOFFS,
    ):
        idx += 1
        yield BridgeSweepParams(
            name=f"grid_{idx:04d}",
            global_cap=g,
            market_cap=m,
            injury_cap=inj,
            lineup_cap=lin,
            tournament_cap=tour,
            dq_disable_below=dq,
            active_agents=None,
        )


def iter_ablation_params(best_grid: BridgeSweepParams | None):
    from worldcup_predictor.prediction.lambda_bridge.calibration import ABLATION_SCENARIOS, BridgeSweepParams

    base = best_grid or BridgeSweepParams(name="ablation_default")
    for label, agents in ABLATION_SCENARIOS.items():
        yield BridgeSweepParams(
            name=label,
            global_cap=base.global_cap,
            market_cap=base.market_cap,
            injury_cap=base.injury_cap,
            lineup_cap=base.lineup_cap,
            tournament_cap=base.tournament_cap,
            dq_disable_below=base.dq_disable_below,
            active_agents=agents,
        )


def write_report(
    baseline: CandidateResult,
    passing: list[CandidateResult],
    top: list[CandidateResult],
    ablation: list[CandidateResult],
    total_swept: int,
) -> None:
    best = top[0] if top else None
    if best and best.passes:
        rec = "Safe for Phase 12C shadow production (simulation validated)"
        verdict = "PROCEED — shadow 12C with recalibrated params"
    elif best:
        rec = "Further tuning recommended; best near-miss does not meet all gates"
        verdict = "HOLD — partial improvement only"
    else:
        rec = "Pause bridge activation; no candidate meets safety gates"
        verdict = "PAUSE BRIDGE"

    lines = [
        "# Phase 12B-R — Lambda Bridge Recalibration Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Mode",
        "",
        "- Simulation only — no deploy, no production changes",
        "",
        "## Production baseline (unchanged)",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Fixtures | {baseline.fixture_count} |",
        f"| Evaluated | {baseline.evaluated_count} |",
        f"| Conflict rate | {baseline.production_conflict_rate:.1%} |",
        f"| Accuracy | {baseline.production_accuracy:.1%} |",
        f"| Draw rate | {baseline.production_draw_rate:.1%} |",
        "",
        f"Grid combinations tested: **{total_swept}**",
        f"Candidates passing all gates: **{len(passing)}**",
        "",
        "## Success gates",
        "",
        "- Shadow accuracy ≥ production baseline",
        "- Shadow conflict rate < production",
        "- Shadow draw rate < production",
        "- No single signal > 55% of total |Δλ|",
        "- Global cap applied ≤ 40% of fixtures",
        "",
        "## Top candidates",
        "",
    ]

    if not top:
        lines.append("_No candidates ranked._")
    else:
        lines.append(
            "| Rank | Name | Accuracy | Conflict | Draw | Avg |Δλ| | Cap% | Dominance | Pass |"
        )
        lines.append("|------|------|----------|----------|------|---------|------|-----------|------|")
        for i, c in enumerate(top[:15], 1):
            lines.append(
                f"| {i} | {c.params_name} | {c.shadow_accuracy:.1%} | {c.shadow_conflict_rate:.1%} | "
                f"{c.shadow_draw_rate:.1%} | {c.avg_abs_delta_lambda:.3f} | {c.global_cap_rate:.1%} | "
                f"{c.max_agent_share:.1%} | {'✓' if c.passes else '✗'} |"
            )

    if best:
        lines.extend(
            [
                "",
                "## Best candidate",
                "",
                f"**{best.params_name}**",
                "",
                "```json",
                json.dumps(best.params, indent=2),
                "```",
                "",
                f"- Accuracy: {best.shadow_accuracy:.1%} (baseline {best.production_accuracy:.1%})",
                f"- Conflict: {best.shadow_conflict_rate:.1%} (baseline {best.production_conflict_rate:.1%})",
                f"- Draw rate: {best.shadow_draw_rate:.1%} (baseline {best.production_draw_rate:.1%})",
                f"- Home/Away: {best.shadow_home_rate:.1%} / {best.shadow_away_rate:.1%}",
                f"- Avg |Δλ|: {best.avg_abs_delta_lambda:.4f}",
                f"- Global cap applied: {best.global_cap_rate:.1%}",
                f"- Max agent share: {best.max_agent_share:.1%}",
                f"- Conflicts improved/worsened: {best.conflict_improved}/{best.conflict_worsened}",
                "",
                "### Why safer",
                "",
            ]
        )
        if best.passes:
            lines.append(
                "- Meets all gates: accuracy preserved, conflict and draw rates reduced, "
                "balanced specialist contributions, bounded global cap usage."
            )
        else:
            lines.append(f"- Near-miss: {', '.join(best.fail_reasons)}")
        if best.worst_examples:
            lines.extend(["", "### Worst-case examples", ""])
            for ex in best.worst_examples:
                lines.append(
                    f"- {ex['fixture_id']} {ex['match']}: WDE `{ex['wde']}` prod `{ex['prod']}` "
                    f"shadow `{ex['shadow']}` actual `{ex['actual']}` λ {ex['lambda']}"
                )

    lines.extend(
        [
            "",
            "## Ablation summary (best grid caps)",
            "",
            "| Scenario | Accuracy | Conflict | Draw | Pass |",
            "|----------|----------|----------|------|------|",
        ]
    )
    for c in ablation:
        lines.append(
            f"| {c.params_name} | {c.shadow_accuracy:.1%} | {c.shadow_conflict_rate:.1%} | "
            f"{c.shadow_draw_rate:.1%} | {'✓' if c.passes else '✗'} |"
        )

    lines.extend(
        [
            "",
            f"## Verdict: **{verdict}**",
            "",
            f"## Recommendation: **{rec}**",
            "",
            "## Safety",
            "",
            "- No deployment performed",
            "- Production predictions unchanged",
            "- Recalibrated params are simulation-only until explicit 12C config update",
            "",
        ]
    )

    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    from worldcup_predictor.prediction.lambda_bridge.calibration import BridgeSweepParams

    _reset_settings()
    fixtures = build_fixture_cache()
    if len(fixtures) < 50:
        print(f"WARNING: only {len(fixtures)} fixtures cached", file=sys.stderr)

    baseline = baseline_candidate(fixtures)
    print(
        f"Baseline: conflict={baseline.production_conflict_rate:.1%} "
        f"acc={baseline.production_accuracy:.1%} draw={baseline.production_draw_rate:.1%}",
        file=sys.stderr,
    )

    results: list[CandidateResult] = []
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.write_text("", encoding="utf-8")

    grid_total = 0
    for params in iter_grid_params():
        grid_total += 1
        cand = evaluate_candidate(params, fixtures, baseline=baseline)
        results.append(cand)
        with RESULTS_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(cand.__dict__, ensure_ascii=False) + "\n")
        if grid_total % 200 == 0:
            print(f"  grid {grid_total}...", file=sys.stderr)

    passing = [r for r in results if r.passes]
    ranked = sorted(
        results,
        key=lambda c: (
            -c.passes,
            -c.shadow_accuracy,
            c.shadow_conflict_rate,
            c.shadow_draw_rate,
            c.max_agent_share,
        ),
    )

    best_grid_params = None
    if ranked and ranked[0].params:
        p = ranked[0].params
        best_grid_params = BridgeSweepParams(
            name=ranked[0].params_name,
            global_cap=float(p.get("global_cap", 0.22)),
            market_cap=float(p.get("market_cap", 0.10)),
            injury_cap=float(p.get("injury_cap", 0.12)),
            lineup_cap=float(p.get("lineup_cap", 0.10)),
            tournament_cap=float(p.get("tournament_cap", 0.06)),
            dq_disable_below=float(p.get("dq_disable_below", 45.0)),
        )

    ablation_results: list[CandidateResult] = []
    for params in iter_ablation_params(best_grid_params):
        cand = evaluate_candidate(params, fixtures, baseline=baseline)
        ablation_results.append(cand)

    all_passing = passing + [r for r in ablation_results if r.passes]
    all_ranked = sorted(
        passing + ablation_results,
        key=lambda c: (
            -c.passes,
            -c.shadow_accuracy,
            c.shadow_conflict_rate,
            c.shadow_draw_rate,
        ),
    )

    write_report(baseline, all_passing, all_ranked, ablation_results, grid_total)

    print(f"Grid tested: {grid_total}")
    print(f"Passing: {len(passing)} grid + {sum(1 for r in ablation_results if r.passes)} ablation")
    if all_ranked:
        b = all_ranked[0]
        print(
            f"Best: {b.params_name} acc={b.shadow_accuracy:.1%} conflict={b.shadow_conflict_rate:.1%} "
            f"pass={b.passes}"
        )
    print(f"Report: {REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
