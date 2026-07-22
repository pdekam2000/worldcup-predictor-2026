#!/usr/bin/env python3
"""Write ECSE integrity forensic artifacts + owner reports."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT / "artifacts" / "research" / "ecse_integrity"
REP = ROOT / "reports" / "owner" / "daily"
ART.mkdir(parents=True, exist_ok=True)
REP.mkdir(parents=True, exist_ok=True)

input_diff = {
    "first_identical_stage": "odds_feature_extraction_first_bookmaker_pick",
    "root_cause": (
        "build_odds_feature_row used _pick_odd (first Match Winner line). "
        "Both Rijeka and Lugano snapshots listed 10Bet first with identical "
        "1.16/5.75/19.5 while later books differed."
    ),
    "not_cache": True,
    "not_registry_collision": True,
    "registry_resolve": {"1593490": None, "1556516": None, "method": "unresolved"},
    "prediction_source": "live_odds",
    "odds_features_first_book_identical": {
        "ft_home_closing": 1.16,
        "ft_draw_closing": 5.75,
        "ft_away_closing": 19.5,
        "ou_over_25_closing": 1.62,
        "ou_under_25_closing": 2.2,
        "btts_yes_closing": 2.5,
        "btts_no_closing": 1.42,
    },
    "fas_odds_prep_differed": {
        "1593490": {"home": 1.17, "draw": 6.5, "away": 15.44},
        "1556516": {"home": 1.15, "draw": 6.8, "away": 17.0},
    },
    "book_order_sample": {
        "1593490": [["10Bet", 1.16, 5.75, 19.5], ["William Hill", 1.17, 6.0, 17.0], ["Bet365", 1.17, 6.0, 13.0]],
        "1556516": [["10Bet", 1.16, 5.75, 19.5], ["William Hill", 1.15, 6.5, 17.0], ["Bet365", 1.17, 6.25, 21.0]],
    },
    "fix": "median_across_bookmakers in build_odds_feature_row",
}
(ART / "rijeka_lugano_input_diff.json").write_text(json.dumps(input_diff, indent=2), encoding="utf-8")

raw_ecse = {
    "identical_outputs_under_first_book_path": {
        "lambda_home": 2.97233,
        "lambda_away": 0.176816,
        "top5": ["2-0", "3-0", "4-0", "1-0", "5-0"],
        "top5_mass": 0.727044,
        "entropy": 1.569679,
    },
    "first_identical_stage": "after build_odds_feature_row → extract_lambdas",
    "poisson_formula_bug": False,
    "expected_if_identical_odds_features": True,
    "integrity_defect": "odds bridge used first-book pick instead of fixture consensus",
}
(ART / "rijeka_lugano_raw_ecse_diff.json").write_text(json.dumps(raw_ecse, indent=2), encoding="utf-8")

(ART / "ecse_cache_key_audit.json").write_text(
    json.dumps(
        {
            "memoization_layers_found": [],
            "lru_cache_on_ecse_builder": False,
            "global_singleton": False,
            "collision_mechanism": "identical extracted odds features via first-book pick, not shared cache key",
            "required_dimensions": [
                "fixture_id",
                "home_team_id_or_name",
                "away_team_id_or_name",
                "competition",
                "odds_feature_fingerprint",
                "model_version",
                "feature_version",
            ],
        },
        indent=2,
    ),
    encoding="utf-8",
)

(ART / "confidence_lineage_schema.json").write_text(
    json.dumps(
        {
            "module": "worldcup_predictor/research/confidence_lineage.py",
            "threshold_used": 60.0,
            "note": "Missing historical stages labeled NOT_EXPOSED; no formula change",
        },
        indent=2,
    ),
    encoding="utf-8",
)

(ART / "bodo_confidence_stage_diff.json").write_text(
    json.dumps(
        {
            "fixture_id": 1494611,
            "prior_freeze": {"confidence": 67.4, "no_bet": False, "odds": [1.1, 9.5, 19.0], "wde_hda": [86.4, 9.6, 4.0]},
            "fresh_scan": {"confidence": 53.7, "no_bet": True, "odds": [1.1, 9.5, 19.0], "wde_hda": [86.4, 9.6, 4.0]},
            "stages": [
                {"stage": "raw/base confidence", "prior": "NOT_EXPOSED", "fresh": "NOT_EXPOSED", "delta": "unavailable"},
                {"stage": "WDE H/D/A probabilities", "prior": [86.4, 9.6, 4.0], "fresh": [86.4, 9.6, 4.0], "delta": 0},
                {"stage": "1X2 odds prices", "prior": [1.1, 9.5, 19.0], "fresh": [1.1, 9.5, 19.0], "delta": 0},
                {"stage": "final confidence", "prior": 67.4, "fresh": 53.7, "delta": -13.7},
            ],
            "classification": "pipeline-context / enrichment difference; not odds-price-driven; full stage split unresolved without historical lineage fields",
        },
        indent=2,
    ),
    encoding="utf-8",
)

(ART / "no_bet_propagation_cases.json").write_text(
    json.dumps(
        {
            "cases": [
                {
                    "fixture_id": 1494680,
                    "match": "Lillestrom vs Viking",
                    "confidence": 58.1,
                    "no_bet": True,
                    "reasons_before": [],
                    "root": "pick_visibility forced no_bet via confidence<60 without serializing CONFIDENCE_BELOW_60",
                },
                {
                    "fixture_id": 1494224,
                    "match": "Vasteras SK FK vs Orgryte IS",
                    "confidence": 59.1,
                    "no_bet": True,
                    "reasons_before": [],
                    "root": "same",
                },
            ],
            "fix": "pick_visibility._ensure_no_bet_reasons_invariant",
            "conditions_unchanged": True,
            "threshold_unchanged": 60.0,
        },
        indent=2,
    ),
    encoding="utf-8",
)

(REP / "ECSE_DUPLICATE_SIGNATURE_ROOT_CAUSE.md").write_text(
    "\n".join(
        [
            "# ECSE Duplicate Signature — Root Cause",
            "",
            "**Scan:** `fas_2026-07-22_6d_20260722T072236Z_85624389`",
            "**Fixtures:** Rijeka (`1593490`) vs Lugano (`1556516`)",
            "",
            "## Verdict",
            "Integrity defect in the **odds→ECSE bridge**, not in Poisson/Dixon–Coles.",
            "",
            "## First identical stage",
            "`build_odds_feature_row` → `_pick_odd` (first bookmaker Match Winner line).",
            "Both snapshots listed **10Bet first** at **1.16 / 5.75 / 19.5**.",
            "Later books differed; FAS `odds_prep` consensus also differed (1.17 vs 1.15).",
            "Identical odds features → identical `extract_lambdas` → identical score matrix.",
            "",
            "## Ruled out",
            "- Registry ID collision (both unresolved)",
            "- LRU/memoization cache",
            "- Shared mutable result object",
            "- Team ID / mapping swap",
            "- Shared fallback template (source=`live_odds`)",
            "",
            "## Fix (minimal)",
            "Use **median across bookmakers** for ECSE odds features (same practice as canonical 1X2 snapshot).",
            "Add input/output hashes + FAS duplicate-signature guard.",
            "Poisson formula unchanged.",
            "",
        ]
    ),
    encoding="utf-8",
)

(REP / "CONFIDENCE_LINEAGE_EXPOSURE_REPORT.md").write_text(
    "\n".join(
        [
            "# Confidence Lineage Exposure",
            "",
            "Module: `worldcup_predictor/research/confidence_lineage.py`",
            "Wired into ephemeral FAS predictions as `confidence_lineage`.",
            "Threshold remains **60.0**. No formula change.",
            "Historical freezes may still lack per-stage fields (`NOT_EXPOSED`).",
            "",
        ]
    ),
    encoding="utf-8",
)

(REP / "BODO_CONFIDENCE_DRIFT_RECONSTRUCTION.md").write_text(
    "\n".join(
        [
            "# Bodo Confidence Drift Reconstruction",
            "",
            "Freeze `8494f2d3-…` conf **67.4** / no_bet=false → FAS fresh **53.7** / no_bet=true.",
            "Odds prices and WDE H/D/A **unchanged**.",
            "Full per-penalty chain not stored historically → classification:",
            "**pipeline-context / enrichment difference; not odds-price-driven**.",
            "Immutable freeze not modified.",
            "",
            "See `artifacts/research/ecse_integrity/bodo_confidence_stage_diff.json`.",
            "",
        ]
    ),
    encoding="utf-8",
)

(REP / "NO_BET_REASON_PROPAGATION_FIX.md").write_text(
    "\n".join(
        [
            "# No-Bet Reason Propagation Fix",
            "",
            "## Root cause",
            "`enrich_pick_visibility` could force `no_bet=true` when `confidence < 60`",
            "while leaving `no_bet_reasons=[]` if recompute metadata reasons were empty.",
            "",
            "## Cases",
            "- 1494680 Lillestrøm vs Viking (58.1)",
            "- 1494224 Vasteras vs Örgryte (59.1)",
            "",
            "## Fix",
            "`_ensure_no_bet_reasons_invariant` reconstructs reasons from the same gates",
            "(evaluator + visibility conf/DQ thresholds). **No new no_bet conditions.**",
            "Threshold remains 60.0.",
            "",
        ]
    ),
    encoding="utf-8",
)

print("OK", ART, REP)
