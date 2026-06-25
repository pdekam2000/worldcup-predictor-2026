# Phase 46B — Historical Prediction Recovery

**Date:** 2026-06-21  
**Status:** COMPLETE — validated locally, deployed to production  
**Production:** `91.107.188.229` / https://footballpredictor.it.com

---

## Executive summary

Recoverable historical prediction assets identified in Phase 46A were imported into `worldcup_stored_predictions` using insert-if-absent semantics. **No authoritative archive rows were overwritten.** Low-quality imports were quarantined and excluded from the public global archive listing.

| Metric | Local dev | Production |
|--------|----------:|-----------:|
| Archive total **before** | 2 | **12** |
| Archive total **after** | 30 | **56** |
| **Imported** | 28 | **44** |
| **Quarantined** | 2 | **1** |
| **Duplicates skipped** | 2 | **12** |
| Errors | 0 | 0 |

Post-deploy dry-run on production: **0** additional imports available (all recoverable assets absorbed).

---

## Implementation

### Schema (Phase 46B migration)

Added to `worldcup_stored_predictions`:

| Column | Purpose |
|--------|---------|
| `imported_at` | UTC timestamp of import run |
| `import_source` | `cache`, `legacy_sqlite`, or `jsonl` |
| `quality_score` | 0.0–1.0 recoverability/quality score |
| `is_quarantined` | 1 = excluded from public archive |
| `quarantine_reason` | e.g. `known_test_fixture`, `low_quality_score`, `partial_jsonl_payload` |

Row-level `source` is set to **`legacy_import`** for all imported rows.

### Import pipeline

Module: `worldcup_predictor/automation/worldcup_background/legacy_prediction_import.py`

**Sources (priority: cache → legacy SQLite → JSONL):**

1. `.cache/predictions/*.json` — full API prediction envelopes
2. `predictions` + `prediction_markets` — reconstructed payloads via `latest_prediction_for_fixture`
3. `data/predictions/prediction_history.jsonl` — only when minimum fields present (1X2, teams, `created_at`, and O/U or confidence)

**Safety rules:**

- `insert_worldcup_stored_prediction_legacy_import()` — `INSERT … WHERE NOT EXISTS` on `fixture_id`
- Never calls production `upsert` / `evaluate_prediction_storage` guards
- Preserves original `predicted_at` from cache / JSONL / legacy row
- Known test fixtures (99, 123, 1489393, 1539007) and placeholder teams → quarantine
- Quality score &lt; 0.55 → quarantine
- Partial JSONL without `detailed_markets` → quarantine

### CLI

```bash
python main.py worldcup-import-legacy          # live import
python main.py worldcup-import-legacy --dry-run # preview only
```

### Public archive filter

`list_global_archive_rows()` now passes `include_quarantined=False` so quarantined legacy imports do not appear in public history.

---

## Validation

### Local automated validation

Script: `scripts/validate_phase46b_historical_recovery.py`  
Result: **17/17 PASS**  
Artifact: `artifacts/phase46b_historical_recovery_validation.json`

Checks include:

- Schema columns present
- Authoritative row not overwritten on re-import
- All imports tagged `source=legacy_import` with metadata columns
- Test fixture quarantined
- Duplicate re-run skips all rows
- Quarantined rows excluded from public archive API

### Production smoke

Script: `scripts/phase46b_production_smoke.py`  
Backup: `/opt/worldcup-predictor/backups/deploy-phase46b-20260621-200221`

| Check | Result |
|-------|--------|
| `archive_total` | 56 |
| `legacy_import_count` | 44 |
| `authoritative_count` | 12 (unchanged) |
| `legacy_quarantined` | 1 |
| `schema_import_columns` | True |
| `no_legacy_overwrites_authoritative` | True |

---

## Production import detail

| Count | Value |
|-------|------:|
| Recoverable candidates merged | 56 |
| Already in archive (skipped) | 12 |
| New legacy imports | 44 |
| Quarantined imports | 1 |
| Public archive rows (non-quarantined) | 55 |

The 12 skipped rows are the pre-existing authoritative predictions (`background`, `user_predict`, etc.) — import correctly refused to overwrite them.

---

## Local import detail

| Count | Value |
|-------|------:|
| Archive before | 2 |
| Imported | 28 |
| Quarantined | 2 (includes test fixtures 99, 123) |
| Duplicates skipped | 2 |
| Archive after | 30 |

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/database/migrations.py` | Phase 46B columns |
| `worldcup_predictor/database/repository.py` | `insert_worldcup_stored_prediction_legacy_import`, quarantine-aware list/count |
| `worldcup_predictor/automation/worldcup_background/legacy_prediction_import.py` | Import engine |
| `worldcup_predictor/api/global_prediction_archive.py` | Exclude quarantined; detect `legacy_import` source |
| `worldcup_predictor/cli/commands.py` | CLI handler |
| `main.py` | `worldcup-import-legacy` command |
| `scripts/validate_phase46b_historical_recovery.py` | Validation |
| `scripts/phase46b_post_deploy.py` | Production import runner |
| `scripts/phase46b_production_smoke.py` | Production smoke |
| `scripts/deploy_phase46b_production.sh` | Deploy orchestration |

---

## What was NOT changed

- Prediction engine, WDE, raw probabilities
- Evaluation quarantine logic (Phase 45B) — separate from stored-prediction quarantine
- Stripe / billing configuration

---

## Follow-up (Phase 46C+)

1. **46C** — Wire advanced market evaluation (HT, correct score, first goal, goalscorer) into WC pipeline
2. **Re-evaluate imported rows** — run `worldcup-auto-evaluation` after result refresh for finished fixtures
3. **Review quarantined row** — inspect the 1 production quarantined import; promote manually if quality is acceptable

---

## Rollback

Production DB backup before import:

```
/opt/worldcup-predictor/backups/deploy-phase46b-20260621-200221/football_intelligence.db
```

To rollback archive only:

```bash
cp BACKUP/football_intelligence.db data/football_intelligence.db
systemctl restart worldcup-api
```
