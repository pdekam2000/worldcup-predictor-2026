# Storage Contract — Football Predictor Platform

**Version:** 1.0 (Phase 44D)  
**Effective:** 2026-06-21  
**Status:** AUTHORITATIVE

This document defines **ownership**, **write rules**, **read rules**, and **sync rules** for the three persistence layers used by the platform.

---

## 1. PostgreSQL (SaaS primary)

**Path:** `DATABASE_URL` — production PostgreSQL  
**Access:** `worldcup_predictor/database/postgres/*`, `saas_uow()`

### Owns

| Domain | Tables (representative) |
|--------|-------------------------|
| Identity & auth | `users`, password reset tokens, email verification |
| Subscriptions & billing | `subscriptions`, `billing_invoices`, Stripe customer IDs |
| Per-user SaaS logs | `user_prediction_history`, `user_daily_prediction_usage` |
| Admin / audit | contact messages, admin audit where PG-backed |

### Write rules

- **Only** via SaaS repositories inside `saas_uow()` transactions.
- User history writes are **best-effort** on predict; never block prediction pipeline.
- Billing state changes require **Stripe webhook authority** (39B-3) or admin/manual override.
- Never store full prediction payloads or raw probabilities here.

### Read rules

- Authenticated API routes for `/api/user/*`, `/api/billing/*`, `/api/history?scope=my`.
- Admin routes with `require_admin_user`.
- No direct SQLite → PG mirroring of intelligence payloads.

### Sync rules

- **No automatic sync** from SQLite intelligence DB.
- User history enriched at **read time** via `FixtureOutcomeResolver` (Phase 29).
- Subscription plan is source of truth in PG; quota checks read PG only.

---

## 2. SQLite (`football_intelligence.db`)

**Path:** `SQLITE_PATH` / `data/football_intelligence.db`  
**Access:** `FootballIntelligenceRepository`

### Owns

| Domain | Tables / artifacts |
|--------|-------------------|
| Fixtures & results | `fixtures`, `fixture_results`, `fixture_enrichment` |
| Prediction intelligence | `predictions`, `prediction_markets`, `worldcup_stored_predictions` |
| Evaluations & performance | `worldcup_prediction_evaluations`, `worldcup_accuracy_summary` |
| Caches & provider data | `odds_snapshots`, `xg_snapshots`, `sportmonks_fixture_enrichment`, national team caches |
| Learning (SQLite) | `learning_records_v2`, `learning_reports` |
| File cache mirror | `.cache/predictions/` (fast API path, synced on store) |

### Write rules

- Intelligence writes via repository upserts; **never** from frontend directly.
- `worldcup_stored_predictions.payload_json` is **immutable for evaluation** — eval job reads only.
- Background daily job + user predict both upsert stored predictions (dedupe by `fixture_id` PK).
- Auto evaluation (Phase 44A) writes **only** `worldcup_prediction_evaluations` + summary JSON.

### Read rules

- Global archive: `GET /api/history?scope=global|all`
- Performance Center: `GET /api/performance/summary`, `GET /api/best-tips`
- Predict cache lookup before pipeline run
- Admin accuracy center

### Sync rules

- Every `worldcup_stored_predictions` upsert also updates `.cache/predictions/` file cache.
- PG user history **does not** auto-sync into SQLite archive.
- Fixture results synced from API / `match_results.jsonl` into `fixture_results`.

---

## 3. JSONL (legacy / research)

**Paths:**

| File | Purpose |
|------|---------|
| `data/predictions/prediction_history.jsonl` | Global learning memory (pre-SaaS) |
| `data/verification/prediction_verification.jsonl` | Verification export log |
| `data/results/match_results.jsonl` | Finished match outcomes (resolver input) |
| `data/shadow/*.jsonl` | Phase replay / shadow experiments (non-prod) |

### Owns

- Historical **append-only** learning records
- Offline verification exports
- Match outcome fallback for `FixtureOutcomeResolver`
- Research / calibration replays (shadow)

### Write rules

- Append-only via dedicated stores (`PredictionHistoryStore`, verification writers).
- **Not** used for SaaS user-facing history or billing.
- Shadow JSONL must never be promoted to production metrics without explicit migration.

### Read rules

- Streamlit / CLI accuracy tools
- `FixtureOutcomeResolver` reads `match_results.jsonl`
- Calibration / replay scripts only

### Sync rules

- **No automatic promotion** to Performance Center metrics (Phase 44 audit finding).
- Optional export from SQLite; import requires explicit migration design.
- Production may omit dev-only shadow files.

---

## 4. Cross-layer matrix

| Concern | PostgreSQL | SQLite | JSONL |
|---------|------------|--------|-------|
| User login | ✅ | ❌ | ❌ |
| Subscription plan | ✅ | ❌ | ❌ |
| User viewed predictions | ✅ (1X2 only) | ❌ | ❌ |
| Full prediction payload | ❌ | ✅ | ✅ (legacy) |
| Global public archive | ❌ | ✅ | ❌ |
| Performance / Best Tips | ❌ | ✅ | ❌ |
| Match results | ❌ | ✅ | ✅ (fallback) |
| Stripe billing | ✅ | ❌ | ❌ |

---

## 5. Prohibited patterns

1. Writing SaaS user PII into SQLite global archive payloads.
2. Using JSONL counts for `/api/performance/summary` without migration.
3. Mutating `payload_json` during evaluation backfill.
4. Duplicating subscription state in SQLite.
5. Silent `except: pass` on enrichment paths (Phase 44B — use `log_enrichment_failure`).

---

## 6. Change control

Changes to this contract require:

- Architecture review if a new storage layer is proposed.
- Validation script update if read/write boundaries shift.
- Report filed under `PHASE_*` with explicit migration plan.

**Maintainer note:** Triple storage is intentional during SaaS transition; unification must be explicit, not accidental.
