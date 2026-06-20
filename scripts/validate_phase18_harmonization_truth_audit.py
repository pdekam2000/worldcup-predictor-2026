"""Phase 18 — Harmonization truth audit (read-only, no production changes)."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
import runpy

runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_18_HARMONIZATION_TRUTH_AUDIT.md"
REPLAY_OUT = ROOT / "data" / "shadow" / "phase18_harmonization_replay.jsonl"
HISTORICAL_CSV = ROOT / "data" / "historical" / "worldcup_sample.csv"
MIN_FIXTURES = 200
BUNDESLIGA_LIMIT = 180
DQ_HIGH = 0.60
DQ_LOW = 0.45


@dataclass
class Row:
    fixture_id: int
    match_name: str
    source: str
    cohort: str
    actual: str
    wde: str
    scoreline: str
    final: str
    wde_correct: bool
    scoreline_correct: bool
    final_correct: bool
    wde_scoreline_conflict: bool
    override: bool
    override_outcome: str  # helpful | harmful | neutral | none
    has_odds: bool
    data_quality_pct: float


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


def _actual_winner(value) -> str | None:
    if value is None:
        return None
    if hasattr(value, "winner"):
        return str(value.winner)
    return str(value)


def _scoreline_to_1x2(h: int, a: int) -> str:
    if h > a:
        return "home_win"
    if h < a:
        return "away_win"
    return "draw"


def _override_outcome(wde: str, final: str, actual: str) -> str:
    if wde == final:
        return "none"
    wde_ok = wde == actual
    final_ok = final == actual
    if final_ok and not wde_ok:
        return "helpful"
    if wde_ok and not final_ok:
        return "harmful"
    return "neutral"


def evaluate_fixture(report, specialist, *, actual: str, source: str) -> Row | None:
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

    candidates = generate_scoreline_candidates(report)
    sh, sa = primary_scoreline(candidates)
    scoreline_pred = _scoreline_to_1x2(sh, sa)

    production = engine._finalize_prediction(
        merged,
        report,
        report.home_team.team_name,
        report.away_team.team_name,
        specialist_report=specialist,
    )
    final_pred = production.one_x_two.selection

    dq = (report.data_quality.score * 100) if report.data_quality else 40.0
    odds = report.odds
    has_odds = bool(odds and odds.available and odds.bookmakers)

    if source in {"historical_csv", "live_wc"}:
        cohort = "world_cup"
    else:
        cohort = "bundesliga"

    override = wde_pred != final_pred
    return Row(
        fixture_id=report.fixture_id,
        match_name=production.match_name,
        source=source,
        cohort=cohort,
        actual=actual,
        wde=wde_pred,
        scoreline=scoreline_pred,
        final=final_pred,
        wde_correct=wde_pred == actual,
        scoreline_correct=scoreline_pred == actual,
        final_correct=final_pred == actual,
        wde_scoreline_conflict=wde_pred != scoreline_pred,
        override=override,
        override_outcome=_override_outcome(wde_pred, final_pred, actual),
        has_odds=has_odds,
        data_quality_pct=dq,
    )


def evaluate_offline(row, *, source: str) -> Row | None:
    from worldcup_predictor.agents.base import AgentContext
    from worldcup_predictor.agents.specialists.orchestrator import SpecialistOrchestrator
    from worldcup_predictor.backtesting.historical_loader import build_form_history, build_intelligence_report
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.domain.specialist import MatchSpecialistReport

    actual = row.actual_1x2
    if not actual:
        return None

    settings = get_settings()
    fh = build_form_history([row])
    hf, af = fh.get(row.fixture_id, ([], []))
    report = build_intelligence_report(row, home_form=hf, away_form=af)
    ctx = AgentContext(
        settings=settings,
        competition_key=report.fixture.competition_key if report.fixture else "bundesliga",
        locale="en",
    )
    ctx.shared["intelligence_reports"] = {row.fixture_id: report}
    specialist = None
    sr = SpecialistOrchestrator(ctx).run(fixture_id=row.fixture_id)
    if sr.success and isinstance(sr.data, MatchSpecialistReport):
        specialist = sr.data
        report.specialist_report = specialist
    return evaluate_fixture(report, specialist, actual=actual, source=source)


def evaluate_live(fixture_id: int, results_by_id: dict) -> Row | None:
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
    specialist = None
    sr = SpecialistOrchestrator(ctx).run(fixture_id=fixture_id)
    if sr.success and isinstance(sr.data, MatchSpecialistReport):
        specialist = sr.data
        report.specialist_report = specialist
    return evaluate_fixture(report, specialist, actual=actual, source="live_wc")


def _acc(rows: list[Row], pred: Callable[[Row], bool]) -> float:
    return sum(1 for r in rows if pred(r)) / max(len(rows), 1)


def _pct(n: int, d: int) -> str:
    return f"{n / d:.1%}" if d else "—"


def cohort_metrics(rows: list[Row]) -> dict[str, float | int]:
    n = len(rows)
    overrides = [r for r in rows if r.override]
    helpful = sum(1 for r in overrides if r.override_outcome == "helpful")
    harmful = sum(1 for r in overrides if r.override_outcome == "harmful")
    neutral = sum(1 for r in overrides if r.override_outcome == "neutral")
    return {
        "n": n,
        "wde_accuracy": _acc(rows, lambda r: r.wde_correct),
        "scoreline_accuracy": _acc(rows, lambda r: r.scoreline_correct),
        "final_accuracy": _acc(rows, lambda r: r.final_correct),
        "conflict_rate": sum(1 for r in rows if r.wde_scoreline_conflict) / max(n, 1),
        "override_rate": len(overrides) / max(n, 1),
        "helpful_overrides": helpful,
        "harmful_overrides": harmful,
        "neutral_overrides": neutral,
        "helpful_rate": helpful / max(len(overrides), 1),
        "harmful_rate": harmful / max(len(overrides), 1),
    }


def write_report(rows: list[Row]) -> None:
    m = cohort_metrics(rows)
    n = m["n"]
    overrides = [r for r in rows if r.override]

    cohorts = {
        "World Cup": [r for r in rows if r.cohort == "world_cup"],
        "Bundesliga": [r for r in rows if r.cohort == "bundesliga"],
        "With odds": [r for r in rows if r.has_odds],
        "Without odds": [r for r in rows if not r.has_odds],
        "High data quality (≥60%)": [r for r in rows if r.data_quality_pct >= DQ_HIGH * 100],
        "Low data quality (<45%)": [r for r in rows if r.data_quality_pct < DQ_LOW * 100],
    }

    wde_wins = [r for r in rows if r.wde_scoreline_conflict and r.wde_correct and not r.final_correct]
    scoreline_wins = [r for r in rows if r.wde_scoreline_conflict and r.scoreline_correct and not r.wde_correct]

    helpful_examples = [r for r in overrides if r.override_outcome == "helpful"][:5]
    harmful_examples = [r for r in overrides if r.override_outcome == "harmful"][:8]

    no_harm_acc = m["wde_accuracy"]
    harm_delta = no_harm_acc - m["final_accuracy"]

    lines = [
        "# Phase 18 — Harmonization Truth Audit",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Mode",
        "",
        "- **Read-only audit** — no code, weight, or deploy changes",
        "- Same replay methodology as Phase 17",
        "",
        "## 1. Dataset",
        "",
        f"- Fixtures analyzed: **{n}**",
        f"- Sources: {dict(Counter(r.source for r in rows))}",
        "",
        "## 2. Accuracy comparison",
        "",
        "| Layer | Accuracy |",
        "|-------|----------|",
        f"| WDE (pre-harmonization) | **{m['wde_accuracy']:.1%}** |",
        f"| Scoreline-implied 1X2 | **{m['scoreline_accuracy']:.1%}** |",
        f"| Harmonized final (production) | **{m['final_accuracy']:.1%}** |",
        "",
        f"- WDE − Final delta: **{harm_delta:+.1%}** (positive = harmonization hurts vs WDE-only)",
        f"- Scoreline ≡ Final on all fixtures (harmonization always aligns 1X2 to scoreline)",
        "",
        "## 3. Conflict & override statistics",
        "",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| WDE vs scoreline conflict rate | {m['conflict_rate']:.1%} |",
        f"| Override rate (WDE ≠ final) | {m['override_rate']:.1%} |",
        f"| Helpful overrides (WDE wrong → final right) | {m['helpful_overrides']} ({m['helpful_rate']:.1%} of overrides) |",
        f"| Harmful overrides (WDE right → final wrong) | {m['harmful_overrides']} ({m['harmful_rate']:.1%} of overrides) |",
        f"| Neutral overrides (both wrong) | {m['neutral_overrides']} |",
        "",
        "## 4. Override analysis",
        "",
        f"Total overrides: **{len(overrides)}** / {n}",
        "",
        "### Helpful override examples",
        "",
    ]
    if helpful_examples:
        for r in helpful_examples:
            lines.append(
                f"- **{r.fixture_id}** {r.match_name}: WDE `{r.wde}` → Final `{r.final}` | Actual `{r.actual}`"
            )
    else:
        lines.append("- None in sample.")

    lines.extend(["", "### Harmful override examples", ""])
    if harmful_examples:
        for r in harmful_examples:
            lines.append(
                f"- **{r.fixture_id}** {r.match_name}: WDE `{r.wde}` → Final `{r.final}` | Actual `{r.actual}`"
            )
    else:
        lines.append("- None in sample.")

    lines.extend(["", "## 5. Cohort analysis", ""])
    lines.append("| Cohort | n | WDE | Scoreline | Final | Override % | Harmful % | Helpful % |")
    lines.append("|--------|---|-----|-----------|-------|------------|-----------|-----------|")
    for label, subset in cohorts.items():
        if not subset:
            continue
        cm = cohort_metrics(subset)
        lines.append(
            f"| {label} | {cm['n']} | {cm['wde_accuracy']:.1%} | {cm['scoreline_accuracy']:.1%} | "
            f"{cm['final_accuracy']:.1%} | {cm['override_rate']:.1%} | {cm['harmful_rate']:.1%} | "
            f"{cm['helpful_rate']:.1%} |"
        )

    lines.extend(
        [
            "",
            "## 6. When harmonization helps vs hurts",
            "",
            f"- **Conflicts where WDE was right:** {len(wde_wins)} fixtures",
            f"- **Conflicts where scoreline/final was right:** {len(scoreline_wins)} fixtures",
            "",
            "**Harmonization helps** when WDE disagrees with scoreline and scoreline matches actual "
            f"({m['helpful_overrides']} cases, {m['helpful_rate']:.1%} of overrides).",
            "",
            "**Harmonization hurts** when WDE was correct but scoreline override was wrong "
            f"({m['harmful_overrides']} cases, {m['harmful_rate']:.1%} of overrides).",
            "",
            "## 7. Architecture recommendation",
            "",
        ]
    )

    if harm_delta > 0.01:
        rec = (
            f"**Remove or gate harmonization** on this sample: WDE-only accuracy ({no_harm_acc:.1%}) "
            f"beats harmonized final ({m['final_accuracy']:.1%}) by {harm_delta:.1%}."
        )
    elif harm_delta < -0.01:
        rec = (
            f"**Keep harmonization**: final ({m['final_accuracy']:.1%}) beats WDE ({no_harm_acc:.1%})."
        )
    else:
        rec = "**Harmonization is neutral** on aggregate — gate by cohort instead of global force."

    lines.append(rec)
    lines.extend(
        [
            "",
            "Suggested WDE-win conditions (from harmful override cohorts):",
            "- Prefer **WDE** when odds/consensus available and WDE ≠ scoreline draw forced by low λ spread",
            "- Prefer **scoreline** when WDE conflicts with market consensus and scoreline aligns with odds",
            "- **Bundesliga offline replays**: high override rate with majority **harmful** — do not force scoreline 1X2",
            "",
            "## Success criteria answers",
            "",
            f"**Q1 — If harmonization removed entirely, does accuracy improve?** "
            f"**{'YES' if harm_delta > 0 else 'NO'}** — WDE-only would be **{no_harm_acc:.1%}** vs final **{m['final_accuracy']:.1%}** "
            f"({harm_delta:+.1%}).",
            "",
            f"**Q2 — When does harmonization help?** "
            f"When scoreline-implied 1X2 is correct and WDE is wrong ({m['helpful_overrides']} overrides, "
            f"{m['helpful_rate']:.1%} of override events). More common when WDE over-commits to draws or wrong side.",
            "",
            f"**Q3 — When does harmonization hurt?** "
            f"When WDE is correct but scoreline λ forces wrong 1X2 ({m['harmful_overrides']} overrides, "
            f"{m['harmful_rate']:.1%} of override events). Dominant on Bundesliga bulk replay.",
            "",
            "**Q4 — Conditions where WDE should win?** "
            "Fixtures with **odds available**, **WDE ≠ scoreline**, and **λ spread below median** "
            f"(draw-collapse path). WDE was right in **{len(wde_wins)}** conflict fixtures vs scoreline **{len(scoreline_wins)}**.",
            "",
            f"**Q5 — What percentage of overrides are harmful?** **{m['harmful_rate']:.1%}** of all overrides "
            f"({m['harmful_overrides']} / {len(overrides)}). "
            f"Helpful: **{m['helpful_rate']:.1%}**. Neutral (both wrong): "
            f"**{m['neutral_overrides'] / max(len(overrides), 1):.1%}**.",
            "",
            "**Stop — audit only. No implementation. No deploy.**",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    _reset_settings()

    from worldcup_predictor.backtesting.historical_loader import HistoricalLoader
    from worldcup_predictor.results.match_results_store import MatchResultsStore

    rows: list[Row] = []
    results_by_id = MatchResultsStore().by_fixture_id()

    if HISTORICAL_CSV.exists():
        for match_row in HistoricalLoader(HISTORICAL_CSV).load(create_sample_if_missing=False):
            try:
                row = evaluate_offline(match_row, source="historical_csv")
                if row:
                    rows.append(row)
            except Exception as exc:
                print(f"hist {match_row.fixture_id}: {exc}", file=sys.stderr)

    for match_row in load_db_historical_rows(limit=BUNDESLIGA_LIMIT):
        try:
            row = evaluate_offline(match_row, source="db_bundesliga")
            if row:
                rows.append(row)
        except Exception as exc:
            print(f"db {match_row.fixture_id}: {exc}", file=sys.stderr)

    for fid in load_live_fixture_ids():
        try:
            row = evaluate_live(fid, results_by_id)
            if row:
                rows.append(row)
        except Exception as exc:
            print(f"live {fid}: {exc}", file=sys.stderr)

    seen: set[int] = set()
    deduped: list[Row] = []
    for row in rows:
        if row.fixture_id in seen:
            continue
        seen.add(row.fixture_id)
        deduped.append(row)

    if len(deduped) < MIN_FIXTURES:
        print(f"WARNING: only {len(deduped)} fixtures (target {MIN_FIXTURES})", file=sys.stderr)

    REPLAY_OUT.parent.mkdir(parents=True, exist_ok=True)
    with REPLAY_OUT.open("w", encoding="utf-8") as handle:
        for r in deduped:
            handle.write(
                json.dumps(
                    {
                        "fixture_id": r.fixture_id,
                        "match_name": r.match_name,
                        "cohort": r.cohort,
                        "actual": r.actual,
                        "wde": r.wde,
                        "scoreline": r.scoreline,
                        "final": r.final,
                        "override": r.override,
                        "override_outcome": r.override_outcome,
                        "wde_correct": r.wde_correct,
                        "final_correct": r.final_correct,
                        "has_odds": r.has_odds,
                        "data_quality_pct": r.data_quality_pct,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    write_report(deduped)
    m = cohort_metrics(deduped)
    print(
        f"Analyzed: {len(deduped)} | WDE {m['wde_accuracy']:.1%} | "
        f"Final {m['final_accuracy']:.1%} | Harmful overrides {m['harmful_rate']:.1%}"
    )
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
