# RESULT-TRUTH-SOURCE-CONSOLIDATION-1 — Change Inventory

**Timestamp:** 2026-07-05  
**Starting HEAD:** `282ef700f7bc31090f775f752f168d30e701ba24`

---

## 1. RESULT-TRUTH source code (INCLUDE)

| File | Status | Role |
|------|--------|------|
| `worldcup_predictor/database/schema.py` | Modified | Schema v8 |
| `worldcup_predictor/database/migrations.py` | Modified | v8 column migration |
| `worldcup_predictor/database/repository.py` | Modified | `upsert_fixture_result` stage truth |
| `worldcup_predictor/outcomes/provider_score_truth.py` | New | Provider score parsing |
| `worldcup_predictor/outcomes/market_result_resolver.py` | New | Regulation/AET/PEN market resolver |
| `worldcup_predictor/owner/owner_tracker_builder.py` | New | DB-truth owner tracker |
| `worldcup_predictor/research/ecse_live/result_sync.py` | Modified | Passes stage truth to upsert |
| `worldcup_predictor/api/prediction_history_evaluation.py` | Modified | DB regulation precedence over JSONL |

## 2. Scripts (INCLUDE)

| File | Status |
|------|--------|
| `scripts/run_result_truth_repair_1.py` | New |
| `scripts/validate_result_truth_repair_1.py` | New |
| `scripts/validate_result_truth_production_deploy_1.py` | New |

## 3. Reports/docs (INCLUDE)

| File | Status |
|------|--------|
| `RESULT_TRUTH_REPAIR_1_SCHEMA_AUDIT.md` | New |
| `CANADA_MOROCCO_OWNER_TRACKER_DISCREPANCY_FORENSIC.md` | New |
| `CANONICAL_11_MATCH_EVALUATION_SCORECARD.md` | New |
| `PREDICTION_PAYLOAD_HASH_DRIFT_AUDIT.md` | New |
| `RESULT_TRUTH_REPAIR_1_RESEARCH_HANDOFF.md` | New |
| `RESULT_TRUTH_REPAIR_1_REPORT.md` | New |
| `RESULT_TRUTH_PRODUCTION_DEPLOY_1_PREFLIGHT.md` | New |
| `RESULT_TRUTH_PRODUCTION_DEPLOY_1_REPORT.md` | New |

## 4. Consolidation reports (INCLUDE — this phase)

| File | Status |
|------|--------|
| `RESULT_TRUTH_SOURCE_CONSOLIDATION_1_CHANGE_INVENTORY.md` | New |
| `RESULT_TRUTH_SOURCE_CONSOLIDATION_1_FORBIDDEN_FILE_AUDIT.md` | New |
| `RESULT_TRUTH_SOURCE_CONSOLIDATION_1_PUSH_RESULT.md` | New |
| `RESULT_TRUTH_SOURCE_CONSOLIDATION_1_REPORT.md` | New |

---

## 5. Runtime data — EXCLUDE

| Path | Reason |
|------|--------|
| `data/cache/resolved_seasons.json` | Cache drift |
| `data/results/match_results.jsonl` | Runtime JSONL |
| `data/shadow/*.jsonl` (9 files) | Shadow runtime |
| `data/validation/real_world_validation.jsonl` | Runtime validation |

## 6. DB files — EXCLUDE

| Path | Size | Reason |
|------|------|--------|
| `artifacts/result_truth_repair_1/*.db` (×3) | ~30.5 GiB each | Local repair backups |
| Any `*.db` / `*.sqlite` | — | Forbidden |

## 7. Artifacts — EXCLUDE

| Path | Reason |
|------|--------|
| `artifacts/result_truth_repair_1/provider_calls.jsonl` | Runtime provider log |
| `artifacts/result_truth_repair_1/workflow.json` | Local run artifact (gitignored) |
| `artifacts/result_truth_repair_1/validation.json` | Local run artifact (gitignored) |
| `artifacts/result_truth_production_deploy_1/*` | Local run artifact (gitignored) |

## 8. Unrelated untracked work — EXCLUDE

Forensic, controlled-prediction, ECSE market prior, probe scripts, Brazil/Norway, finished-knockout forensic, and other parallel phases — not part of RESULT-TRUTH-REPAIR-1 functional chain.

**Total files to commit:** 22 (8 source + 3 scripts + 8 repair/deploy docs + 4 consolidation docs)
