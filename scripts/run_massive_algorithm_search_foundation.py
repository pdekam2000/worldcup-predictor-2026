#!/usr/bin/env python3
"""Start / resume MASSIVE algorithm search foundation (research-only)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.research.massive_algorithm_search.foundation import run_foundation
from worldcup_predictor.research.massive_algorithm_search.search_engine import SearchEngine
from worldcup_predictor.research.massive_algorithm_search.corpus import build_massive_corpus, chrono_split


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--resume", action="store_true", help="Resume search in --out directory")
    ap.add_argument("--out", type=str, default="", help="Existing artifact directory for resume")
    ap.add_argument("--target", type=int, default=100_000, help="Target unique configs")
    args = ap.parse_args()

    if args.resume and args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = ROOT / out
        rows, _, _ = build_massive_corpus()
        splits = chrono_split(rows)
        eng = SearchEngine(out, target_n=args.target)
        cp = eng.run(splits["train"], splits["validation"], max_new=None, checkpoint_every=5000)
        # max_new=None means fill to target_n
        print(cp.get("status"), "tested=", cp.get("tested"))
        print("NOT DEPLOYED")
        print("CANONICAL UNCHANGED")
        return 0

    # Fresh foundation includes inventory + 100k
    # For resume without rebuilding inventory, use --resume
    if args.resume and not args.out:
        print("--resume requires --out <artifact_dir>")
        return 2

    v = run_foundation(target_n=args.target)
    print(v.get("status"))
    for k in (
        "artifact_dir",
        "valid_prematch_labeled_fixtures",
        "priced_fixtures",
        "true_forward_fixtures",
        "experiment_count_completed",
        "benchmark_rate_cfg_per_sec",
        "est_1m_hours",
        "est_5m_hours",
        "honest_ge_75_candidate_exists",
        "best_accuracy_candidate",
        "best_profitable_candidate",
        "next_resume_command",
        "sealed_holdout_status",
    ):
        print(f"{k}={v.get(k)}")
    print("NOT DEPLOYED")
    print("CANONICAL UNCHANGED")
    print("WDE UNCHANGED")
    print("ECSE UNCHANGED")
    print("NO AUTO-PROMOTION")
    print("NO RESULT LEAKAGE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
