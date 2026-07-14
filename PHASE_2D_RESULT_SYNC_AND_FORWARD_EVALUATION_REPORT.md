# Phase 2D — Result Sync and Forward Market Evaluation Report

**Date:** 2026-07-14  
**Commit:** `1e2928c` — `feat: add controlled result sync and forward market evaluation`  
**Final status:** `RESULT_SYNC_AND_FORWARD_EVALUATION_COMPLETE`

---

## Deployment alignment

| Environment | SHA |
|-------------|-----|
| Local | `1e2928c` |
| origin/main | `1e2928c` |
| Production | `1e2928c` |

Services: `worldcup-api`, `worldcup-gpt-actions`, `worldcup-mcp` — **active**  
Timers: **not installed / not activated**  
Full batch evaluation: **stopped** (controlled acceptance only)

---

## Answers (Parts A–T)

### 1. Canonical result source?
Production: `fixture_results` in `football_intelligence.db`. Forward-eval mirror: `actual_results` in `forward_prediction_tracking.db`. Sync via `sync_result_for_fixture()` (DB-first, optional API-Football fallback).

### 2. Regulation vs ET vs penalties?
`regulation_score_for_evaluation()` + `build_canonical_result_record()` separate regulation goals from ET/PEN fields. Market evaluation uses regulation only.

### 3. Existing result tables reused?
Yes. No new result table. Extended `actual_results` and `market_evaluations` only.

### 4. Migration required?
Additive eval-DB migration only (`_PHASE2D_MIGRATIONS`). Production main DB: **NO_SCHEMA_MIGRATION_REQUIRED**.

### 5. Result idempotency?
`fixture_id` PK on `actual_results`; `result_content_hash`; repeat sync reuses row and updates `last_verified_at`.

### 6. Provider conflicts?
Internal regulation vs FT mismatch → `PROVIDER_CONFLICT` / blocked. No silent overwrite.

### 7. Freeze integrity?
`verify_freeze_integrity()` checks existence, prematch timestamps, rankings, scope, immutability.

### 8. Predictions regenerated?
**No.** Evaluation reads frozen payloads and rankings only. Acceptance verified no freeze/orchestrator calls.

### 9–12. Market evaluation semantics
- **WDE:** `wde_decision` vs `actual_1x2` (regulation)
- **FT Marginal:** `ft_marginal_direction` vs `actual_1x2` (separate column)
- **BTTS:** yes if both teams score regulation goals; unavailable → `NOT_EVALUATED_UNAVAILABLE`
- **O/U 2.5:** total regulation goals ≥3 over, ≤2 under; unavailable → `NOT_EVALUATED_UNAVAILABLE`

### 13. Unavailable components?
`NOT_EVALUATED_UNAVAILABLE` — never counted as MISS.

### 14–16. ECSE Top1/3/5
From frozen `exact_score_rankings` only. Top1/3/5 hit flags vs actual regulation exact score.

### 17. Actual ECSE rank?
Stored as `actual_score_rank` (1–5, `OUTSIDE_TOP5`, or unavailable).

### 18. Tier A / B / owner_daily separation?
`prediction_scope`, `validation_tier`, `public_visible`, `eligibility_class` on evaluation rows. Tier B / owner_shadow / owner_daily → `OWNER_ONLY`.

### 19. Quarantined evaluations?
Quarantined freezes blocked at integrity gate; `eligibility_class=QUARANTINED`.

### 20. Acceptance fixtures

| fixture_id | scope | role |
|------------|-------|------|
| 1581821 | — | Result-sync idempotency (no freeze) |
| 1494204 | production / Tier A | Full evaluation |
| 1494208 | production / Tier A | Full evaluation + partial ECSE |
| 1497629 | owner_shadow / Tier B | Prematch — sync/eval blocked |
| 1554381 | owner_daily | Prematch — sync/eval blocked |

### 21. Acceptance results

**1494204** (2-0): WDE HIT, FT Marginal HIT, BTTS HIT, O/U MISS, ECSE Top1/3/5 HIT, rank 1  
**1494208** (2-0): WDE MISS, FT Marginal HIT, BTTS MISS, O/U HIT, ECSE Top1 MISS / Top3&5 HIT, rank 3  
**1581821** (2-1): sync inserted + reused; no freeze (expected)

### 22. Idempotency?
Yes — result sync on 1581821 reused; evaluations on 1494204/1494208 returned `already_evaluated` on repeat.

### 23. Freezes modified?
**No** — `content_hash` and freeze rows unchanged; only `evaluation_status` updated on evaluated freezes.

### 24. Predictions regenerated?
**No.**

### 25. Phase 2A/2B/2C regression?
Local validator: Phase 2A/2B/2C tests **PASS**; compileall **PASS**.

### 26. Services active?
Yes (production verified post-restart).

### 27. Local = Origin = Production?
Yes — all at `1e2928c`.

### 28. Timers disabled?
Yes — no new timers.

### 29. Full batch stopped?
Yes — dry-run inventory only; 2 evaluation rows inserted (acceptance set).

### 30. Final status
`RESULT_SYNC_AND_FORWARD_EVALUATION_COMPLETE`

---

## Local validation

| Suite | Result |
|-------|--------|
| Phase 2D tests (27 cases) | PASS |
| Phase 2A freeze | PASS |
| Phase 2B bridge | PASS |
| Phase 2C Tier B | PASS |
| compileall | PASS |

## Production dry-run inventory

15 active freezes; 10 `RESULT_MISSING` (prematch); 5 `OWNER_ONLY`. See `PHASE_2D_FORWARD_EVALUATION_DRY_RUN.md`.

## Artifacts

- `artifacts/phase2d_production_acceptance.json` (summary)
- Full production JSON: `/tmp/phase2d_production_acceptance.json` on server

## STOP boundary

Completed: audit → implement → dry-run → local validation → commit → push → deploy → controlled acceptance → idempotency → report.

**Not started:** timers, full historical backfill, public accuracy dashboard changes, model changes.
