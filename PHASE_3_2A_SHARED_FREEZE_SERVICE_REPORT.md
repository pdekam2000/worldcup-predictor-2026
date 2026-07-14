# Phase 3 / 2A — Shared Freeze Service Report

**Generated:** 2026-07-14  
**Starting SHA:** `9c71c2652b58c5f4eb1cb1f4dc7e62c25d500923`  
**Production SHA (unchanged):** `c9764847ac974844078365de0c5e4f4b507b1fb2`  
**Final status:** `FORWARD_FREEZE_SERVICE_IMPLEMENTED`

No production deploy. No production DB access. No timers installed.

---

## 1. What existing freeze code was reused?

| Reused | From |
|---|---|
| Prematch integrity concepts | `freeze.py::validate_prematch_integrity` |
| ECSE rank/mass/entropy helpers | `context.py` |
| Tier A/B fixture metadata | `fixture_model.py` |
| WDE semantic extraction | `gpt_actions/bridge_semantics.py` |
| ECSE snapshot hydration | `research/ecse_live/store.py` |
| Eval DB base schema + UNIQUE constraint | `forward_evaluation/db.py` |
| Legacy MCP freeze path | **Unchanged** — `capture_canonical_prediction()` retained for orchestrator |

---

## 2. What schema changes were added?

Additive migrations in `forward_evaluation/db.py` (`_FREEZE_V2_MIGRATIONS`):

- Source links: `worldcup_stored_prediction_id`, `ecse_snapshot_id`, `source_job_id`, `odds_snapshot_id`, `source_commit_sha`, `source_payload_hash`, `content_hash`
- Identity/scope: `prediction_scope`, `public_visible`, `provider_fixture_id`, team names, `season`, `league_id`
- Timestamps: `odds_fetched_at_utc`, `last_valid_prematch_time_utc`
- Payload JSON columns: WDE/BTTS/O-U/ECSE/complete
- Immutability: `immutable`, `freeze_version`, `freeze_status`, execution status columns, `quarantine_reason`
- New table: `freeze_quarantine`
- Indexes: scope, kickoff, ecse snapshot, WSP, content/source hashes

**Rollback limitation:** SQLite ADD COLUMN is irreversible without DB restore; no data loss on rollback — old columns remain.

---

## 3. Canonical WSP source rule

- Primary key: `fixture_id` (WSP has no surrogate id)
- Active row: `is_active=1`, not quarantined
- Explicit `worldcup_stored_prediction_id` must equal `fixture_id`
- Latest valid prematch: `predicted_at < kickoff`
- Complete WDE payload via `extract_wde_semantics()`

---

## 4. Canonical ECSE source rule

- Explicit `ecse_snapshot_id` → `get_snapshot_by_id` with fixture match
- Otherwise `get_snapshot(fixture_id)` (one row per fixture)
- Requires Top5 complete ranks + `generated_at < kickoff`

---

## 5. How are timestamps validated?

- Parse ISO / legacy UTC strings to timezone-aware datetimes
- Reject if `predicted_at` or `generated_at >= kickoff`
- Reject capture if `now >= kickoff` (default; overridable for future backfill)
- Quarantine if no generated timestamp available

---

## 6. How is post-kickoff capture blocked?

- Hard reject: `POST_KICKOFF_GENERATION`, `POST_KICKOFF_CAPTURE`
- No freeze written when kickoff has passed (unless `allow_post_kickoff_capture` in source_context — not enabled by default)

---

## 7. How are hashes calculated?

| Hash | Input |
|---|---|
| `source_payload_hash` | fixture_id + WSP predicted_at + full WSP payload + ECSE id/timestamp/top5 |
| `content_hash` / `payload_hash` | Full envelope + complete_payload; excludes volatile fields (frozen_at, prediction_id, etc.) |

Canonical JSON: `sort_keys=True`, stable separators.

---

## 8. How is idempotency enforced?

1. Compute `content_hash`
2. Lookup `UNIQUE(fixture_id, payload_hash)` via `fetch_by_fixture_and_hash`
3. Return existing `prediction_id` with `reused=true`

---

## 9. How are conflicts handled?

- Same source IDs + same `source_payload_hash` + different `content_hash` → `SOURCE_PAYLOAD_CONFLICT` (tampered freeze row)
- Different `source_payload_hash` for same fixture → **new freeze row** (multiple prematch versions preserved)
- Quarantine rows recorded in `freeze_quarantine`

---

## 10. Can multiple legitimate prematch versions coexist?

**Yes.** Distinct `source_payload_hash` values create distinct freeze rows under existing `UNIQUE(fixture_id, payload_hash)`.

---

## 11. Are Tier B freezes private?

**Yes.** `prediction_scope=owner_shadow` and `public_visible=0` enforced for Tier B; public visibility true rejected for Tier B.

---

## 12. Were any predictions regenerated?

**No.** Service reads WSP/ECSE only; MCP `run_fixture_prediction` not called.

---

## 13. Were any providers called?

**No.** No API-Football, Sportmonks, or odds refresh during freeze.

---

## 14. Were any existing freezes overwritten?

**No.** Insert-only for payload columns; idempotent reuse returns existing row.

---

## 15. What did the historical dry-run find?

Local DB (`football_intelligence.db`):

| Category | Count |
|---|---:|
| ELIGIBLE_FREEZE | 5 |
| POST_KICKOFF_SOURCE | 38 |
| MISSING_ECSE | 162 |

Report: `FORWARD_EVALUATION_FREEZE_CANDIDATE_DRY_RUN.md`

---

## 16–18. Validation

| Check | Result |
|---|---|
| Unit tests | **32/32 PASS** |
| Integration tests | included above |
| Validator `validate_phase3_2a_shared_freeze_service.py` | **47/47 PASS** |

---

## 19. Commit

Recorded after push in git log (see below).

---

## 20. Is Phase 2B ready?

**Yes — pending approval.** Shared `create_or_reuse_freeze()` is ready for owner_daily / GPT Actions bridge hooks. No bridge wired in this phase.

---

## Files delivered

- `worldcup_predictor/forward_evaluation/freeze_service.py`
- `worldcup_predictor/forward_evaluation/repository.py`
- `worldcup_predictor/forward_evaluation/hashing.py`
- `worldcup_predictor/forward_evaluation/db.py` (migrations)
- `tests/forward_evaluation/test_freeze_service.py`
- `tests/forward_evaluation/test_freeze_service_integration.py`
- `tests/forward_evaluation/conftest.py`
- `scripts/dry_run_forward_evaluation_freeze_candidates.py`
- `scripts/validate_phase3_2a_shared_freeze_service.py`
- `PHASE_3_2A_EXISTING_FREEZE_IMPLEMENTATION_AUDIT.md`
- `FORWARD_EVALUATION_FREEZE_CANDIDATE_DRY_RUN.md`

---

## STOP

Phase 3 / 2A complete. Do not deploy. Do not begin owner_daily bridge until Phase 2B approved.
