# Tier B Structured Persistence — Current State Audit

**Phase:** 2C (pre-implementation audit)  
**Baseline SHA:** `4692cea`  
**Generated:** 2026-07-14

---

## Lifecycle trace (GPT Actions / MCP → freeze)

| Step | Tier B behavior | Storage |
|---|---|---|
| Discovery / routing | `fixture_tier()` → B; `owner_shadow` scope via GPT worker | In-memory |
| Odds gate | `controlled_owner_odds_lookup` (Tier B only) | Diagnostics in evidence |
| WDE | `run_daily_wde` → `upsert_worldcup_stored_prediction` | `worldcup_stored_predictions.payload_json` |
| ECSE | `run_daily_ecse` → `insert_snapshot` | `ecse_prediction_snapshots` |
| Bridge | `maybe_capture_after_prediction_persistence` | `frozen_predictions` + `exact_score_rankings` |
| JSONL mirror | `freeze_tier_b_shadow_prediction` (GPT worker) | `data/shadow/tier_b_domestic_predictions.jsonl` |

**Gap before 2C:** MCP direct calls defaulted `prediction_scope=production` for Tier B; WSP/ECSE lacked structured scope columns; JSONL not linked to freeze IDs.

---

## Field coverage (pre-2C)

| Field group | Generated | Structured column | JSON only | In freeze | Gap |
|---|---|---|---|---|---|
| WDE decision / FT marginal | ✅ | freeze scalars | WSP payload | ✅ | WSP scope column missing |
| H/D/A probabilities | ✅ | freeze scalars | WSP payload | ✅ | — |
| BTTS / O/U | ✅ | freeze scalars | WSP payload | ✅ | — |
| ECSE Top1–Top5 | ✅ | ECSE + rankings table | JSON blobs | ✅ | ECSE scope column missing |
| Top3/Top5 mass | ✅ | freeze scalars | — | ✅ | — |
| Odds freshness | ✅ | freeze + WSP | payload | ✅ | — |
| Data quality | ✅ | ECSE score + payload | payload | ✅ | — |
| prediction_scope | ✅ (bridge) | freeze only | JSONL partial | ✅ | WSP/ECSE not stamped |
| public_visible | ✅ | freeze `0` | JSONL | ✅ | MCP default was wrong |
| content_hash | ✅ | freeze | forward_eval block | ✅ | — |

---

## Tables reused (no new table)

- `worldcup_stored_predictions` — WDE canonical payload
- `ecse_prediction_snapshots` — ECSE canonical snapshot
- `frozen_predictions` — evaluation-ready envelope (`prediction_scope=owner_shadow`)
- `exact_score_rankings` — Top1–Top5 structural child rows

---

## JSONL shadow file

**Path:** `data/shadow/tier_b_domestic_predictions.jsonl`  
**Role:** Non-authoritative audit mirror (Phase 6B legacy)  
**Post-2C:** Remains written; adds `freeze_id`, `content_hash`, `structured_db_canonical=true`
