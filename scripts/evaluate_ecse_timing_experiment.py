#!/usr/bin/env python3
"""Evaluate ECSE timing experiment snapshots against confirmed final results."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from worldcup_predictor.config.env_loading import project_root
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.forward_evaluation.db import connect_eval_db
from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.research.ecse_timing_experiment.constants import ARTIFACT_ROOT, FINISHED, TZ_NAME
from worldcup_predictor.research.ecse_timing_experiment.db import connect_timing_db
from worldcup_predictor.research.ecse_timing_experiment.evaluate import (
    aggregate_timing_metrics,
    evaluate_fixture_timeline,
    normalize_score,
)
from worldcup_predictor.research.ecse_timing_experiment.extract import freeze_payload_from_eval
from worldcup_predictor.research.ecse_timing_experiment.store import (
    ensure_experiment,
    list_successful_snapshots,
    upsert_evaluation,
)


def _load_actual(prod, eval_conn, fid: int) -> tuple[str | None, str | None]:
    # Prefer evaluation DB actual_results
    row = eval_conn.execute(
        "SELECT home_goals, away_goals, status FROM actual_results WHERE fixture_id=? LIMIT 1",
        (int(fid),),
    ).fetchone()
    if row:
        score = normalize_score(row["home_goals"], row["away_goals"])
        return score, str(row["status"] or "FT")
    row = prod.execute(
        "SELECT home_goals, away_goals, status FROM fixtures WHERE fixture_id=? LIMIT 1",
        (int(fid),),
    ).fetchone()
    if not row:
        return None, None
    d = dict(row)
    score = normalize_score(d.get("home_goals"), d.get("away_goals"))
    return score, str(d.get("status") or "")


def _load_freeze(eval_conn, fid: int) -> dict[str, Any] | None:
    row = eval_conn.execute(
        "SELECT * FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1",
        (int(fid),),
    ).fetchone()
    if not row:
        return None
    fr = dict(row)
    ranks = [
        dict(r)
        for r in eval_conn.execute(
            "SELECT rank, score, probability FROM exact_score_rankings WHERE prediction_id=? ORDER BY rank",
            (fr["prediction_id"],),
        ).fetchall()
    ]
    fr["ranks"] = ranks
    return fr


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Evaluate ECSE timing experiment (research only)")
    p.add_argument("--date", required=True)
    p.add_argument("--scope", default="owner")
    p.add_argument("--json", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args(argv)

    target = resolve_target_date(args.date, TZ_NAME).isoformat()
    root = project_root()
    timing = connect_timing_db(root)
    experiment_id = ensure_experiment(
        timing, experiment_date=target, scope=args.scope, timezone=TZ_NAME
    )
    snaps = list_successful_snapshots(timing, experiment_id)
    by_fid: dict[int, dict[str, Any]] = {}
    meta_by_fid: dict[int, dict[str, Any]] = {}
    for s in snaps:
        fid = int(s["fixture_id"])
        by_fid.setdefault(fid, {})[s["snapshot_class"]] = s.get("payload") or {}
        meta_by_fid.setdefault(fid, {})[s["snapshot_class"]] = {
            "hours_to_kickoff": s.get("hours_to_kickoff"),
            "top5_mass": ((s.get("payload") or {}).get("ecse") or {}).get("top5_mass"),
            "entropy": ((s.get("payload") or {}).get("ecse") or {}).get("entropy"),
        }

    settings = get_settings()
    prod = connect(settings.sqlite_path)
    eval_conn = connect_eval_db(root)

    fixture_evals = []
    for fid, snapshots in sorted(by_fid.items()):
        score, status = _load_actual(prod, eval_conn, fid)
        fr = _load_freeze(eval_conn, fid)
        freeze_payload = freeze_payload_from_eval(fr)
        if not score or str(status or "").upper() not in FINISHED:
            # Explicitly exclude pending from denominators
            ev = evaluate_fixture_timeline(
                snapshots,
                actual_score=score or "",
                status=status or "NS",
                freeze_payload=freeze_payload,
            )
            if score and str(status or "").upper() in FINISHED:
                pass
            else:
                ev = {
                    "eligible": False,
                    "exclusion_reason": "pending_or_unresolved",
                    "actual_score": score,
                    "status": status,
                    "fixture_id": fid,
                    "research_only": True,
                }
        else:
            ev = evaluate_fixture_timeline(
                snapshots,
                actual_score=score,
                status=status,
                freeze_payload=freeze_payload,
            )
            ev["fixture_id"] = fid
            ev["snapshot_meta"] = meta_by_fid.get(fid) or {}
            if not args.dry_run:
                for sc, per in (ev.get("per_snapshot") or {}).items():
                    upsert_evaluation(
                        timing,
                        experiment_id=experiment_id,
                        fixture_id=fid,
                        snapshot_class=sc,
                        result_status="EVALUATED",
                        actual_score=score,
                        payload=per,
                        event_labels=ev.get("event_labels") or [],
                    )
                if ev.get("stable_union_eval"):
                    upsert_evaluation(
                        timing,
                        experiment_id=experiment_id,
                        fixture_id=fid,
                        snapshot_class="STABLE_UNION_TOP5",
                        result_status="EVALUATED",
                        actual_score=score,
                        payload=ev["stable_union_eval"],
                        event_labels=ev.get("event_labels") or [],
                    )
        fixture_evals.append(ev)

    agg = aggregate_timing_metrics(fixture_evals)
    out = {
        "experiment_id": experiment_id,
        "experiment_date": target,
        "fixture_evaluations": fixture_evals,
        "aggregate": agg,
        "research_only": True,
        "declare_winner": False,
    }
    art = root / ARTIFACT_ROOT / target / "evaluation"
    art.mkdir(parents=True, exist_ok=True)
    (art / "evaluation.json").write_text(json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    if args.json:
        print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"eligible={agg.get('eligible_fixtures')} excluded={agg.get('excluded_fixtures')}")
        print(f"interpretation={((agg.get('paired_early_vs_late') or {}).get('interpretation'))}")
        print("declare_winner=false")
        for sc, block in (agg.get("by_class") or {}).items():
            t5 = block.get("top5") or {}
            print(f"{sc}: n={block.get('sample_size')} top5={t5.get('rate')}")
    timing.close()
    prod.close()
    eval_conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
