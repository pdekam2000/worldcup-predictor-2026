# Model-Only and Result Backfill — Final Alignment Report

**Generated:** 2026-07-11T08:20:00+00:00  
**FINAL STATUS:** `MODEL_ONLY_AND_BACKFILL_ALIGNED`

---

## Commit

| Field | Value |
|-------|-------|
| Commit | `066611619f52796baf0cab459a5ec5bad89679c9` |
| Message | Add model-only Best3 ECSE extraction and result backfill confirmation. |
| Branch | `main` → pushed to `origin/main` |

### Files committed (6)

| File | Safe | Notes |
|------|:----:|-------|
| `scripts/extract_best3_exact_score_top5.py` | ✓ | Extraction tooling |
| `scripts/validate_best3_exact_score_top5_extraction.py` | ✓ | 26/26 validation |
| `BEST_3_EXACT_SCORE_TOP5_MODEL_OUTPUT_2026_07_12.md` | ✓ | Model output report |
| `PRODUCTION_RESULT_BACKFILL_BATCH2_CONFIRMATION_REPORT.md` | ✓ | Backfill confirmation |
| `MODEL_ONLY_DAILY_PREDICTION_RUN_REPORT.md` | ✓ | Model-only run report |
| `worldcup_predictor/owner_predict_eval/domestic_league_control.py` | ✓ | Registry wiring only — uses `TIER_B_SHADOW_DOMAINS` |

### Intentionally excluded

| Item | Reason |
|------|--------|
| `artifacts/model_only_best3_exact_score_top5_20260712.json` | `artifacts/` gitignored — runtime payload |
| `artifacts/domestic_league_control_20260712/payload.json` | Large runtime artifact |
| Production DB / WAL / SHM | Runtime data |
| Provider cache dumps | Policy exclusion |
| `.env` / secrets | Forbidden |

---

## Validations (pre-commit)

| Script | Result |
|--------|--------|
| `validate_best3_exact_score_top5_extraction.py` | **26/26 PASS** — `BEST3_EXACT_SCORE_TOP5_EXTRACTED` |
| `validate_model_only_daily_prediction_run.py` | **18/18 PASS** |
| `validate_provider_rescue_lightweight.py` | Skipped locally (not tracked); production has untracked copy; prior run **PASS** (`ft_without_result=12`, dup=0, orphan=0) |

---

## HEAD parity

| Layer | SHA | Match |
|-------|-----|:-----:|
| LOCAL | `066611619f52796baf0cab459a5ec5bad89679c9` | ✓ |
| ORIGIN_MAIN | `066611619f52796baf0cab459a5ec5bad89679c9` | ✓ |
| PRODUCTION | `066611619f52796baf0cab459a5ec5bad89679c9` | ✓ |

Production aligned via `git reset --hard origin/main` after stashing/restoring three runtime rescue patches (uncommitted working-tree diffs only):

- `worldcup_predictor/data_import/european_result_backfill.py`
- `worldcup_predictor/database/repository.py`
- `worldcup_predictor/ingestion/league_history_importer.py`

These remain as **local production modifications** (not in this commit) — result backfill runtime fixes preserved.

---

## Production services

| Service | Status |
|---------|--------|
| worldcup-api | **active** |
| worldcup-gpt-actions | **active** |
| worldcup-mcp | **active** |

---

## Result backfill state (unchanged by this commit)

| Metric | Value |
|--------|------:|
| FT without result (before) | 220 |
| Inserted | 208 |
| Remaining | 12 (`PROVIDER_FIXTURE_MISSING`) |
| Duplicate fixtures | 0 |
| Orphan results | 0 |

No predictions regenerated. No WDE/ECSE/gate/timer changes in this commit.

---

## Policy compliance

- No model formula changes (registry wiring only in `domestic_league_control.py`)
- No odds-only predictions
- No blind backfill of remaining 12 fixtures
- No runtime DB committed
