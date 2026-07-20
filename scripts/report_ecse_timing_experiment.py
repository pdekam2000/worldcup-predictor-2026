#!/usr/bin/env python3
"""Aggregate report across ECSE timing experiment dates."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.ecse_timing_experiment.constants import ARTIFACT_ROOT, REPORT_ROOT, TZ_NAME
from worldcup_predictor.research.ecse_timing_experiment.db import connect_timing_db
from worldcup_predictor.research.ecse_timing_experiment.stats import interpretation_band, rate_block
from worldcup_predictor.research.ecse_timing_experiment.store import list_experiments


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Report ECSE timing experiment aggregates")
    p.add_argument("--from", dest="date_from", required=True)
    p.add_argument("--to", dest="date_to", required=True)
    p.add_argument("--json", action="store_true")
    args = p.parse_args(argv)

    conn = connect_timing_db(ROOT)
    exps = list_experiments(conn, date_from=args.date_from, date_to=args.date_to)
    rows = conn.execute(
        """
        SELECT e.experiment_date, r.snapshot_class, r.result_status, r.actual_score, r.payload_json, r.event_labels_json
        FROM timing_result_evaluations r
        JOIN timing_experiments e ON e.experiment_id = r.experiment_id
        WHERE e.experiment_date >= ? AND e.experiment_date <= ?
        """,
        (args.date_from, args.date_to),
    ).fetchall()

    by_class: dict[str, list[dict]] = {}
    for r in rows:
        d = dict(r)
        try:
            payload = json.loads(d.get("payload_json") or "{}")
        except json.JSONDecodeError:
            payload = {}
        by_class.setdefault(str(d["snapshot_class"]), []).append(payload)

    summary = {"date_from": args.date_from, "date_to": args.date_to, "experiments": len(exps), "by_class": {}}
    for sc, payloads in by_class.items():
        n = len(payloads)
        h1 = sum(1 for x in payloads if x.get("top1_hit"))
        h3 = sum(1 for x in payloads if x.get("top3_hit"))
        h5 = sum(1 for x in payloads if x.get("top5_hit"))
        summary["by_class"][sc] = {
            "n": n,
            "top1": rate_block(h1, n),
            "top3": rate_block(h3, n),
            "top5": rate_block(h5, n),
        }
    paired_n = summary["by_class"].get("EARLY", {}).get("n") or 0
    summary["interpretation"] = interpretation_band(int(paired_n))
    summary["declare_winner"] = False
    summary["research_only"] = True
    summary["note"] = "Do not declare EARLY/MID/LATE winner until sample policy thresholds are met."

    art = ROOT / ARTIFACT_ROOT / f"report_{args.date_from}_to_{args.date_to}"
    art.mkdir(parents=True, exist_ok=True)
    (art / "aggregate.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    report = ROOT / REPORT_ROOT / f"ecse_timing_experiment_{args.date_from}_to_{args.date_to}.md"
    lines = [
        f"# ECSE Timing Experiment Aggregate ({args.date_from} → {args.date_to})",
        "",
        f"Experiments: **{len(exps)}** · Interpretation: **{summary['interpretation']}**",
        "",
        "Do **not** declare a timing-class winner under current policy unless n≥100 and promotion review passes.",
        "",
        "| Class | n | Top1 | Top3 | Top5 | Wilson Top5 |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for sc, block in summary["by_class"].items():
        t5 = block["top5"]
        lines.append(
            f"| {sc} | {block['n']} | {block['top1'].get('rate')} | {block['top3'].get('rate')} | "
            f"{t5.get('rate')} | [{t5.get('wilson_lo')}, {t5.get('wilson_hi')}] |"
        )
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    summary["report_path"] = str(report)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(summary["interpretation"])
        print(f"report={report}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
