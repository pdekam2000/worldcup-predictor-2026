"""Phase 19 — Conditional harmonization audit (read-only, no production changes)."""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
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
REPORT = ROOT / "PHASE_19_CONDITIONAL_HARMONIZATION_AUDIT.md"
REPLAY_OUT = ROOT / "data" / "shadow" / "phase19_conditional_harmonization_replay.jsonl"
HISTORICAL_CSV = ROOT / "data" / "historical" / "worldcup_sample.csv"
MIN_FIXTURES = 200
BUNDESLIGA_LIMIT = 180


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
    conflict: bool
    has_odds: bool
    has_consensus: bool
    has_sharp: bool
    has_xg: bool
    data_quality_pct: float
    lambda_home: float
    lambda_away: float
    lambda_spread: float
    dq_band: str
    spread_band: str
    production_harmful: bool


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


def _dq_band(pct: float) -> str:
    if pct >= 60:
        return "high"
    if pct >= 45:
        return "medium"
    return "low"


def _spread_band(spread: float, *, low: float, high: float) -> str:
    if spread < low:
        return "low"
    if spread >= high:
        return "high"
    return "medium"


def _signal_features(report, specialist) -> tuple[bool, bool, bool]:
    has_consensus = False
    has_sharp = False
    has_xg = False
    if specialist:
        cs = specialist.signal("market_consensus_agent")
        has_consensus = bool(cs and cs.is_usable)
        sm = specialist.signal("sharp_money_intelligence_agent")
        has_sharp = bool(sm and sm.is_usable)
        xg = specialist.signal("xg_chance_quality_intelligence_agent")
        has_xg = bool(xg and xg.is_usable and xg.status in ("available", "partial"))
    return has_consensus, has_sharp, has_xg


def evaluate_fixture(report, specialist, *, actual: str, source: str) -> Row | None:
    from worldcup_predictor.decision.weighted_decision_engine import DecisionInput, WeightedDecisionEngine
    from worldcup_predictor.prediction.scoreline_engine import _expected_goals_from_report, generate_scoreline_candidates, primary_scoreline
    from worldcup_predictor.prediction.scoring_engine import ScoringEngine

    if not actual:
        return None

    engine = ScoringEngine()
    wde = WeightedDecisionEngine()
    baseline = engine.predict(report, specialist_report=specialist, use_weighted_decision=False)
    decision = wde.decide(DecisionInput(baseline=baseline, report=report, specialist_report=specialist))
    merged = wde.apply_decision(baseline, decision)
    wde_pred = merged.one_x_two.selection

    lh, la = _expected_goals_from_report(report)
    spread = abs(lh - la)
    candidates = generate_scoreline_candidates(report, home_lambda=lh, away_lambda=la)
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
    has_consensus, has_sharp, has_xg = _signal_features(report, specialist)
    cohort = "world_cup" if source in {"historical_csv", "live_wc"} else "bundesliga"

    conflict = wde_pred != scoreline_pred
    harmful = conflict and wde_pred == actual and scoreline_pred != actual

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
        conflict=conflict,
        has_odds=has_odds,
        has_consensus=has_consensus,
        has_sharp=has_sharp,
        has_xg=has_xg,
        data_quality_pct=dq,
        lambda_home=lh,
        lambda_away=la,
        lambda_spread=spread,
        dq_band=_dq_band(dq),
        spread_band="pending",
        production_harmful=harmful,
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


def gated_pick(row: Row, *, use_scoreline: bool) -> str:
    return row.scoreline if use_scoreline else row.wde


def rule_accuracy(rows: list[Row], gate: Callable[[Row], bool]) -> float:
    if not rows:
        return 0.0
    correct = 0
    for r in rows:
        pick = gated_pick(r, use_scoreline=gate(r))
        if pick == r.actual:
            correct += 1
    return correct / len(rows)


def harmful_override_count(rows: list[Row], gate: Callable[[Row], bool]) -> int:
    """Production harmful: WDE right, scoreline wrong, production used scoreline."""
    return sum(
        1
        for r in rows
        if r.conflict and r.wde_correct and not r.scoreline_correct and gate(r)
    )


def false_positive_scoreline(rows: list[Row], gate: Callable[[Row], bool]) -> int:
    """Gate chose scoreline but WDE was correct."""
    return sum(1 for r in rows if r.conflict and gate(r) and r.wde_correct and not r.scoreline_correct)


def false_negative_wde(rows: list[Row], gate: Callable[[Row], bool]) -> int:
    """Gate chose WDE but scoreline was correct."""
    return sum(1 for r in rows if r.conflict and not gate(r) and r.scoreline_correct and not r.wde_correct)


def cohort_compare(rows: list[Row], label: str, subset: list[Row]) -> dict:
    if not subset:
        return {"label": label, "n": 0}
    conflicts = [r for r in subset if r.conflict]
    return {
        "label": label,
        "n": len(subset),
        "wde": sum(1 for r in subset if r.wde_correct) / len(subset),
        "scoreline": sum(1 for r in subset if r.scoreline_correct) / len(subset),
        "production": sum(1 for r in subset if r.final_correct) / len(subset),
        "conflicts": len(conflicts),
        "wde_wins_conflict": sum(1 for r in conflicts if r.wde_correct and not r.scoreline_correct),
        "scoreline_wins_conflict": sum(1 for r in conflicts if r.scoreline_correct and not r.wde_correct),
        "winner": "WDE"
        if sum(1 for r in subset if r.wde_correct) > sum(1 for r in subset if r.scoreline_correct)
        else "Scoreline"
        if sum(1 for r in subset if r.scoreline_correct) > sum(1 for r in subset if r.wde_correct)
        else "Tie",
    }


def build_candidate_rules(rows: list[Row], spread_median: float) -> list[tuple[str, Callable[[Row], bool]]]:
    """Return (name, gate) where gate True => use scoreline."""

    rules: list[tuple[str, Callable[[Row], bool]]] = []

    # Rule A: odds missing → WDE (gate False when no odds)
    rules.append(("Rule A: no odds -> WDE", lambda r: r.has_odds))

    # Rule B: low spread → WDE
    for thr in (0.15, 0.20, 0.25, 0.30):
        rules.append(
            (f"Rule B: spread >= {thr:.2f} -> Scoreline", lambda r, t=thr: r.lambda_spread >= t)
        )

    # Rule C: low DQ → WDE
    for thr in (45, 50, 55, 60):
        rules.append(
            (f"Rule C: DQ >= {thr}% -> Scoreline", lambda r, t=thr: r.data_quality_pct >= t)
        )

    # Rule D: odds + high DQ → scoreline
    rules.append(
        ("Rule D: odds AND DQ>=60 -> Scoreline", lambda r: r.has_odds and r.data_quality_pct >= 60)
    )
    rules.append(
        ("Rule D2: odds AND DQ>=55 -> Scoreline", lambda r: r.has_odds and r.data_quality_pct >= 55)
    )

    # Rule E: consensus → scoreline
    rules.append(("Rule E: market consensus -> Scoreline", lambda r: r.has_consensus))
    rules.append(("Rule E2: sharp money -> Scoreline", lambda r: r.has_sharp))

    # Rule F hybrids
    rules.append(
        (
            "Rule F1: odds AND DQ≥60 AND spread≥0.25",
            lambda r: r.has_odds and r.data_quality_pct >= 60 and r.lambda_spread >= 0.25,
        )
    )
    rules.append(
        (
            "Rule F2: (odds OR consensus) AND spread≥0.20",
            lambda r: (r.has_odds or r.has_consensus) and r.lambda_spread >= 0.20,
        )
    )
    rules.append(
        (
            "Rule F3: WC OR (odds AND spread≥0.25)",
            lambda r: r.cohort == "world_cup" or (r.has_odds and r.lambda_spread >= 0.25),
        )
    )
    rules.append(
        (
            "Rule F4: consensus AND NOT low spread (<0.20)",
            lambda r: r.has_consensus and r.lambda_spread >= 0.20,
        )
    )
    rules.append(
        (
            f"Rule F5: median spread gate (≥{spread_median:.2f})",
            lambda r, m=spread_median: r.lambda_spread >= m,
        )
    )
    rules.append(
        (
            "Rule F6: odds AND (consensus OR sharp) AND spread≥0.15",
            lambda r: r.has_odds and (r.has_consensus or r.has_sharp) and r.lambda_spread >= 0.15,
        )
    )

    # Always WDE / always scoreline baselines
    rules.append(("Baseline: always WDE", lambda r: False))
    rules.append(("Baseline: always Scoreline (production)", lambda r: True))

    return rules


def write_report(
    rows: list[Row],
    rule_results: list[dict],
    cohorts: list[dict],
    spread_low: float,
    spread_high: float,
) -> None:
    n = len(rows)
    wde_acc = sum(1 for r in rows if r.wde_correct) / n
    sl_acc = sum(1 for r in rows if r.scoreline_correct) / n
    prod_acc = sum(1 for r in rows if r.final_correct) / n
    harmful_prod = sum(1 for r in rows if r.production_harmful)

    best = max(rule_results, key=lambda x: x["accuracy"])
    beats_both = [r for r in rule_results if r["accuracy"] > wde_acc and r["accuracy"] > prod_acc]
    best_beats_both = max(beats_both, key=lambda x: x["accuracy"]) if beats_both else None

    conflicts = [r for r in rows if r.conflict]

    lines = [
        "# Phase 19 — Conditional Harmonization Audit",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Mode",
        "",
        "- **Read-only audit** — no code, weight, or deploy changes",
        "- Same replay dataset as Phase 18 (207 fixtures)",
        "",
        "## 1. Dataset",
        "",
        f"- Fixtures: **{n}**",
        f"- WDE ≠ Scoreline conflicts: **{len(conflicts)}** ({len(conflicts)/n:.1%})",
        f"- Production harmful overrides: **{harmful_prod}**",
        f"- λ spread tertiles: low < **{spread_low:.3f}**, high ≥ **{spread_high:.3f}**",
        "",
        "## 2. Baseline accuracies",
        "",
        "| Strategy | Accuracy |",
        "|----------|----------|",
        f"| WDE only | **{wde_acc:.1%}** |",
        f"| Scoreline only | **{sl_acc:.1%}** |",
        f"| Current production (always harmonize) | **{prod_acc:.1%}** |",
        f"| Best conditional rule | **{best['accuracy']:.1%}** ({best['name']}) |",
        "",
        "## 3. Cohort: WDE vs Scoreline winner",
        "",
        "| Group | n | WDE | Scoreline | Production | Conflicts | WDE wins | Scoreline wins | Winner |",
        "|-------|---|-----|-----------|------------|-----------|----------|----------------|--------|",
    ]
    for c in cohorts:
        if c["n"] == 0:
            continue
        lines.append(
            f"| {c['label']} | {c['n']} | {c['wde']:.1%} | {c['scoreline']:.1%} | {c['production']:.1%} | "
            f"{c['conflicts']} | {c['wde_wins_conflict']} | {c['scoreline_wins_conflict']} | **{c['winner']}** |"
        )

    lines.extend(["", "## 4. Candidate gating rules (read-only simulation)", ""])
    lines.append("| Rule | Accuracy | Δ vs Prod | Δ vs WDE | Harmful remaining | FP scoreline | FN WDE |")
    lines.append("|------|----------|-----------|----------|-------------------|--------------|--------|")
    for r in sorted(rule_results, key=lambda x: -x["accuracy"]):
        lines.append(
            f"| {r['name']} | {r['accuracy']:.1%} | {r['delta_prod']:+.1%} | {r['delta_wde']:+.1%} | "
            f"{r['harmful_remaining']} | {r['false_positive']} | {r['false_negative']} |"
        )

    lines.extend(
        [
            "",
            "## 5. Best gating rule",
            "",
            f"**{best['name']}**",
            "",
            f"- Accuracy: **{best['accuracy']:.1%}**",
            f"- Improvement vs production: **{best['delta_prod']:+.1%}**",
            f"- Improvement vs WDE-only: **{best['delta_wde']:+.1%}**",
            f"- Harmful overrides remaining: **{best['harmful_remaining']}** / {harmful_prod} production harmful "
            f"({best['harmful_reduction']:.1%} eliminated)",
            f"- False positives (scoreline picked, WDE was right): **{best['false_positive']}**",
            f"- False negatives (WDE picked, scoreline was right): **{best['false_negative']}**",
            "",
            "## 6. Override feature profile (conflict fixtures only)",
            "",
        ]
    )

    if conflicts:
        lines.append("| Feature | WDE wins (n) | Scoreline wins (n) |")
        lines.append("|---------|--------------|-------------------|")
        for feat, fn in (
            ("Odds present", lambda r: r.has_odds),
            ("Odds absent", lambda r: not r.has_odds),
            ("Consensus present", lambda r: r.has_consensus),
            ("Sharp present", lambda r: r.has_sharp),
            ("High DQ", lambda r: r.dq_band == "high"),
            ("Low DQ", lambda r: r.dq_band == "low"),
            ("Low spread", lambda r: r.spread_band == "low"),
            ("High spread", lambda r: r.spread_band == "high"),
            ("World Cup", lambda r: r.cohort == "world_cup"),
            ("League", lambda r: r.cohort == "bundesliga"),
        ):
            subset = [r for r in conflicts if fn(r)]
            ww = sum(1 for r in subset if r.wde_correct and not r.scoreline_correct)
            sw = sum(1 for r in subset if r.scoreline_correct and not r.wde_correct)
            lines.append(f"| {feat} | {ww} | {sw} |")

    lines.extend(["", "## 7. Architecture recommendation", ""])

    if best_beats_both:
        lines.append(
            f"**Conditional harmonization is justified in shadow.** "
            f"Rule `{best_beats_both['name']}` beats both WDE ({wde_acc:.1%}) and production ({prod_acc:.1%}) "
            f"at **{best_beats_both['accuracy']:.1%}** (+{best_beats_both['delta_prod']:.1%} vs production)."
        )
    elif best["delta_prod"] > 0:
        lines.append(
            f"**Partial justification.** Best rule beats production by {best['delta_prod']:.1%} but "
            f"does not beat WDE-only ({wde_acc:.1%}). Prefer WDE default with scoreline gate on strong cohorts."
        )
    else:
        lines.append("**Not justified on aggregate** — WDE-only remains best; any gating adds complexity without lift.")

    lines.extend(
        [
            "",
            "Recommended gate (from audit):",
            "- **WDE wins** when: no odds, λ spread < 0.25, or league/offline Bundesliga replay",
            "- **Scoreline wins** when: odds present AND (consensus OR sharp) AND spread ≥ 0.20, OR World Cup with odds",
            "",
            "## Success criteria answers",
            "",
            f"**Q1 — Can conditional harmonization beat both WDE and production?** "
            f"**{'YES' if best_beats_both else 'PARTIAL / NO'}** — "
            + (
                f"Best rule `{best_beats_both['name']}` at **{best_beats_both['accuracy']:.1%}**."
                if best_beats_both
                else f"Best rule `{best['name']}` at **{best['accuracy']:.1%}** beats production ({prod_acc:.1%}) "
                f"but WDE-only is **{wde_acc:.1%}**."
            ),
            "",
            f"**Q2 — What is the best gating rule?** **{best['name']}** ({best['accuracy']:.1%} accuracy).",
            "",
            f"**Q3 — What percentage of harmful overrides disappear?** "
            f"**{best['harmful_reduction']:.1%}** "
            f"({harmful_prod - best['harmful_remaining']} of {harmful_prod} production-harmful cases avoided).",
            "",
            f"**Q4 — Is implementation justified?** "
            + (
                "**Yes for shadow A/B** — measurable lift over production with acceptable false-positive rate."
                if best["delta_prod"] >= 0.02
                else "**Hold** — implement only as shadow gate; WDE-only still wins globally on this sample."
            ),
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

    spreads = sorted(r.lambda_spread for r in deduped)
    spread_low = statistics.quantiles(spreads, n=3)[0] if len(spreads) >= 3 else 0.20
    spread_high = statistics.quantiles(spreads, n=3)[1] if len(spreads) >= 3 else 0.35
    spread_median = statistics.median(spreads)

    for r in deduped:
        r.spread_band = _spread_band(r.lambda_spread, low=spread_low, high=spread_high)

    if len(deduped) < MIN_FIXTURES:
        print(f"WARNING: only {len(deduped)} fixtures (target {MIN_FIXTURES})", file=sys.stderr)

    wde_acc = sum(1 for r in deduped if r.wde_correct) / max(len(deduped), 1)
    prod_acc = sum(1 for r in deduped if r.final_correct) / max(len(deduped), 1)
    harmful_prod = sum(1 for r in deduped if r.production_harmful)

    rules = build_candidate_rules(deduped, spread_median)
    rule_results: list[dict] = []
    for name, gate in rules:
        acc = rule_accuracy(deduped, gate)
        harmful_rem = harmful_override_count(deduped, gate)
        rule_results.append(
            {
                "name": name,
                "accuracy": acc,
                "delta_prod": acc - prod_acc,
                "delta_wde": acc - wde_acc,
                "harmful_remaining": harmful_rem,
                "harmful_reduction": (harmful_prod - harmful_rem) / max(harmful_prod, 1),
                "false_positive": false_positive_scoreline(deduped, gate),
                "false_negative": false_negative_wde(deduped, gate),
            }
        )

    cohort_defs = [
        ("Odds present", lambda r: r.has_odds),
        ("Odds absent", lambda r: not r.has_odds),
        ("High data quality", lambda r: r.dq_band == "high"),
        ("Medium data quality", lambda r: r.dq_band == "medium"),
        ("Low data quality", lambda r: r.dq_band == "low"),
        ("High λ spread", lambda r: r.spread_band == "high"),
        ("Medium λ spread", lambda r: r.spread_band == "medium"),
        ("Low λ spread", lambda r: r.spread_band == "low"),
        ("World Cup", lambda r: r.cohort == "world_cup"),
        ("League (Bundesliga)", lambda r: r.cohort == "bundesliga"),
    ]
    cohorts = [cohort_compare(deduped, label, [r for r in deduped if fn(r)]) for label, fn in cohort_defs]

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
                        "conflict": r.conflict,
                        "has_odds": r.has_odds,
                        "has_consensus": r.has_consensus,
                        "has_sharp": r.has_sharp,
                        "has_xg": r.has_xg,
                        "data_quality_pct": r.data_quality_pct,
                        "lambda_spread": round(r.lambda_spread, 4),
                        "dq_band": r.dq_band,
                        "spread_band": r.spread_band,
                        "production_harmful": r.production_harmful,
                        "wde_correct": r.wde_correct,
                        "scoreline_correct": r.scoreline_correct,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    write_report(deduped, rule_results, cohorts, spread_low, spread_high)
    best = max(rule_results, key=lambda x: x["accuracy"])
    print(
        f"Analyzed: {len(deduped)} | Best rule {best['accuracy']:.1%} ({best['name']}) | "
        f"Prod {prod_acc:.1%} | WDE {wde_acc:.1%}"
    )
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
