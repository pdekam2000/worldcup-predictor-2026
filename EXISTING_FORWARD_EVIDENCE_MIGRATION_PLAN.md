# Existing Forward Evidence Migration Plan

## Scope

Preserve authentic frozen prematch evidence from the local Phase 7B evaluation database without committing DB bytes to git.

## Source (forensic workspace runtime)

- Path: `C:\Users\kaman\Desktop\Footbal\data\evaluation\forward_prediction_tracking.db`
- Fixtures: **1494204**, **1494205**, **1494208**
- Status: all `evaluation_status=PENDING`
- Evidence: Top1–Top5 complete (15 rank rows), payload hashes intact

## Target (production runtime)

- Path: `/opt/worldcup-predictor/data/evaluation/forward_prediction_tracking.db`
- Schema: unified A+B schema with optional columns (migrations are idempotent)

## Migration procedure (controlled deploy only)

1. **Pre-check production DB**
   - If DB absent: bootstrap via `connect_eval_db()` on deploy (schema only).
   - If DB present: verify no rows exist for fixture_ids 1494204, 1494205, 1494208.

2. **Export source rows (read-only)**
   ```bash
   python scripts/_export_forward_evidence_rows.py --fixture-ids 1494204,1494205,1494208
   ```
   Produces JSON manifest with:
   - `frozen_predictions` rows
   - `exact_score_rankings` rows
   - payload_hash values
   - frozen_at / generated_at timestamps

3. **Import on production**
   - Use `INSERT OR IGNORE` keyed on `(fixture_id, payload_hash)`.
   - Preserve `evaluation_status=PENDING`.
   - Do **not** regenerate predictions or re-run MCP.

4. **Post-import verification**
   - Row count = 3 frozen_predictions
   - Rank rows = 15 (5 per fixture)
   - All PENDING
   - Payload hashes match export manifest
   - No duplicate fixture_id rows with different payload_hash unless explicitly documented

## Do not

- Copy entire local DB file blindly (may contain dev-only batches)
- Regenerate Tier A backfills postmatch
- Duplicate rows on re-deploy (idempotent import only)
- Commit DB to git

## Rollback

- Backup production eval DB before import: `forward_prediction_tracking.db.bak.YYYYMMDD`
- Remove imported rows by prediction_id if verification fails
