"""Phase 51H — EGIE historical backtest."""

from __future__ import annotations

import argparse
import json
import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))

from worldcup_predictor.goal_timing.backtest.runner import GoalTimingBacktestRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="EGIE Phase 51H historical backtest (read-only)")
    parser.add_argument("--competition-key", default="premier_league")
    parser.add_argument("--limit", type=int, default=None, help="Max finished fixtures to scan")
    parser.add_argument("--lookback-days", type=int, default=730)
    parser.add_argument(
        "--include-missing-goal-events",
        action="store_true",
        help="Include fixtures without goal events (may reduce evaluable sample)",
    )
    parser.add_argument("--output", type=Path, default=Path("artifacts/phase51h_egie_backtest.json"))
    parser.add_argument("--jsonl", type=Path, default=Path("artifacts/phase51h_egie_backtest.jsonl"))
    parser.add_argument("--report", type=Path, default=Path("PHASE_51H_EGIE_HISTORICAL_BACKTEST_REPORT.md"))
    args = parser.parse_args()

    runner = GoalTimingBacktestRunner(lookback_days=int(args.lookback_days))
    payload = runner.run(
        competition_key=str(args.competition_key),
        limit=args.limit,
        require_goal_events=not args.include_missing_goal_events,
    )

    results = payload.pop("results", [])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.jsonl:
        args.jsonl.parent.mkdir(parents=True, exist_ok=True)
        with args.jsonl.open("w", encoding="utf-8") as fh:
            for row in results:
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    report = _render_report(payload, results_path=args.output, jsonl_path=args.jsonl)
    args.report.write_text(report, encoding="utf-8")

    print(json.dumps({k: v for k, v in payload.items() if k != "results"}, indent=2, default=str))
    print(f"\nWrote {args.output}")
    print(f"Wrote {args.jsonl}")
    print(f"Wrote {args.report}")
    return 0


def _render_report(payload: dict, *, results_path: Path, jsonl_path: Path) -> str:
    m = payload.get("metrics") or {}
    markets = m.get("by_market") or {}
    team = markets.get("first_goal_team") or {}
    rng = markets.get("goal_range") or {}
    minute = markets.get("goal_minute") or {}

    def pct(v):
        return f"{v * 100:.1f}%" if v is not None else "—"

    lines = [
        "# PHASE 51H — EGIE Historical Backtest Report",
        "",
        f"**Status:** {payload.get('status')}",
        f"**Competition:** `{payload.get('competition_key')}`",
        f"**Data policy:** {payload.get('data_policy')}",
        f"**Window:** {payload.get('window_start')} → {payload.get('window_end')} ({payload.get('lookback_days')} days)",
        "",
        "## Sample",
        "",
        f"| Metric | Count |",
        f"|--------|------:|",
        f"| Fixtures scanned | {m.get('fixtures_scanned', 0)} |",
        f"| Published predictions | {m.get('published_predictions', 0)} |",
        f"| NO_PICK | {m.get('no_pick_count', 0)} |",
        f"| Evaluable published | {m.get('evaluable_published', 0)} |",
        f"| Errors | {payload.get('errors', 0)} |",
        "",
        "## Accuracy (published + evaluable)",
        "",
        f"| Market | Win rate | Soft win rate | Correct | Wrong | Partial |",
        f"|--------|----------|---------------|--------:|------:|--------:|",
        f"| First Goal Team | {pct(team.get('winrate'))} | — | {team.get('correct', 0)} | {team.get('wrong', 0)} | {team.get('partial', 0)} |",
        f"| Goal Range | {pct(rng.get('winrate'))} | — | {rng.get('correct', 0)} | {rng.get('wrong', 0)} | {rng.get('partial', 0)} |",
        f"| Goal Minute | {pct(minute.get('winrate'))} | {pct(minute.get('soft_winrate'))} | {minute.get('correct', 0)} | {minute.get('wrong', 0)} | {minute.get('partial', 0)} |",
        "",
        "## League breakdown",
        "",
    ]
    for league, stats in (m.get("by_league") or {}).items():
        t = stats.get("first_goal_team") or {}
        lines.append(f"### `{league}` (n={stats.get('sample_size', 0)})")
        lines.append(f"- Team: {pct(t.get('winrate'))}")
        lines.append(f"- Range: {pct((stats.get('goal_range') or {}).get('winrate'))}")
        lines.append(f"- Minute soft: {pct((stats.get('goal_minute') or {}).get('soft_winrate'))}")
        lines.append("")

    lines.extend(["## DQ bucket win rate (team market)", ""])
    for bucket, stats in (m.get("by_dq_bucket") or {}).get("first_goal_team", {}).items():
        lines.append(f"- `{bucket}`: {pct(stats.get('winrate'))} (n={stats.get('total', 0)})")

    lines.extend(["", "## Confidence bucket win rate (team market)", ""])
    for bucket, stats in (m.get("by_confidence_bucket") or {}).get("first_goal_team", {}).items():
        lines.append(f"- `{bucket}`: {pct(stats.get('winrate'))} (n={stats.get('total', 0)})")

    lines.extend(["", "## Calibration (confidence vs hit rate)", ""])
    cal = payload.get("calibration") or {}
    for market, buckets in cal.items():
        lines.append(f"### {market}")
        for bucket, stats in buckets.items():
            lines.append(
                f"- `{bucket}`: hit {pct(stats.get('hit_rate'))}, "
                f"soft {pct(stats.get('soft_hit_rate'))}, "
                f"mean conf {stats.get('mean_confidence')}, n={stats.get('total', 0)}"
            )
        lines.append("")

    lines.extend(
        [
            "## Artifacts",
            "",
            f"- Metrics JSON: `{results_path}`",
            f"- Per-fixture JSONL: `{jsonl_path}`",
            "",
            "**No deployment. Read-only historical data.**",
        ]
    )
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    raise SystemExit(main())
