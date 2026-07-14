# Tier B Legacy Shadow Storage — Transition Report

**Phase:** 2C  
**Policy:** **Option B — Structured DB canonical; JSONL compatibility mirror**

---

## Before

| Store | Authority | Eval-ready |
|---|---|---|
| JSONL | de facto owner audit | ❌ |
| WSP + ECSE | sometimes populated | partial |
| frozen_predictions | bridge after Phase 3 | ✅ when bridge ran |

---

## After Phase 2C

| Store | Authority | Notes |
|---|---|---|
| WSP + ECSE + freeze + rankings | **Canonical** | `prediction_scope=owner_shadow`, `public_visible=0` |
| JSONL | **Mirror only** | `structured_db_canonical=true`, links `freeze_id` + `content_hash` |

---

## Runtime dependencies

- GPT worker: MCP predict → bridge → `finalize_tier_b_structured_persistence` → JSONL append
- MCP direct: auto `resolve_tier_b_bridge_context` for Tier B → finalize
- owner_daily: unchanged (`prediction_scope=owner_daily` for all fixtures in that path)

JSONL is **not** read for evaluation or freeze construction.

---

## Backfill

- Dry-run: `scripts/dry_run_tier_b_structured_persistence_backfill.py`
- No broad automatic backfill in Phase 2C
- Unsupported legacy rows: `LEGACY_TIER_B_INCOMPLETE_NOT_BACKFILLED`

---

## Data safety

- JSONL not deleted
- No production DB copy from local
- No regeneration of existing freezes
