#!/usr/bin/env python3
"""Run APPROVED_BETS_FORENSIC_EVALUATION (read-only)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.approved_bets_forensic_evaluation import run


def main() -> int:
    v = run()
    print(v.get("status"))
    print("artifact_dir", v.get("artifact_dir"))
    print("taxonomy", v.get("taxonomy_conclusion"))
    print(
        "strict",
        v.get("strict_unique_fixtures"),
        "finished",
        v.get("strict_finished"),
        "pending",
        v.get("strict_pending"),
        "hits",
        v.get("1x2_hits"),
        "misses",
        v.get("1x2_misses"),
        "acc",
        v.get("1x2_accuracy"),
        "ci",
        v.get("1x2_ci95"),
    )
    print("priced", v.get("priced_n"), "roi", v.get("roi"), "dd", v.get("max_drawdown"))
    print("exact", v.get("exact_finished_n"), v.get("exact_top1"), v.get("exact_top5"))
    print("cohorts", v.get("cohort_summaries"))
    print("baseline", v.get("baseline_all_canonical_accuracy"), "improves", v.get("approval_improves_vs_baseline"))
    print("sample_ok", v.get("sample_size_sufficient"), "recon", v.get("reconciliation_ok"))
    print("NOT DEPLOYED")
    print("CANONICAL UNCHANGED")
    print("FREEZES UNCHANGED")
    print("NO PREDICTIONS REGENERATED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
