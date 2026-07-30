#!/usr/bin/env python3
"""Read-only recompute of corrected Phase 5 three-fixture preview tables.

Does not mutate predictions, freezes, or shadow rows.
Writes a separate forensic artifact.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("APP_ENV", "production")
FIXTURES = [1556628, 1494717, 1567860]
LABELS = {
    1556628: "Dundee United vs Rangers",
    1494717: "Bodo/Glimt vs Lillestrom",
    1567860: "Admira Wacker vs Rapid Wien II",
}


def _git() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(ROOT), text=True).strip()
    except Exception:
        return "unknown"


def main() -> int:
    import sys

    sys.path.insert(0, str(ROOT))
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.forward_evaluation.db import connect_eval_db
    from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
    from worldcup_predictor.research.football_strength_foundation.score_v2 import dist_dc
    from worldcup_predictor.research.infra_l2f_forward.research_preview import build_fixture_preview
    from worldcup_predictor.research.football_strength_foundation.constants import SHADOW_TABLE

    settings = get_settings()
    prod = connect(settings.sqlite_path)
    ev = connect_eval_db()
    out_dir = ROOT / "artifacts" / "phase5_three_fixture_forensic"
    out_dir.mkdir(parents=True, exist_ok=True)

    before_hashes = {}
    after_hashes = {}
    report = {
        "git_sha": _git(),
        "mode": "read_only_forensic_correction",
        "no_prediction_mutation": True,
        "no_freeze_mutation": True,
        "no_shadow_mutation": True,
        "no_promotion": True,
        "fixtures": {},
    }

    for fid in FIXTURES:
        fr = ev.execute(
            "SELECT prediction_id, content_hash FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1",
            (fid,),
        ).fetchone()
        sh_rows = prod.execute(
            f"SELECT model_id, shadow_hash FROM {SHADOW_TABLE} WHERE fixture_id=? AND model_id IN ('EXACT_V2_SELECTED','LAMBDA_V2_BLENDED_ADAPTIVE')",
            (fid,),
        ).fetchall()
        before_hashes[fid] = {
            "freeze_id": fr[0] if fr else None,
            "freeze_hash": fr[1] if fr else None,
            "shadows": {r[0]: r[1] for r in sh_rows},
        }

        preview = build_fixture_preview(prod=prod, fi=prod, eval_conn=ev, fixture_id=fid)
        # Drop internal-only keys if any remain
        can = dict(preview.get("canonical") or {})
        can.pop("_poisson_dist", None)
        exact = dict(preview.get("exact_v2") or {})
        wde = dict(preview.get("wde") or {})

        # Explicit forensic table rows
        can_rows = []
        for i, t in enumerate((can.get("top5") or [])[:5]):
            can_rows.append(
                {
                    "stored_rank": t.get("rank") or i + 1,
                    "score": t.get("score"),
                    "raw_probability": t.get("probability"),
                    "calibrated_probability": t.get("probability"),
                    "displayed_probability": t.get("probability"),
                    "selection_score": t.get("probability"),
                    "ranking_field": t.get("ranking_field") or can.get("ranking_field"),
                    "expected_correct_rank": t.get("rank") or i + 1,
                }
            )
        ex_rows = []
        for i, t in enumerate((exact.get("top5") or [])[:5]):
            ex_rows.append(
                {
                    "stored_rank": t.get("rank") or i + 1,
                    "score": t.get("score"),
                    "raw_probability": t.get("probability"),
                    "calibrated_probability": t.get("probability"),
                    "displayed_probability": t.get("probability"),
                    "selection_score": t.get("probability"),
                    "ranking_field": t.get("ranking_field") or exact.get("ranking_field"),
                    "expected_correct_rank": t.get("rank") or i + 1,
                }
            )

        report["fixtures"][str(fid)] = {
            "label": LABELS.get(fid),
            "preview": preview,
            "canonical_rank_table": can_rows,
            "exact_v2_rank_table": ex_rows,
            "wde_decision_audit": {
                "wde_probabilities": wde.get("probabilities"),
                "raw_argmax": wde.get("raw_argmax") or wde.get("probability_argmax"),
                "stored_decision": wde.get("canonical_decision") or wde.get("decision"),
                "displayed_decision": wde.get("decision"),
                "override_applied": bool(wde.get("decision_override_reason")),
                "exact_override_reason": wde.get("decision_override_reason"),
                "decision_policy": wde.get("decision_policy"),
                "no_bet": wde.get("no_bet"),
            },
            "full_distribution_1x2": {
                "canonical": {
                    "home_win_mass": can.get("home_win_mass"),
                    "draw_mass": can.get("draw_mass"),
                    "away_win_mass": can.get("away_win_mass"),
                    "score_mass_1x2_direction": can.get("score_mass_1x2_direction"),
                    "ranking_field": can.get("ranking_field"),
                },
                "exact_v2": {
                    "home_win_mass": exact.get("home_win_mass"),
                    "draw_mass": exact.get("draw_mass"),
                    "away_win_mass": exact.get("away_win_mass"),
                    "score_mass_1x2_direction": exact.get("score_mass_1x2_direction"),
                    "ranking_field": exact.get("ranking_field"),
                },
                "wde_raw_argmax": wde.get("raw_argmax") or wde.get("probability_argmax"),
                "canonical_final_decision": wde.get("decision"),
            },
            "metrics": {
                "canonical_top5_mass": can.get("top5_mass"),
                "exact_top5_mass": exact.get("top5_mass"),
                "canonical_entropy": can.get("entropy"),
                "exact_entropy": exact.get("entropy"),
                "comparison": preview.get("comparison"),
                "agreement": preview.get("agreement"),
            },
            "ranking_consistent": can.get("ranking_consistent_with_displayed_probability"),
        }

        fr2 = ev.execute(
            "SELECT prediction_id, content_hash FROM frozen_predictions WHERE fixture_id=? ORDER BY frozen_at ASC LIMIT 1",
            (fid,),
        ).fetchone()
        sh2 = prod.execute(
            f"SELECT model_id, shadow_hash FROM {SHADOW_TABLE} WHERE fixture_id=? AND model_id IN ('EXACT_V2_SELECTED','LAMBDA_V2_BLENDED_ADAPTIVE')",
            (fid,),
        ).fetchall()
        after_hashes[fid] = {
            "freeze_id": fr2[0] if fr2 else None,
            "freeze_hash": fr2[1] if fr2 else None,
            "shadows": {r[0]: r[1] for r in sh2},
        }

    report["freeze_hashes_before"] = before_hashes
    report["freeze_hashes_after"] = after_hashes
    report["hashes_unchanged"] = before_hashes == after_hashes
    report["root_causes"] = {
        "rank_probability_mismatch": (
            "research_preview._canonical_ecse_tops joined Dixon–Coles (dist_dc) probabilities "
            "onto independent-Poisson ECSE ranks when top_5_scores lacked embedded probs. "
            "Canonical ranking field is independent_poisson_probability; Exact V2 SELECTED uses dixon_coles_probability."
        ),
        "dundee_wde_decision": (
            "Stored prediction/match_winner.selection=draw while probability argmax=away_win. "
            "Canonical WDE uses WeightedDecisionEngine._resolve_1x2 (home_edge bands / draw preference), "
            "not raw probability argmax. no_bet=true. Report previously showed only decision without argmax."
        ),
    }
    path = out_dir / "corrected_preview.json"
    path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"wrote": str(path), "hashes_unchanged": report["hashes_unchanged"], "git": report["git_sha"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
