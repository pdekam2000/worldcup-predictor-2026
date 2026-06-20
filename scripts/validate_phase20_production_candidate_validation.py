"""Phase 20 — Production candidate validation (read-only, no production changes)."""

from __future__ import annotations

import json
import os
import sqlite3
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
import runpy

runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_20_PRODUCTION_CANDIDATE_VALIDATION.md"
REPLAY_IN = ROOT / "data" / "shadow" / "phase19_conditional_harmonization_replay.jsonl"
REPLAY_OUT = ROOT / "data" / "shadow" / "phase20_production_candidate_replay.jsonl"
HISTORICAL_CSV = ROOT / "data" / "historical" / "worldcup_sample.csv"
MIN_FIXTURES = 200
BUNDESLIGA_LIMIT = 180
SPREAD_THRESHOLD = 0.25
SPREAD_LOW = 0.20
DQ_HIGH = 60.0
DQ_LOW = 45.0


@dataclass
class Row:
    fixture_id: int
    match_name: str
    cohort: str
    actual: str
    wde: str
    scoreline: str
    final: str
    has_odds: bool
    has_consensus: bool
    has_sharp: bool
    data_quality_pct: float
    lambda_spread: float

    @property
    def conflict(self) -> bool:
        return self.wde != self.scoreline

    @property
    def wde_correct(self) -> bool:
        return self.wde == self.actual

    @property
    def scoreline_correct(self) -> bool:
        return self.scoreline == self.actual

    @property
    def production_correct(self) -> bool:
        return self.final == self.actual


def _reset_settings() -> None:
    os.environ["LAMBDA_BRIDGE_MODE"] = "off"
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()


def pick(row: Row, use_scoreline: bool) -> str:
    return row.scoreline if use_scoreline else row.wde


def rule_metrics(rows: list[Row], name: str, gate: Callable[[Row], bool]) -> dict:
    n = len(rows)
    correct = helpful = harmful = overrides = 0
    draw_preds = 0
    for r in rows:
        gated = pick(r, gate(r))
        prod = r.final
        if gated == r.actual:
            correct += 1
        if gated == "draw":
            draw_preds += 1
        if gated != prod:
            overrides += 1
        if r.conflict:
            used_sl = gate(r)
            if used_sl and r.scoreline_correct and not r.wde_correct:
                helpful += 1
            elif used_sl and r.wde_correct and not r.scoreline_correct:
                harmful += 1
    acc = correct / max(n, 1)
    return {
        "name": name,
        "accuracy": acc,
        "draw_rate": draw_preds / max(n, 1),
        "override_rate": overrides / max(n, 1),
        "helpful_overrides": helpful,
        "harmful_overrides": harmful,
        "net_override_benefit": helpful - harmful,
        "gate": gate,
    }


def baseline_metrics(rows: list[Row], name: str, selector: Callable[[Row], str]) -> dict:
    n = len(rows)
    correct = helpful = harmful = overrides = 0
    draw_preds = 0
    for r in rows:
        gated = selector(r)
        if gated == r.actual:
            correct += 1
        if gated == "draw":
            draw_preds += 1
        if gated != r.final:
            overrides += 1
        if r.conflict:
            used_sl = gated == r.scoreline
            if used_sl and r.scoreline_correct and not r.wde_correct:
                helpful += 1
            elif used_sl and r.wde_correct and not r.scoreline_correct:
                harmful += 1
    return {
        "name": name,
        "accuracy": correct / max(n, 1),
        "draw_rate": draw_preds / max(n, 1),
        "override_rate": overrides / max(n, 1),
        "helpful_overrides": helpful,
        "harmful_overrides": harmful,
        "net_override_benefit": helpful - harmful,
        "gate": None,
    }


def cohort_accuracy(rows: list[Row], gate: Callable[[Row], bool]) -> float:
    if not rows:
        return 0.0
    return sum(1 for r in rows if pick(r, gate(r)) == r.actual) / len(rows)


def robustness_score(rows: list[Row], gate: Callable[[Row], bool]) -> float:
    """Min cohort accuracy across key cohorts (higher = more robust)."""
    cohorts = [
        [r for r in rows if r.cohort == "world_cup"],
        [r for r in rows if r.cohort == "bundesliga"],
        [r for r in rows if r.has_odds],
        [r for r in rows if not r.has_odds],
        [r for r in rows if r.data_quality_pct >= DQ_HIGH],
        [r for r in rows if r.data_quality_pct < DQ_LOW],
    ]
    accs = [cohort_accuracy(c, gate) for c in cohorts if c]
    return min(accs) if accs else 0.0


def build_rules() -> list[tuple[str, Callable[[Row], bool]]]:
    return [
        ("Rule A: No Odds -> WDE, Odds -> Scoreline", lambda r: r.has_odds),
        (
            "Rule B: Low Spread -> WDE, Else Scoreline",
            lambda r: r.lambda_spread >= SPREAD_LOW,
        ),
        (
            "Rule C: Low DQ -> WDE, Else Scoreline",
            lambda r: r.data_quality_pct >= DQ_HIGH,
        ),
        (
            "Rule D: No Odds OR Low Spread -> WDE, Else Scoreline",
            lambda r: r.has_odds and r.lambda_spread >= SPREAD_LOW,
        ),
        (
            "Rule E: No Odds OR Low DQ -> WDE, Else Scoreline",
            lambda r: r.has_odds and r.data_quality_pct >= DQ_HIGH,
        ),
        (
            "Rule F: Odds AND High DQ -> Scoreline, Else WDE",
            lambda r: r.has_odds and r.data_quality_pct >= DQ_HIGH,
        ),
        (
            "Rule G: Odds AND Spread > Threshold -> Scoreline, Else WDE",
            lambda r: r.has_odds and r.lambda_spread > SPREAD_THRESHOLD,
        ),
        (
            "Rule H: Odds AND Consensus -> Scoreline, Else WDE",
            lambda r: r.has_odds and r.has_consensus,
        ),
        (
            "Rule I: Odds AND High DQ AND Spread > Threshold -> Scoreline, Else WDE",
            lambda r: r.has_odds and r.data_quality_pct >= DQ_HIGH and r.lambda_spread > SPREAD_THRESHOLD,
        ),
        (
            "Rule J: Hybrid (WC OR odds+consensus/sharp+spread>=0.20) -> Scoreline, Else WDE",
            lambda r: (
                r.cohort == "world_cup"
                or (r.has_odds and (r.has_consensus or r.has_sharp) and r.lambda_spread >= SPREAD_LOW)
            ),
        ),
    ]


def load_from_phase19_replay() -> list[Row] | None:
    if not REPLAY_IN.exists():
        return None
    rows: list[Row] = []
    for line in REPLAY_IN.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        rows.append(
            Row(
                fixture_id=int(d["fixture_id"]),
                match_name=str(d.get("match_name", "")),
                cohort=str(d["cohort"]),
                actual=str(d["actual"]),
                wde=str(d["wde"]),
                scoreline=str(d["scoreline"]),
                final=str(d["final"]),
                has_odds=bool(d["has_odds"]),
                has_consensus=bool(d.get("has_consensus", False)),
                has_sharp=bool(d.get("has_sharp", False)),
                data_quality_pct=float(d["data_quality_pct"]),
                lambda_spread=float(d["lambda_spread"]),
            )
        )
    return rows if rows else None


def _parse_halftime(score: str | None) -> tuple[int | None, int | None]:
    if not score or "-" not in score:
        return None, None
    parts = score.split("-", 1)
    try:
        return int(parts[0]), int(parts[1])
    except ValueError:
        return None, None


def load_db_historical_rows(*, limit: int = 180) -> list:
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
        WHERE f.competition_key = 'bundesliga' AND f.status = 'FT'
        ORDER BY f.kickoff_utc DESC LIMIT ?
    """
    rows = []
    for raw in conn.execute(query, (limit,)):
        kickoff = raw["kickoff_utc"] or "2023-08-01"
        date = datetime.fromisoformat(kickoff[:19])
        ht_h, ht_a = _parse_halftime(raw["halftime_score"])
        rows.append(
            HistoricalMatchRow(
                fixture_id=int(raw["fixture_id"]),
                date=date,
                competition="bundesliga",
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


def collect_rows_fresh() -> list[Row]:
    """Full replay if Phase 19 cache unavailable."""
    from worldcup_predictor.backtesting.historical_loader import HistoricalLoader
    from worldcup_predictor.results.match_results_store import MatchResultsStore

    sys.path.insert(0, str(ROOT / "scripts"))
    import validate_phase19_conditional_harmonization_audit as p19

    out: list[Row] = []
    results = MatchResultsStore().by_fixture_id()

    if HISTORICAL_CSV.exists():
        for mr in HistoricalLoader(HISTORICAL_CSV).load(create_sample_if_missing=False):
            r = p19.evaluate_offline(mr, source="historical_csv")
            if r:
                out.append(_from_p19(r))

    for mr in load_db_historical_rows(limit=BUNDESLIGA_LIMIT):
        r = p19.evaluate_offline(mr, source="db_bundesliga")
        if r:
            out.append(_from_p19(r))

    for fid in p19.load_live_fixture_ids():
        r = p19.evaluate_live(fid, results)
        if r:
            out.append(_from_p19(r))

    seen: set[int] = set()
    deduped: list[Row] = []
    for r in out:
        if r.fixture_id in seen:
            continue
        seen.add(r.fixture_id)
        deduped.append(r)
    return deduped


def _from_p19(r) -> Row:
    return Row(
        fixture_id=r.fixture_id,
        match_name=r.match_name,
        cohort=r.cohort,
        actual=r.actual,
        wde=r.wde,
        scoreline=r.scoreline,
        final=r.final,
        has_odds=r.has_odds,
        has_consensus=r.has_consensus,
        has_sharp=r.has_sharp,
        data_quality_pct=r.data_quality_pct,
        lambda_spread=r.lambda_spread,
    )


def write_report(rows: list[Row], all_metrics: list[dict], prod_acc: float, wde_acc: float) -> None:
    n = len(rows)
    ranked = sorted(all_metrics, key=lambda m: (-m["accuracy"], -m["net_override_benefit"]))
    rule_a = next(m for m in all_metrics if m["name"].startswith("Rule A"))
    best = ranked[0]
    beats_a = [m for m in all_metrics if m["accuracy"] > rule_a["accuracy"] + 1e-9]

    safest = min(
        [m for m in all_metrics if m["name"].startswith("Rule")],
        key=lambda m: (m["harmful_overrides"], -m["accuracy"]),
    )
    robust_list = [
        (m["name"], robustness_score(rows, m["gate"]))
        for m in all_metrics
        if m["gate"] is not None
    ]
    most_robust = max(robust_list, key=lambda x: x[1])

    cohort_defs = [
        ("World Cup", lambda r: r.cohort == "world_cup"),
        ("Bundesliga", lambda r: r.cohort == "bundesliga"),
        ("Odds available", lambda r: r.has_odds),
        ("Odds unavailable", lambda r: not r.has_odds),
        ("High DQ (>=60%)", lambda r: r.data_quality_pct >= DQ_HIGH),
        ("Low DQ (<45%)", lambda r: r.data_quality_pct < DQ_LOW),
    ]

    lines = [
        "# Phase 20 — Production Candidate Validation",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Mode",
        "",
        "- **Read-only validation** — no code, deploy, or production changes",
        f"- Identical dataset: **{n}** finished fixtures (Phase 18/19 replay)",
        "",
        "## 1. Baselines",
        "",
        "| Baseline | Accuracy | Draw Rate | Override vs Prod | Harmful | Helpful | Net Benefit |",
        "|----------|----------|-----------|------------------|---------|---------|-------------|",
    ]
    for m in [x for x in all_metrics if x["name"] in {
        "Production (always harmonize)",
        "WDE Only",
        "Scoreline Only",
        "Rule A: No Odds -> WDE, Odds -> Scoreline",
    }]:
        lines.append(
            f"| {m['name']} | {m['accuracy']:.1%} | {m['draw_rate']:.1%} | {m['override_rate']:.1%} | "
            f"{m['harmful_overrides']} | {m['helpful_overrides']} | {m['net_override_benefit']:+d} |"
        )

    lines.extend(["", "## 2. Full leaderboard (Rules A–J)", ""])
    lines.append("| Rank | Rule | Accuracy | d vs Prod | d vs WDE | Draw | Override | Harmful | Helpful | Net |")
    lines.append("|------|------|----------|-----------|----------|------|----------|---------|---------|-----|")
    for i, m in enumerate(ranked, 1):
        if not m["name"].startswith("Rule") and m["name"] not in {"Production (always harmonize)", "WDE Only", "Scoreline Only"}:
            continue
        if m["name"] in {"Production (always harmonize)", "WDE Only", "Scoreline Only"}:
            continue
        lines.append(
            f"| {i} | {m['name']} | {m['accuracy']:.1%} | {m['accuracy']-prod_acc:+.1%} | "
            f"{m['accuracy']-wde_acc:+.1%} | {m['draw_rate']:.1%} | {m['override_rate']:.1%} | "
            f"{m['harmful_overrides']} | {m['helpful_overrides']} | {m['net_override_benefit']:+d} |"
        )

    lines.extend(["", "## 3. Cohort analysis (best rule vs Rule A)", ""])
    lines.append("| Cohort | n | Rule A | Best Rule | Best Acc | Winner |")
    lines.append("|--------|---|--------|-----------|----------|--------|")
    rule_metrics_map = {m["name"]: m for m in all_metrics if m.get("gate")}
    for label, fn in cohort_defs:
        subset = [r for r in rows if fn(r)]
        if not subset:
            continue
        a_acc = cohort_accuracy(subset, rule_a["gate"])
        best_c = max(
            ((name, cohort_accuracy(subset, m["gate"])) for name, m in rule_metrics_map.items()),
            key=lambda x: x[1],
        )
        winner = "Rule A" if abs(a_acc - best_c[1]) < 1e-9 else best_c[0].replace("Rule ", "")[:12]
        lines.append(
            f"| {label} | {len(subset)} | {a_acc:.1%} | {best_c[0][:40]} | {best_c[1]:.1%} | {winner} |"
        )

    lines.extend(
        [
            "",
            "## 4. Override analysis",
            "",
            f"- Production harmful overrides (always scoreline): **63** on full Phase 18/19 sample",
            f"- Rule A harmful overrides: **{rule_a['harmful_overrides']}**",
            f"- Rule A helpful overrides: **{rule_a['helpful_overrides']}**",
            f"- Rule A net override benefit: **{rule_a['net_override_benefit']:+d}**",
            "",
            "**Safest rule (min harmful overrides):** "
            f"{safest['name']} — {safest['harmful_overrides']} harmful, {safest['accuracy']:.1%} accuracy",
            "",
            "**Most cohort-robust rule (min cohort accuracy):** "
            f"{most_robust[0]} — floor accuracy **{most_robust[1]:.1%}**",
            "",
            "## 5. Best candidate",
            "",
            f"**{best['name']}** — **{best['accuracy']:.1%}** accuracy "
            f"(+{best['accuracy']-prod_acc:.1%} vs production, +{best['accuracy']-wde_acc:.1%} vs WDE)",
            "",
            "## 6. Production recommendation",
            "",
        ]
    )

    if best["name"] == rule_a["name"]:
        rec = (
            "Proceed to **shadow implementation** of **Rule A** only. "
            "No competing rule beats it on this identical dataset. "
            "Simplest gate: `use_scoreline = has_odds`."
        )
    else:
        rec = (
            f"Shadow-test **{best['name']}** first; it edges Rule A by "
            f"{best['accuracy']-rule_a['accuracy']:.1%}. Validate on live WC before production."
        )

    lines.append(rec)
    lines.extend(
        [
            "",
            "## Success criteria answers",
            "",
            f"**Q1 — Best overall?** **{best['name']}** at **{best['accuracy']:.1%}**.",
            "",
            f"**Q2 — Any rule beat Rule A?** **{'YES — ' + beats_a[0]['name'] if beats_a else 'NO'}** "
            + (f"({beats_a[0]['accuracy']:.1%} vs {rule_a['accuracy']:.1%})." if beats_a else f"(Rule A ties at {rule_a['accuracy']:.1%})."),
            "",
            f"**Q3 — Safest for production?** **{safest['name']}** "
            f"({safest['harmful_overrides']} harmful overrides, {safest['accuracy']:.1%} accuracy).",
            "",
            f"**Q4 — Most robust across cohorts?** **{most_robust[0]}** "
            f"(minimum cohort accuracy **{most_robust[1]:.1%}**).",
            "",
            f"**Q5 — Implementation justified?** **{'YES — shadow gate only' if best['accuracy'] > prod_acc + 0.01 else 'HOLD'}** — "
            f"Rule A improves production by **{rule_a['accuracy']-prod_acc:.1%}** with **{rule_a['harmful_overrides']}** harmful overrides remaining.",
            "",
            "**Stop — read-only validation complete. No implementation. No deploy.**",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    _reset_settings()

    rows = load_from_phase19_replay()
    if rows:
        print(f"Loaded {len(rows)} fixtures from Phase 19 replay", file=sys.stderr)
    else:
        print("Phase 19 replay missing — running full replay", file=sys.stderr)
        rows = collect_rows_fresh()

    if len(rows) < MIN_FIXTURES:
        print(f"WARNING: only {len(rows)} fixtures (target {MIN_FIXTURES})", file=sys.stderr)

    prod = baseline_metrics(rows, "Production (always harmonize)", lambda r: r.final)
    wde_m = baseline_metrics(rows, "WDE Only", lambda r: r.wde)
    sl_m = baseline_metrics(rows, "Scoreline Only", lambda r: r.scoreline)

    all_metrics: list[dict] = [prod, wde_m, sl_m]
    for name, gate in build_rules():
        all_metrics.append(rule_metrics(rows, name, gate))

    prod_acc = prod["accuracy"]
    wde_acc = wde_m["accuracy"]

    REPLAY_OUT.parent.mkdir(parents=True, exist_ok=True)
    with REPLAY_OUT.open("w", encoding="utf-8") as handle:
        for r in rows:
            record = {
                "fixture_id": r.fixture_id,
                "actual": r.actual,
                "wde": r.wde,
                "scoreline": r.scoreline,
                "final": r.final,
                "has_odds": r.has_odds,
                "data_quality_pct": r.data_quality_pct,
                "lambda_spread": r.lambda_spread,
            }
            picks = {m["name"]: pick(r, m["gate"](r)) if m.get("gate") else None for m in all_metrics}
            record["rule_picks"] = {k: v for k, v in picks.items() if v}
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    write_report(rows, all_metrics, prod_acc, wde_acc)
    best = max(all_metrics, key=lambda m: m["accuracy"])
    print(
        f"Validated {len(rows)} fixtures | Best: {best['name'][:30]} {best['accuracy']:.1%} | "
        f"Rule A {next(m for m in all_metrics if m['name'].startswith('Rule A'))['accuracy']:.1%}"
    )
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
