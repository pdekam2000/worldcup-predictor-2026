#!/usr/bin/env python3
"""Five-fixture Tier B WDE recovery E2E acceptance."""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.gpt_actions.config import load_gpt_actions_config
from worldcup_predictor.gpt_actions.jobs import JobStore
from worldcup_predictor.gpt_actions.runtime_bootstrap import bootstrap_gpt_actions_runtime
from worldcup_predictor.gpt_actions.worker import execute_prediction_job

FIXTURES = [1494698, 1508803, 1508804, 1508805, 1508806]


def main() -> int:
    bootstrap_gpt_actions_runtime()
    cfg = load_gpt_actions_config()
    store = JobStore(cfg.job_store_dir, max_retained=cfg.max_jobs_retained)
    results = []
    for fid in FIXTURES:
        job = store.create(
            payload={
                "date": "2026-07-12",
                "timezone": "Europe/Vienna",
                "scope": "owner",
                "prediction_scope": "owner_shadow",
                "fixture_ids": [fid],
                "refresh_if_stale": True,
                "include_all_predictions": True,
            },
            idempotency_key=f"wde-recovery-e2e-{fid}-{uuid.uuid4().hex[:8]}",
        )
        job_id = job["job_id"]
        execute_prediction_job(job_id, store=store, config=cfg)
        record = store.get(job_id) or {}
        pred = ((record.get("result") or {}).get("predictions") or [{}])[0]
        wde = pred.get("wde") or {}
        ecse = pred.get("ecse") or {}
        results.append(
            {
                "fixture_id": fid,
                "job_id": job_id,
                "job_status": record.get("status"),
                "data_quality": pred.get("data_quality") or pred.get("quality"),
                "odds_freshness": (pred.get("odds") or {}).get("freshness"),
                "wde_execution_status": wde.get("wde_execution_status"),
                "wde_failure_code": wde.get("wde_failure_code"),
                "wde_decision": wde.get("decision_pick"),
                "ft_marginal": wde.get("probability_argmax"),
                "had": {
                    "home": wde.get("home_probability"),
                    "draw": wde.get("draw_probability"),
                    "away": wde.get("away_probability"),
                },
                "btts": pred.get("btts"),
                "over_under_2_5": pred.get("over_under_2_5"),
                "ecse_top1": ecse.get("top1"),
                "ecse_top5": ecse.get("top5"),
                "top3_mass": ecse.get("top3_mass"),
                "top5_mass": ecse.get("top5_mass"),
                "model_agreement": pred.get("consensus"),
                "public_visible": pred.get("public_visible"),
            }
        )
    out = {"fixtures": results, "all_wde_executed": all(r["wde_execution_status"] == "executed" for r in results)}
    out_path = ROOT / "artifacts" / "tier_b_wde_recovery" / "five_fixture_e2e.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps(out, indent=2, default=str))
    return 0 if out["all_wde_executed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
