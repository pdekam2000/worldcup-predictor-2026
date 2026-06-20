"""Phase 16 — Odds-primary shadow engine replay and report (shadow only)."""

from __future__ import annotations

import json
import os
import statistics
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
import runpy

runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_16_ODDS_PRIMARY_SHADOW_REPORT.md"
REPLAY_OUT = ROOT / "data" / "shadow" / "phase16_odds_primary_replay.jsonl"
REPLAY = ROOT / "data" / "shadow" / "phase12b_replay.jsonl"
HIST = ROOT / "data/historical/worldcup_sample.csv"
HISTORY = ROOT / "data/predictions/prediction_history.jsonl"
RESULTS = ROOT / "data/results/match_results.jsonl"
MIN_FIXTURES = 100


@dataclass
class Row:
    fixture_id: int
    match_name: str
    actual: str
    prod_pred: str
    shadow_pred: str
    prod_sl: str
    shadow_sl: str
    prod_lh: float
    prod_la: float
    shadow_lh: float
    shadow_la: float
    prod_spread: float
    shadow_spread: float
    prod_correct: bool
    shadow_correct: bool
    odds_available: bool
    shadow_fallback: bool
    source: str


def is_wc_fixture(fid: int) -> bool:
    return (1489369 <= fid <= 1489425) or (1538999 <= fid <= 1539035) or (900001 <= fid <= 900012)


def collect_wc_ids() -> list[int]:
    ids: set[int] = set()
    if REPLAY.exists():
        for line in REPLAY.read_text(encoding="utf-8").splitlines():
            if line.strip():
                fid = int(json.loads(line)["fixture_id"])
                if is_wc_fixture(fid):
                    ids.add(fid)
    if HISTORY.exists():
        for line in HISTORY.read_text(encoding="utf-8").splitlines():
            if line.strip():
                fid = int(json.loads(line)["fixture_id"])
                if is_wc_fixture(fid):
                    ids.add(fid)
    for fid in list(range(1489369, 1489426)) + list(range(1538999, 1539036)):
        ids.add(fid)
    return sorted(ids)


def load_results() -> dict[int, str]:
    out: dict[int, str] = {}
    if RESULTS.exists():
        for line in RESULTS.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[int(r["fixture_id"])] = r["winner"]
    return out


def load_fixtures() -> list[tuple[int, object, str, str | None]]:
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.data_collector_agent import DataCollectorAgent
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.backtesting.historical_loader import (
        HistoricalLoader,
        build_form_history,
        build_intelligence_report,
    )
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.domain.specialist import MatchSpecialistReport
    from worldcup_predictor.schedule.context_loader import load_tournament_context

    settings = get_settings()
    results = load_results()
    out: list[tuple[int, object, str, str | None]] = []
    seen: set[int] = set()

    if HIST.exists():
        for row in HistoricalLoader(HIST).load(create_sample_if_missing=False):
            if not is_wc_fixture(row.fixture_id):
                continue
            fh = build_form_history([row])
            hf, af = fh.get(row.fixture_id, ([], []))
            report = build_intelligence_report(row, home_form=hf, away_form=af)
            ctx = AgentContext(settings=settings, competition_key="world_cup_2026", locale="en")
            ctx.shared["intelligence_reports"] = {row.fixture_id: report}
            spec = None
            sr = SpecialistOrchestrator(ctx).run(fixture_id=row.fixture_id)
            if sr.success and isinstance(sr.data, MatchSpecialistReport):
                spec = sr.data
            out.append((row.fixture_id, report, "hist_csv", row.actual_1x2))
            seen.add(row.fixture_id)

    for fid in collect_wc_ids():
        if fid in seen:
            continue
        actual = results.get(fid)
        try:
            ctx = AgentContext(settings=settings, competition_key="world_cup_2026", locale="en")
            ctx.shared["smart_prediction_fetch"] = True
            load_tournament_context(ctx)
            if not DataCollectorAgent(ctx).run(fixture_id=fid).success:
                continue
            report = (ctx.shared.get("intelligence_reports") or {}).get(fid)
            if report is None:
                continue
            out.append((fid, report, "live_cache", actual))
            seen.add(fid)
        except Exception as exc:
            print(f"skip {fid}: {exc}", file=sys.stderr)
    return out


def evaluate_row(fid: int, report, source: str, actual: str | None) -> Row | None:
    if not actual:
        return None

    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine
    from worldcup_predictor.prediction.odds_primary.engine import OddsPrimaryScorelineEngine
    from worldcup_predictor.prediction.odds_primary.shadow_runner import shadow_scoreline_from_lambdas
    from worldcup_predictor.prediction.scoreline_engine import _expected_goals_from_report
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    engine = ScoringEngine()
    wde = WeightedDecisionEngine()
    spec = getattr(report, "specialist_report", None)
    baseline = engine.predict(report, specialist_report=spec, use_weighted_decision=False)
    merged = wde.apply_decision(
        baseline,
        wde.decide(DecisionInput(baseline=baseline, report=report, specialist_report=spec)),
    )
    home_name = report.home_team.team_name
    away_name = report.away_team.team_name
    production = engine._finalize_prediction(
        merged, report, home_name, away_name, specialist_report=spec
    )

    prod_lh, prod_la = _expected_goals_from_report(report)
    prod_sl, prod_pred = shadow_scoreline_from_lambdas(report, lambda_home=prod_lh, lambda_away=prod_la)
    final_pred = production.one_x_two.selection

    shadow_engine = OddsPrimaryScorelineEngine()
    shadow_l = shadow_engine.compute(report)
    shadow_sl, shadow_pred = shadow_scoreline_from_lambdas(
        report,
        lambda_home=shadow_l.lambda_home,
        lambda_away=shadow_l.lambda_away,
    )

    return Row(
        fixture_id=fid,
        match_name=production.match_name,
        actual=actual,
        prod_pred=final_pred,
        shadow_pred=shadow_pred,
        prod_sl=prod_sl,
        shadow_sl=shadow_sl,
        prod_lh=prod_lh,
        prod_la=prod_la,
        shadow_lh=shadow_l.lambda_home,
        shadow_la=shadow_l.lambda_away,
        prod_spread=abs(prod_lh - prod_la),
        shadow_spread=shadow_l.spread,
        prod_correct=final_pred == actual,
        shadow_correct=shadow_pred == actual,
        odds_available=shadow_l.odds_available,
        shadow_fallback=shadow_l.used_production_fallback,
        source=source,
    )


def metrics(rows: list[Row]) -> dict:
    n = len(rows)
    if not n:
        return {}
    spreads_p = [r.prod_spread for r in rows]
    spreads_s = [r.shadow_spread for r in rows]
    return {
        "n": n,
        "prod_accuracy": sum(1 for r in rows if r.prod_correct) / n,
        "shadow_accuracy": sum(1 for r in rows if r.shadow_correct) / n,
        "prod_draw": sum(1 for r in rows if r.prod_pred == "draw") / n,
        "shadow_draw": sum(1 for r in rows if r.shadow_pred == "draw") / n,
        "prod_home": sum(1 for r in rows if r.prod_pred == "home_win") / n,
        "shadow_home": sum(1 for r in rows if r.shadow_pred == "home_win") / n,
        "prod_away": sum(1 for r in rows if r.prod_pred == "away_win") / n,
        "shadow_away": sum(1 for r in rows if r.shadow_pred == "away_win") / n,
        "prod_avg_spread": statistics.mean(spreads_p),
        "shadow_avg_spread": statistics.mean(spreads_s),
        "prod_med_spread": statistics.median(spreads_p),
        "shadow_med_spread": statistics.median(spreads_s),
        "prod_scorelines": Counter(r.prod_sl for r in rows),
        "shadow_scorelines": Counter(r.shadow_sl for r in rows),
    }


def write_report(all_rows: list[Row], odds_rows: list[Row]) -> None:
    all_m = metrics(all_rows)
    odds_m = metrics(odds_rows) if odds_rows else {}
    prod_acc = all_m.get("prod_accuracy", 0)
    shadow_acc = all_m.get("shadow_accuracy", 0)
    odds_prod = odds_m.get("prod_accuracy", 0)
    odds_shadow = odds_m.get("shadow_accuracy", 0)

    pass_all = shadow_acc > prod_acc
    pass_odds = odds_shadow > odds_prod if odds_rows else False

    if pass_odds or (pass_all and shadow_acc > prod_acc + 0.01):
        rec = "Proceed — odds-primary shadow beats production on accuracy (odds-available cohort)"
        verdict = "PASS"
    elif shadow_acc > prod_acc:
        rec = "Marginal improvement — extend replay before production consideration"
        verdict = "HOLD"
    else:
        rec = "Redesign — shadow accuracy does not exceed production"
        verdict = "FAIL — REDESIGN"

    best = sorted(
        [r for r in odds_rows if r.shadow_correct and not r.prod_correct],
        key=lambda r: r.shadow_spread,
        reverse=True,
    )[:6]
    worst = sorted(
        [r for r in odds_rows if not r.shadow_correct and r.prod_correct],
        key=lambda r: r.shadow_spread,
        reverse=True,
    )[:6]

    lines = [
        "# Phase 16 — Odds-Primary Shadow Engine Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Mode",
        "",
        "- **Shadow only** — production engine unchanged",
        "- **No deploy**, no live prediction changes",
        "- Engine: `OddsPrimaryScorelineEngine` (odds 70% + xG 25% + stats nudge 5%)",
        "",
        "## Dataset",
        "",
        f"- Fixtures evaluated (with results): **{len(all_rows)}**",
        f"- Odds-available shadow path: **{len(odds_rows)}**",
        "",
        "## 1. Accuracy comparison",
        "",
        "### All fixtures (final production vs shadow scoreline 1X2)",
        "",
        f"| Metric | Production | Shadow |",
        f"|--------|------------|--------|",
        f"| 1X2 accuracy | {prod_acc:.1%} | {shadow_acc:.1%} |",
        f"| Δ (Shadow − Prod) | | **{shadow_acc - prod_acc:+.1%}** |",
        "",
        "### Odds-available cohort (primary shadow path)",
        "",
    ]
    if odds_m:
        lines.extend(
            [
                f"| Metric | Production | Shadow |",
                f"|--------|------------|--------|",
                f"| 1X2 accuracy | {odds_prod:.1%} | {odds_shadow:.1%} |",
                f"| Δ | | **{odds_shadow - odds_prod:+.1%}** |",
                "",
            ]
        )

    lines.extend(
        [
            "## 2. Draw comparison",
            "",
            f"| | Production | Shadow |",
            f"|--|------------|--------|",
            f"| Draw rate (all) | {all_m.get('prod_draw', 0):.1%} | {all_m.get('shadow_draw', 0):.1%} |",
        ]
    )
    if odds_m:
        lines.append(f"| Draw rate (odds cohort) | {odds_m.get('prod_draw', 0):.1%} | {odds_m.get('shadow_draw', 0):.1%} |")

    lines.extend(
        [
            "",
            "## 3. Spread comparison",
            "",
            f"| | Production | Shadow |",
            f"|--|------------|--------|",
            f"| Avg λ spread | {all_m.get('prod_avg_spread', 0):.4f} | {all_m.get('shadow_avg_spread', 0):.4f} |",
            f"| Median λ spread | {all_m.get('prod_med_spread', 0):.4f} | {all_m.get('shadow_med_spread', 0):.4f} |",
            "",
            "## 4. Scoreline distribution (top 8)",
            "",
            "### Production",
            "",
        ]
    )
    for sl, cnt in all_m.get("prod_scorelines", Counter()).most_common(8):
        lines.append(f"- `{sl}`: {cnt} ({cnt/len(all_rows):.1%})")
    lines.extend(["", "### Shadow", ""])
    for sl, cnt in all_m.get("shadow_scorelines", Counter()).most_common(8):
        lines.append(f"- `{sl}`: {cnt} ({cnt/len(all_rows):.1%})")

    lines.extend(["", "## 5. Best examples (shadow correct, production wrong)", ""])
    if best:
        for r in best:
            lines.append(
                f"- **{r.fixture_id}** {r.match_name}: actual `{r.actual}` | "
                f"prod `{r.prod_pred}` ({r.prod_sl}) | shadow `{r.shadow_pred}` ({r.shadow_sl}) | "
                f"λ {r.prod_lh:.2f}/{r.prod_la:.2f} → {r.shadow_lh:.2f}/{r.shadow_la:.2f}"
            )
    else:
        lines.append("- None in odds cohort.")

    lines.extend(["", "## 6. Worst examples (production correct, shadow wrong)", ""])
    if worst:
        for r in worst:
            lines.append(
                f"- **{r.fixture_id}** {r.match_name}: actual `{r.actual}` | "
                f"prod `{r.prod_pred}` ({r.prod_sl}) | shadow `{r.shadow_pred}` ({r.shadow_sl})"
            )
    else:
        lines.append("- None in odds cohort.")

    lines.extend(
        [
            "",
            "## 7. Recommendation",
            "",
            f"**Verdict: {verdict}**",
            "",
            f"**{rec}**",
            "",
            "### Success criterion",
            "",
            f"- Accuracy > Production: **{'YES' if shadow_acc > prod_acc else 'NO'}** (all fixtures)",
            f"- Odds cohort: **{'YES' if odds_shadow > odds_prod else 'NO'}**" if odds_rows else "",
            "",
            "Note: Draw rate reduction is expected but **not** the success metric for Phase 16.",
            "",
            "**Stop — shadow only. No deploy. No production changes.**",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    os.environ["LAMBDA_BRIDGE_MODE"] = "off"
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()

    fixtures = load_fixtures()
    print(f"loaded {len(fixtures)} WC fixtures", file=sys.stderr)

    rows: list[Row] = []
    for fid, report, source, actual in fixtures:
        try:
            row = evaluate_row(fid, report, source, actual)
            if row:
                rows.append(row)
        except Exception as exc:
            print(f"eval {fid}: {exc}", file=sys.stderr)

    odds_rows = [r for r in rows if r.odds_available and not r.shadow_fallback]

    REPLAY_OUT.parent.mkdir(parents=True, exist_ok=True)
    with REPLAY_OUT.open("w", encoding="utf-8") as handle:
        for r in rows:
            handle.write(
                json.dumps(
                    {
                        "fixture_id": r.fixture_id,
                        "match_name": r.match_name,
                        "actual": r.actual,
                        "production_prediction": r.prod_pred,
                        "shadow_prediction": r.shadow_pred,
                        "production_scoreline": r.prod_sl,
                        "shadow_scoreline": r.shadow_sl,
                        "production_correct": r.prod_correct,
                        "shadow_correct": r.shadow_correct,
                        "odds_available": r.odds_available,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    if len(rows) < MIN_FIXTURES:
        print(f"WARNING: only {len(rows)} evaluated (target {MIN_FIXTURES})", file=sys.stderr)

    write_report(rows, odds_rows)
    all_m = metrics(rows)
    print(f"Evaluated: {len(rows)} | Prod {all_m.get('prod_accuracy', 0):.1%} | Shadow {all_m.get('shadow_accuracy', 0):.1%}")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
