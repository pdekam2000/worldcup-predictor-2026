# Phase 3 / 2A — Existing Freeze Implementation Audit

**Generated:** 2026-07-14  
**Baseline SHA:** `9c71c2652b58c5f4eb1cb1f4dc7e62c25d500923`

---

## 1. What freeze functionality already exists?

| Module | Role |
|---|---|
| `forward_evaluation/freeze.py` | `capture_canonical_prediction()` — **re-runs MCP** per fixture; `validate_prematch_integrity()`; `store_frozen_prediction()` insert |
| `forward_evaluation/db.py` | Eval DB schema + `_SCHEMA_MIGRATIONS` (5 tier columns) |
| `forward_evaluation/orchestrator.py` | Daily discovery → MCP capture → store |
| `forward_evaluation/evaluate.py` | Reads frozen rows; updates `evaluation_status` only |
| `forward_evaluation/context.py` | ECSE mass/entropy helpers reused in envelope |

Production state: **3** `frozen_predictions` rows (manual `--date 2026-07-12` run); **0** `market_evaluations`.

---

## 2. What is reusable?

| Component | Reuse |
|---|---|
| `validate_prematch_integrity()` | Extend for WSP/ECSE-source path (prematch timestamp rules) |
| `_payload_hash()` / forbidden result keys | Basis for content hash |
| `_rank_rows()` ECSE-only branch | Rank extraction without MCP |
| `context.py` entropy/mass | Unchanged |
| `fixture_model.py` tier/scope helpers | Tier A/B visibility |
| `store_frozen_prediction()` insert shape | Extended via repository |
| `UNIQUE(fixture_id, payload_hash)` | Idempotency constraint — keep |
| `exact_score_rankings` child table | Unchanged |

---

## 3. What is incomplete?

| Gap | Phase 2A fix |
|---|---|
| No WSP+ECSE-only capture path | **New `freeze_service.py`** |
| `capture_canonical_prediction()` calls MCP | Bridge path must not use it |
| No source link columns | Additive migration |
| No `source_payload_hash` vs `content_hash` split | New hashing module |
| No quarantine table | Add `freeze_quarantine` |
| No explicit source selection rules | `freeze_service` selection |
| No repository immutability guard | New `forward_evaluation/repository.py` |
| `batch_id` required but bridge has no batch | `FREEZE-SERVICE-v2` sentinel |
| Tier B `public_visible` not stored | New column |
| GPT/JSONL not excluded as authority | Service reads WSP/ECSE only |

---

## 4. Are current freeze rows immutable?

**Partially.** Insert-only in practice; no UPDATE on payload columns in code. `evaluate.py` updates `evaluation_status` only. No DB trigger prevents payload UPDATE — **repository guard added in 2A**.

---

## 5. Are source WSP/ECSE IDs stored?

**No.** Current schema has no `worldcup_stored_prediction_id`, `ecse_snapshot_id`, or `source_commit_sha`. Only implicit fixture_id linkage.

---

## 6. Are hashes stable?

**Mostly.** `_payload_hash()` uses `json.dumps(sort_keys=True)`. Volatile fields excluded via `_FORBIDDEN_RESULT_KEYS`. No separate source hash; MCP runtime fields could drift if re-run. **WSP+ECSE path fixes drift.**

---

## 7. Are duplicate freezes possible?

**Constrained.** `UNIQUE(fixture_id, payload_hash)` prevents identical payloads. Different payloads for same fixture allowed. `_should_reuse()` returns latest row without hash check — **bridge service uses content_hash idempotency instead.**

---

## 8. Are post-kickoff rows currently rejected?

**Partially.** `validate_prematch_integrity()` rejects `generated_at >= kickoff` and `frozen_at > kickoff`. Orchestrator can still call MCP after kickoff with live gates. **New service rejects post-kickoff sources and post-kickoff capture by default.**

---

## 9. Are model versions stored?

**Yes** — `wde_model_version`, `ecse_model_version` columns populated from MCP/ECSE snapshot. BTTS/O-U versions not separate columns yet.

---

## 10. Are Tier A/Tier B scopes preserved?

**Partially.** `tier`, `validation_tier`, `display_status` exist. No `prediction_scope` or `public_visible`. Tier B stored as tier=B in 3 prod rows. **2A adds scope + public_visible enforcement.**

---

## Recommendation

Implement shared `freeze_service.create_or_reuse_freeze()` reading WSP+ECSE only; extend schema additively; keep legacy `capture_canonical_prediction()` for orchestrator until Phase 2G timer split.
