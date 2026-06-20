"""Phase 21A — Rule A shadow validation and report (shadow only, no deploy)."""

from __future__ import annotations

import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
import runpy

runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_21A_RULE_A_SHADOW_REPORT.md"
SHADOW_PATH = ROOT / "data" / "shadow" / "rule_a_shadow.jsonl"
MIN_PREDICTIONS = 100
MIN_FINISHED = 30


def _reset_settings() -> None:
    os.environ.setdefault("RULE_A_GATE_MODE", "shadow")
    os.environ.setdefault("LAMBDA_BRIDGE_MODE", "off")
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()


def load_shadow_records() -> list[dict]:
    if not SHADOW_PATH.exists():
        return []
    rows: list[dict] = []
    for line in SHADOW_PATH.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    latest: dict[int, dict] = {}
    for row in rows:
        fid = int(row["fixture_id"])
        latest[fid] = row
    return list(latest.values())


def load_actuals() -> dict[int, str]:
    from worldcup_predictor.results.match_results_store import MatchResultsStore

    actuals: dict[int, str] = {}
    replay = ROOT / "data" / "shadow" / "phase19_conditional_harmonization_replay.jsonl"
    if replay.exists():
        for line in replay.read_text(encoding="utf-8").splitlines():
            if line.strip():
                try:
                    d = json.loads(line)
                    actuals[int(d["fixture_id"])] = str(d["actual"])
                except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                    continue
    store = MatchResultsStore()
    for fid, rec in store.by_fixture_id().items():
        actuals[fid] = rec.winner
    return actuals


def accuracy(rows: list[dict], key: str) -> float | None:
    scored = [r for r in rows if r.get("actual")]
    if not scored:
        return None
    hits = sum(1 for r in scored if r.get(key) == r["actual"])
    return hits / len(scored)


def enrich_with_results(records: list[dict], actuals: dict[int, str]) -> list[dict]:
    out: list[dict] = []
    for r in records:
        fid = int(r["fixture_id"])
        row = dict(r)
        row["actual"] = actuals.get(fid)
        out.append(row)
    return out


def write_report(
    records: list[dict],
    *,
    finished: list[dict],
    ready: bool,
) -> None:
    n = len(records)
    nf = len(finished)
    prod = accuracy(finished, "production_prediction")
    wde = accuracy(finished, "wde_prediction")
    sl = accuracy(finished, "scoreline_prediction")
    rule_a = accuracy(finished, "rule_a_prediction")

    def fmt(v: float | None) -> str:
        return f"{v:.1%}" if v is not None else "—"

    rule_a_wins = (
        rule_a is not None
        and prod is not None
        and rule_a > prod
        and (wde is None or rule_a >= wde - 0.001)
    )

    lines = [
        "# Phase 21A — Rule A Shadow Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Mode",
        "",
        "- **Shadow only** — production predictions unchanged",
        "- **No deploy**, no user-facing changes",
        f"- Shadow store: `{SHADOW_PATH.relative_to(ROOT)}`",
        "",
        "## 1. Collection status",
        "",
        f"| Metric | Count | Target |",
        f"|--------|-------|--------|",
        f"| Shadow predictions (unique fixtures) | **{n}** | 100+ |",
        f"| Finished fixtures with results | **{nf}** | 30+ |",
        f"| Ready for decision | **{'YES' if ready else 'NO'}** | |",
        "",
    ]

    if not ready:
        lines.extend(
            [
                "> **Waiting** — continue collecting live shadow predictions. "
                "Re-run this script after **100+ predictions** or **30+ finished fixtures**.",
                "",
            ]
        )

    lines.extend(
        [
            "## 2. Accuracy (finished fixtures only)",
            "",
            "| Strategy | Accuracy | n |",
            "|----------|----------|---|",
            f"| Production | {fmt(prod)} | {nf} |",
            f"| WDE only | {fmt(wde)} | {nf} |",
            f"| Scoreline only | {fmt(sl)} | {nf} |",
            f"| **Rule A shadow** | **{fmt(rule_a)}** | {nf} |",
            "",
        ]
    )

    if prod is not None and rule_a is not None:
        lines.append(f"- Rule A vs Production: **{rule_a - prod:+.1%}**")
    if wde is not None and rule_a is not None:
        lines.append(f"- Rule A vs WDE: **{rule_a - wde:+.1%}**")
    lines.append("")

    if finished:
        lines.extend(["## 3. Rule A source mix (finished)", ""])
        sources = Counter(r.get("rule_a_source", "?") for r in finished)
        for src, cnt in sources.most_common():
            lines.append(f"- `{src}`: {cnt} ({cnt/nf:.1%})")

        harmful = sum(
            1
            for r in finished
            if r.get("actual")
            and r["wde_prediction"] == r["actual"]
            and r["production_prediction"] != r["actual"]
            and r["rule_a_prediction"] == r["actual"]
        )
        lines.extend(
            [
                "",
                "## 4. Override rescue (Rule A fixed production-harmful cases)",
                "",
                f"- Cases where production wrong, WDE right, Rule A right: **{harmful}**",
                "",
            ]
        )

    lines.extend(["## 5. Phase 21B gate", ""])
    if not ready:
        lines.append("**HOLD** — insufficient shadow data.")
    elif rule_a_wins:
        lines.append(
            "**PROCEED to Phase 21B** — Rule A remains superior to production on finished shadow sample."
        )
    else:
        lines.append(
            "**ABORT activation** — Rule A does not beat production on finished shadow sample."
        )

    lines.extend(
        [
            "",
            "## Success criterion",
            "",
            f"- Rule A superior to production: **{'YES' if rule_a_wins and ready else 'PENDING' if not ready else 'NO'}**",
            "",
            "**Stop — shadow only unless Phase 21B approved.**",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load_phase19_rows():
    replay = ROOT / "data" / "shadow" / "phase19_conditional_harmonization_replay.jsonl"
    if not replay.exists():
        return []
    rows = []
    for line in replay.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)

        class R:
            pass

        r = R()
        r.fixture_id = int(d["fixture_id"])
        r.match_name = str(d.get("match_name", ""))
        r.wde = str(d["wde"])
        r.scoreline = str(d["scoreline"])
        r.final = str(d["final"])
        r.has_odds = bool(d["has_odds"])
        r.data_quality_pct = float(d["data_quality_pct"])
        rows.append(r)
    return rows


def bootstrap_from_replay() -> int:
    """Seed shadow store from Phase 19 replay (audit bootstrap; live shadow append continues separately)."""
    _reset_settings()
    from worldcup_predictor.prediction.rule_a_gate.shadow_runner import compute_rule_a_prediction
    from worldcup_predictor.prediction.rule_a_gate.shadow_store import RuleAShadowRecord, RuleAShadowStore

    rows = _load_phase19_rows()
    if not rows:
        print("No Phase 19 replay — run Phase 19 first or wait for live shadow", file=sys.stderr)
        return 1

    store = RuleAShadowStore(SHADOW_PATH)
    ts = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    for r in rows:
        rule_a, source = compute_rule_a_prediction(
            wde_prediction=r.wde,
            scoreline_prediction=r.scoreline,
            odds_available=r.has_odds,
        )
        store.append(
            RuleAShadowRecord(
                fixture_id=r.fixture_id,
                match_name=r.match_name,
                timestamp=ts,
                production_prediction=r.final,
                wde_prediction=r.wde,
                scoreline_prediction=r.scoreline,
                rule_a_prediction=rule_a,
                odds_available=r.has_odds,
                data_quality_pct=r.data_quality_pct,
                rule_a_source=source,
            )
        )
    print(f"Bootstrapped {len(rows)} shadow records from Phase 19 replay", file=sys.stderr)
    return 0


def main() -> int:
    _reset_settings()

    if "--bootstrap-replay" in sys.argv:
        bootstrap_from_replay()

    records = load_shadow_records()
    actuals = load_actuals()
    enriched = enrich_with_results(records, actuals)
    finished = [r for r in enriched if r.get("actual")]

    ready = len(records) >= MIN_PREDICTIONS or len(finished) >= MIN_FINISHED
    write_report(enriched, finished=finished, ready=ready)

    print(f"Shadow predictions: {len(records)} | Finished: {len(finished)} | Ready: {ready}")
    if finished:
        ra = accuracy(finished, "rule_a_prediction")
        pr = accuracy(finished, "production_prediction")
        print(f"Rule A: {ra:.1%} | Production: {pr:.1%}")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
