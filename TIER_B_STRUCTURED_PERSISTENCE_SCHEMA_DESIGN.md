# Tier B Structured Persistence — Schema Design

**Phase:** 2C  
**Decision:** **NO new table required**

---

## Reused tables

| Table | Tier B role |
|---|---|
| `worldcup_stored_predictions` | WDE + markets + odds freshness payload |
| `ecse_prediction_snapshots` | ECSE lambdas + Top1–Top5 blobs |
| `frozen_predictions` | Immutable evaluation envelope |
| `exact_score_rankings` | Structural Top1–Top5 ranks |

---

## Additive migration (Phase 2C)

`PHASE2C_TIER_B_COLUMNS` in `worldcup_predictor/database/migrations.py`:

| Table | Column | Type | Purpose |
|---|---|---|---|
| `worldcup_stored_predictions` | `prediction_scope` | TEXT | `owner_shadow` / `production` / `owner_daily` |
| `worldcup_stored_predictions` | `validation_tier` | TEXT | `A` / `B` |
| `worldcup_stored_predictions` | `source_runtime` | TEXT | `mcp` / `gpt_actions` / `owner_daily` |
| `ecse_prediction_snapshots` | `prediction_scope` | TEXT | mirrors WSP scope |
| `ecse_prediction_snapshots` | `validation_tier` | TEXT | `A` / `B` |
| `ecse_prediction_snapshots` | `source_runtime` | TEXT | provenance |

Indexes: `idx_wsp_prediction_scope`, `idx_ecse_snap_prediction_scope`

**PK unchanged:** `fixture_id` remains PK on WSP; one row per fixture (Tier B does not collide with Tier A on same fixture in current registry).

---

## Idempotency / uniqueness

| Layer | Rule |
|---|---|
| WSP | One row per `fixture_id`; scope stamped on finalize |
| ECSE | One row per `fixture_id`; scope stamped on finalize |
| Freeze | `UNIQUE(fixture_id, payload_hash)` + `create_or_reuse_freeze` content_hash |
| Rankings | PK `(prediction_id, rank)` — no duplicate ranks per freeze |
| JSONL | `payload_hash` dedup on append |

Identical content → reuse freeze. Legitimate pre-kickoff content change → new `content_hash`, new freeze version; prior freeze preserved.

---

## Forbidden changes (not performed)

- No destructive column removal
- No PK changes
- No automatic duplicate row deletion
- No public visibility default true
