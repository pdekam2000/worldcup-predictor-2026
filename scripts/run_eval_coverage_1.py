#!/usr/bin/env python3
"""EVAL-COVERAGE-1 — Finished fixtures evaluation coverage + controlled results/eval run."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.research.eval_coverage.audit import PHASE, render_audit_markdown, run_coverage_audit
from worldcup_predictor.research.eval_coverage.odds_freshness import (
    render_odds_freshness_markdown,
    run_odds_freshness_audit,
)
from worldcup_predictor.research.eval_coverage.promotion_gate import evaluate_s5_promotion_gate
from worldcup_predictor.research.top3_endresult_optimizer.runner import run_optimizer_backtest
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_count, table_exists

ARTIFACT_DIR = ROOT / "artifacts" / "eval_coverage_1"
AUDIT_MD = ROOT / "EVAL_COVERAGE_1_AUDIT.md"
ODDS_MD = ROOT / "EVAL_COVERAGE_1_ODDS_FRESHNESS_SUMMARY.md"
REPORT_MD = ROOT / "EVAL_COVERAGE_1_REPORT.md"


def _run_pipeline(mode: str, *, dry_run: bool, cwd: Path) -> dict:
    cmd = [
        sys.executable,
        str(cwd / "scripts" / "run_production_prediction_pipeline.py"),
        "--mode",
        mode,
    ]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, encoding="utf-8")
    payload: dict = {"mode": mode, "dry_run": dry_run, "exit_code": proc.returncode}
    if proc.stdout.strip():
        try:
            payload["result"] = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload["stdout"] = proc.stdout[-4000:]
    if proc.stderr.strip():
        payload["stderr"] = proc.stderr[-2000:]
    return payload


def _db_counts(db_path: str) -> dict[str, int]:
    conn = connect_readonly(db_path)
    tables = (
        "fixtures",
        "fixture_results",
        "worldcup_stored_predictions",
        "worldcup_prediction_evaluations",
        "ecse_prediction_snapshots",
        "ecse_prediction_evaluations",
    )
    out = {t: table_count(conn, t) for t in tables if table_exists(conn, t)}
    conn.close()
    return out


def _render_report(ctx: dict) -> str:
    before = ctx.get("audit_before", {}).get("summary", {})
    after = ctx.get("audit_after", {}).get("summary", {})
    opt = ctx.get("optimizer", {}).get("payload", {})
    gate = ctx.get("promotion_gate", {})
    dry_results = ctx.get("dry_run_results", {})
    dry_eval = ctx.get("dry_run_eval", {})
    real_results = ctx.get("real_results", {})
    real_eval = ctx.get("real_eval", {})
    rec = ctx.get("final_recommendation", "DO_NOT_PROMOTE")

    lines = [
        "# EVAL-COVERAGE-1 — Final Report",
        "",
        f"Phase: **{PHASE}** | Status: Complete — **DO NOT PROMOTE S5**",
        "",
        f"## Final Recommendation: `{rec}`",
        "",
        f"S5 promotion gate: `{gate.get('decision', 'S5_NEEDS_MORE_DATA')}`",
        "",
        "---",
        "",
        "## Before / After Evaluation Coverage",
        "",
        "| Metric | Before | After | Δ |",
        "|--------|-------:|------:|--:|",
    ]
    keys = [
        ("finished_wc", "Finished WC"),
        ("finished_with_result", "Finished with 90' result"),
        ("ecse_research_finished", "ECSE research sample"),
        ("ecse_pending", "ECSE pending eval"),
        ("wde_pending", "WDE pending eval"),
    ]
    for key, label in keys:
        b = before.get(key, 0)
        a = after.get(key, b)
        lines.append(f"| {label} | {b} | {a} | {a - b:+d} |")

    lines.extend(
        [
            "",
            "## Pipeline Runs",
            "",
            "### Part B — Dry-run",
            "",
        ]
    )
    for label, block in (("results-only", dry_results), ("eval-only", dry_eval)):
        r = block.get("result") or {}
        counts = r.get("counts") or {}
        lines.append(f"**{label} dry-run:** exit={block.get('exit_code')}")
        lines.append(f"- Would sync results: {counts.get('results_synced', 'n/a')}")
        lines.append(f"- Would evaluate: {counts.get('predictions_evaluated', 'n/a')}")
        lines.append(f"- DB writes: {'none (dry_run=true)' if r.get('dry_run') else 'unknown'}")
        lines.append("")

    lines.extend(["### Part C — Controlled real run", ""])
    if ctx.get("real_run_skipped"):
        lines.append(f"**Skipped:** {ctx.get('real_run_skip_reason')}")
    else:
        for label, block in (("results-only", real_results), ("eval-only", real_eval)):
            r = block.get("result") or {}
            counts = r.get("counts") or {}
            errs = r.get("errors") or []
            lines.append(f"**{label}:** exit={block.get('exit_code')}, synced={counts.get('results_synced', 0)}, "
                         f"evaluated={counts.get('predictions_evaluated', 0)}, errors={len(errs)}")
    lines.append("")

    baseline = opt.get("baseline_audit") or {}
    best = opt.get("best_strategy_id", "")
    s5 = (opt.get("strategy_summary") or {}).get("S5_conservative_coverage") or {}
    s5_rate = ((s5.get("segments") or {}).get("all") or {}).get("top3_hit_rate_pct")

    lines.extend(
        [
            "## Research Metrics (expanded sample)",
            "",
            f"- Finished/evaluated matches: **{opt.get('finished_count', 0)}**",
            f"- Raw ECSE Top1: **{baseline.get('raw_top1_hit_rate_pct', 'N/A')}%**",
            f"- Raw ECSE Top3: **{baseline.get('raw_top3_hit_rate_pct', 'N/A')}%**",
            f"- Raw ECSE Top5: **{baseline.get('raw_top5_hit_rate_pct', 'N/A')}%**",
            f"- S5 optimized Top3: **{s5_rate or 'N/A'}%**",
            f"- Best strategy: **{best}**",
            "",
            "## S5 Promotion Gate",
            "",
            f"- Decision: **{gate.get('decision')}**",
            f"- Checks passed: {gate.get('checks_passed')}/{gate.get('checks_total')}",
            f"- Evaluated matches: {gate.get('evaluated_matches')} (need {gate.get('needed_matches')} more for n=40)",
            f"- S5 − raw Top3: **{gate.get('delta_pp')} pp**",
            "",
            "## Odds Freshness",
            "",
            "See `EVAL_COVERAGE_1_ODDS_FRESHNESS_SUMMARY.md`.",
            "",
            "## Next Phase",
            "",
        ]
    )
    if gate.get("odds_all_stale"):
        lines.append("- **ODDS-FRESHNESS-1** — all evaluated fixtures stale")
    if gate.get("decision") == "S5_NEEDS_MORE_DATA":
        lines.append("- **KEEP_COLLECTING_EVALUATIONS** — need 40+ finished evaluated matches")
    lines.append("- **DO_NOT_PROMOTE** — S5 remains shadow-only")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="EVAL-COVERAGE-1 orchestrator")
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--skip-real-run", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    db_path = args.db_path or settings.sqlite_path
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    ctx: dict = {"phase": PHASE, "db_path": db_path}
    ctx["audit_before"] = run_coverage_audit(db_path)
    ctx["db_counts_before"] = _db_counts(db_path)

    AUDIT_MD.write_text(
        render_audit_markdown(ctx["audit_before"], label="Before")
        + "\n\n---\n\n"
        + render_audit_markdown(ctx["audit_before"], label="Initial"),
        encoding="utf-8",
    )

    ctx["dry_run_results"] = _run_pipeline("results-only", dry_run=True, cwd=ROOT)
    ctx["dry_run_eval"] = _run_pipeline("eval-only", dry_run=True, cwd=ROOT)

    if args.audit_only:
        print(json.dumps({"phase": PHASE, "audit_only": True, "summary": ctx["audit_before"]["summary"]}, indent=2))
        return 0

    real_run_skipped = args.skip_real_run
    skip_reason = "--skip-real-run" if args.skip_real_run else ""

    if not real_run_skipped:
        dr = ctx["dry_run_results"].get("result") or {}
        if dr.get("errors"):
            real_run_skipped = True
            skip_reason = f"dry-run errors: {dr['errors']}"

    ctx["real_run_skipped"] = real_run_skipped
    ctx["real_run_skip_reason"] = skip_reason

    if not real_run_skipped:
        ctx["real_results"] = _run_pipeline("results-only", dry_run=False, cwd=ROOT)
        rs_exit = ctx["real_results"].get("exit_code", 1)
        rs_errs = (ctx["real_results"].get("result") or {}).get("errors") or []
        if rs_exit != 0 and rs_errs:
            ctx["real_eval"] = {"skipped": True, "reason": "results-only failed"}
        else:
            ctx["real_eval"] = _run_pipeline("eval-only", dry_run=False, cwd=ROOT)

    ctx["audit_after"] = run_coverage_audit(db_path)
    ctx["db_counts_after"] = _db_counts(db_path)

    audit_after_md = render_audit_markdown(ctx["audit_after"], label="After")
    AUDIT_MD.write_text(
        render_audit_markdown(ctx["audit_before"], label="Before")
        + "\n\n---\n\n"
        + audit_after_md,
        encoding="utf-8",
    )

    ctx["optimizer"] = run_optimizer_backtest(db_path=db_path, artifacts_dir=str(ARTIFACT_DIR))
    ctx["odds_freshness"] = run_odds_freshness_audit(db_path)
    ODDS_MD.write_text(render_odds_freshness_markdown(ctx["odds_freshness"]), encoding="utf-8")

    ctx["promotion_gate"] = evaluate_s5_promotion_gate(
        ctx["optimizer"]["payload"],
        odds_freshness=ctx["odds_freshness"],
    )

    gate_dec = ctx["promotion_gate"]["decision"]
    after_n = ctx["audit_after"]["summary"].get("ecse_research_finished", 0)
    before_n = ctx["audit_before"]["summary"].get("ecse_research_finished", 0)
    wde_pending = ctx["audit_after"]["summary"].get("wde_pending", 0)
    ecse_pending = ctx["audit_after"]["summary"].get("ecse_pending", 0)

    if ctx.get("real_run_skipped") and "failed" in skip_reason.lower():
        rec = "RESULTS_SYNC_FAILED" if "results" in skip_reason.lower() else "EVAL_RUN_FAILED"
    elif after_n == 0 and before_n == 0 and wde_pending == 0 and ecse_pending == 0:
        rec = "NO_UNEVALUATED_FINISHED_FIXTURES"
    elif after_n > before_n:
        rec = "EVAL_COVERAGE_EXPANDED"
    elif ctx["promotion_gate"].get("odds_all_stale") and after_n > 0:
        rec = "ODDS_FRESHNESS_NEXT"
    elif gate_dec == "S5_NEEDS_MORE_DATA":
        rec = "S5_NEEDS_MORE_DATA"
    elif gate_dec == "S5_PROMOTION_GATE_PASSED_FOR_OWNER_PREVIEW":
        rec = "DO_NOT_PROMOTE"
    else:
        rec = "DO_NOT_PROMOTE"

    ctx["final_recommendation"] = rec
    REPORT_MD.write_text(_render_report(ctx), encoding="utf-8")

    out_json = ARTIFACT_DIR / "eval_coverage_1_context.json"
    out_json.write_text(json.dumps(ctx, indent=2, default=str), encoding="utf-8")

    print(
        json.dumps(
            {
                "phase": PHASE,
                "recommendation": rec,
                "gate": gate_dec,
                "before_ecse_sample": ctx["audit_before"]["summary"].get("ecse_research_finished"),
                "after_ecse_sample": ctx["audit_after"]["summary"].get("ecse_research_finished"),
                "real_run_skipped": real_run_skipped,
                "report": str(REPORT_MD),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
