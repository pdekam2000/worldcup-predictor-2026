"""Phase 21A-LIVE — Forward-only Rule A validation (no historical bootstrap)."""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
import runpy

runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_21A_LIVE_VALIDATION_REPORT.md"
MIN_SETTLED = 30
PREFERRED_SETTLED = 50


def _reset_settings() -> None:
    os.environ.setdefault("RULE_A_LIVE_MODE", "shadow")
    os.environ.setdefault("LAMBDA_BRIDGE_MODE", "off")
    from worldcup_predictor.config.settings import get_settings

    get_settings.cache_clear()


def _acc(rows: list, key: str) -> float | None:
    if not rows:
        return None
    return sum(1 for r in rows if getattr(r, key) == r.actual_result) / len(rows)


def write_report(
    *,
    started_at: str | None,
    total_predictions: int,
    pending: int,
    settled_rows: list,
    ready: bool,
) -> None:
    ns = len(settled_rows)
    prod = _acc(settled_rows, "production_prediction")
    wde = _acc(settled_rows, "wde_prediction")
    sl = _acc(settled_rows, "scoreline_prediction")
    rule_a = _acc(settled_rows, "rule_a_prediction")

    def fmt(v: float | None) -> str:
        return f"{v:.1%}" if v is not None else "—"

    with_odds = [r for r in settled_rows if r.odds_available]
    no_odds = [r for r in settled_rows if not r.odds_available]

    beats_all = (
        rule_a is not None
        and prod is not None
        and wde is not None
        and sl is not None
        and rule_a > prod
        and rule_a > wde
        and rule_a > sl
    )

    lines = [
        "# Phase 21A-LIVE — Forward Match Validation Report",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "## Mode",
        "",
        "- **Shadow only** — no production, API, UI, or deploy changes",
        "- **Forward-only** — no Phase 19/20 replay, no bootstrap",
        f"- Tracking started: **{started_at or 'not yet started'}**",
        f"- Live store: `data/shadow/rule_a_live_validation.jsonl`",
        "",
        "## 1. Collection status",
        "",
        f"| Metric | Count | Target |",
        f"|--------|-------|--------|",
        f"| Total live predictions | **{total_predictions}** | — |",
        f"| Pending (unsettled) | **{pending}** | — |",
        f"| **Settled fixtures** | **{ns}** | 30 min / 50 preferred |",
        f"| Ready for decision | **{'YES' if ready else 'NO'}** | |",
        "",
    ]

    if not ready:
        lines.extend(
            [
                "> **Collecting** — run predictions on upcoming fixtures and re-run this script "
                f"after **{MIN_SETTLED}+** fixtures finish. Settlement uses `match_results.jsonl` only.",
                "",
            ]
        )

    lines.extend(
        [
            "## 2. Accuracy (settled forward fixtures only)",
            "",
            "| Strategy | Accuracy | n |",
            "|----------|----------|---|",
            f"| Production | {fmt(prod)} | {ns} |",
            f"| WDE only | {fmt(wde)} | {ns} |",
            f"| Scoreline only | {fmt(sl)} | {ns} |",
            f"| **Rule A** | **{fmt(rule_a)}** | {ns} |",
            "",
        ]
    )

    if rule_a is not None and prod is not None:
        lines.append(f"**Rule A vs Production:** {rule_a - prod:+.1%}")
        lines.append("")

    lines.extend(
        [
            "## 3. Cohort analysis (settled)",
            "",
            "| Cohort | n | Production | WDE | Scoreline | Rule A |",
            "|--------|---|------------|-----|-----------|--------|",
        ]
    )
    for label, subset in (
        ("Odds available", with_odds),
        ("No odds", no_odds),
    ):
        if not subset:
            lines.append(f"| {label} | 0 | — | — | — | — |")
            continue
        lines.append(
            f"| {label} | {len(subset)} | {fmt(_acc(subset, 'production_prediction'))} | "
            f"{fmt(_acc(subset, 'wde_prediction'))} | {fmt(_acc(subset, 'scoreline_prediction'))} | "
            f"**{fmt(_acc(subset, 'rule_a_prediction'))}** |"
        )

    lines.extend(["", "## 4. Recommendation", ""])
    if not ready:
        lines.append(
            "**HOLD** — insufficient settled forward fixtures. Continue shadow tracking."
        )
    elif beats_all:
        lines.append(
            "**Recommend PHASE 21B — Production Activation Candidate** "
            "(shadow validation passed on forward-only sample)."
        )
    else:
        lines.append("**Abort activation** — Rule A did not beat all baselines on forward sample.")

    lines.extend(
        [
            "",
            "## Success criteria",
            "",
            f"- Rule A > Production: **{'YES' if rule_a and prod and rule_a > prod else 'NO' if ready else 'PENDING'}**",
            f"- Rule A > WDE: **{'YES' if rule_a and wde and rule_a > wde else 'NO' if ready else 'PENDING'}**",
            f"- Rule A > Scoreline: **{'YES' if rule_a and sl and rule_a > sl else 'NO' if ready else 'PENDING'}**",
            "",
            "**Stop — shadow validation only. No production activation without Phase 21B approval.**",
        ]
    )
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    _reset_settings()

    from worldcup_predictor.prediction.rule_a_gate.live_settlement import settle_live_records
    from worldcup_predictor.prediction.rule_a_gate.live_validation_store import LiveValidationStore

    store = LiveValidationStore()
    started_at = store.started_at()
    newly, _ = settle_live_records(store)

    latest = store.latest_by_fixture()
    settled = [r for r in latest.values() if r.settled and r.actual_result]
    pending = sum(1 for r in latest.values() if not r.settled)
    ready = len(settled) >= MIN_SETTLED

    write_report(
        started_at=started_at,
        total_predictions=len(latest),
        pending=pending,
        settled_rows=settled,
        ready=ready,
    )

    print(
        f"Live predictions: {len(latest)} | Settled: {len(settled)} | "
        f"Newly settled: {newly} | Ready: {ready}"
    )
    if settled:
        ra = _acc(settled, "rule_a_prediction")
        pr = _acc(settled, "production_prediction")
        print(f"Rule A: {ra:.1%} | Production: {pr:.1%}")
    print(f"Report: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
