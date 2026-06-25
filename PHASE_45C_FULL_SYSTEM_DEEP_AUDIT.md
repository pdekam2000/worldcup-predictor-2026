# Phase 45C — Full System Deep Audit

**Mode:** READ ONLY — no code changes, no deploy, no database modifications  
**Date:** 2026-06-21  
**Scope:** WorldCup Predictor SaaS post–Phase 45B  
**Production server:** `91.107.188.229` / https://footballpredictor.it.com  
**Local workspace:** `c:\Users\kaman\Desktop\Footbal`

---

## Executive summary

The platform is **functionally live** for core SaaS flows (auth, predict, history, billing in Stripe live mode, admin accuracy/learning). After Phase 45B, **public accuracy is honest** (0 real evaluations; 2 test rows quarantined).

The deepest systemic gaps are:

1. **Historical prediction fragmentation** — authoritative global archive has **12** production rows while **39 cache files**, **17 legacy SQLite rows**, and **101 JSONL lines** hold additional or overlapping data that was never unified.
2. **Live result latency** — evaluation depends on a **30-minute systemd timer** and sequential per-fixture API refresh; typical FT→UI update latency is **0–30 minutes** (plus API/cache dependencies).
3. **Accuracy metric duplication** — three parallel accuracy systems (SQLite evals, JSONL `AccuracyTrackerService`, legacy verification) with different scopes and fallbacks.
4. **Frontend trust debt** — landing page marketing stats/testimonials are **hardcoded fiction**; several admin/user pages are stubs (`ApiSettingsPage`, `ContactPage`, premium history blocks).
5. **Provider data underuse** — Sportmonks scores/events/state, API-Football events, odds movement, and most weather fields are fetched or stored but not consumed in WDE.

---

## 1. Historical Prediction Recovery

### 1.1 Source inventory (production — read-only counts)

| Source | Rows / files | Unique fixtures (est.) | Full payload? | Timestamp? | Evaluated? | Classification |
|--------|-------------:|------------------------|---------------|------------|------------|----------------|
| **`worldcup_stored_predictions`** (SQLite) | **12** | **12** | **Yes** (`payload_json`) | `predicted_at` | 2 total, **0 public** (quarantined) | **Authoritative global archive** |
| **`worldcup_prediction_evaluations`** | **2** | 2 | Partial (`detail_json`) | `evaluated_at` | 2 (both quarantined) | Eval layer |
| **`.cache/predictions/`** | **39** JSON | ~39 (est.) | **Yes** (wrapped payload) | `cached_at` | N/A | **Recoverable gap-fill** — likely >12 fixtures |
| **`predictions`** (legacy SQLite) | **17** | **5** | Partial (header + markets split) | `created_at` | via `verification_results` | Legacy engine |
| **`prediction_markets`** | **85** | 17 prediction_ids | Market values only | — | Partial | Legacy supporting |
| **`verification_results`** | **70** | — | Per-market verify | `verified_at` | Yes (audit) | Not authoritative storage |
| **`prediction_history.jsonl`** | **101** lines | ~50 (Phase 44 audit) | Partial (1X2/OU/HT flat) | `created_at` | Some fields | Pre-SaaS learning memory |
| **`prediction_verification.jsonl`** | **542** lines | **16** | Per-market | `verified_at` | Yes | Audit export |
| **`match_results.jsonl`** | **16** | **16** | Results only | `finished_at` | N/A | Resolver input |
| **`user_prediction_history`** (PostgreSQL) | **9** (Phase 44) | **3** | **No** — 1X2 summary only | `viewed_at` | Enriched at read | **User-private** |
| **`data/shadow/*.jsonl`** | **0 on prod** | — | Varies | Varies | Research | **Never import to public metrics** |
| **SQLite backups** (`backups/sqlite/`) | Rotation script exists | — | Full DB if present | — | — | Disaster recovery |

**Local dev workspace** (for comparison): 2 stored, 108 JSONL lines / 27 fixtures, 4 cache files, 17 legacy predictions.

### 1.2 Totals and reconciliation

| Metric | Production | Notes |
|--------|------------|-------|
| **Total prediction-like records (all sources, naive sum)** | **~800+** | Includes duplicate markets, verification rows, JSONL duplicates |
| **Best estimate unique fixtures with any prediction artifact** | **~55–70** | Union of stored(12) + cache-only(~27) + JSONL-only(~38) + legacy-only(5) with overlap |
| **Recoverable full payloads** | **12 stored + up to ~27 cache-only** | Cache diff vs stored is highest-value recovery |
| **Evaluated (public, post-45B)** | **0** | 2 quarantined test rows excluded |
| **Missing from global archive** | **~40+ fixture artifacts** | Legacy JSONL, cache, legacy SQLite never migrated |
| **Orphaned records** | **26+ JSONL fixtures** with no `worldcup_stored_predictions` row (local count) |
| **Duplicate records** | **542 verification JSONL** with 448 dedupe keys; append-only duplicates by design | PK on stored archive prevents duplicate fixtures |

### 1.3 Duplicate detection mechanisms

| Mechanism | Location | Rule |
|-----------|----------|------|
| Global archive | `repository.upsert_worldcup_stored_prediction` | `ON CONFLICT(fixture_id)` — one row per fixture |
| Verification JSONL | `verification/store.py` | `(fixture_id, prediction_id, market)` |
| Learning JSONL | `accuracy/history_store.py` | Latest `created_at` per fixture |
| Admin audit | `GET /admin/accuracy/audit` | Duplicate stored rows count |

### 1.4 Recovery recommendation (informational only — not executed)

1. Diff `.cache/predictions/` fixture IDs vs `worldcup_stored_predictions` → upsert missing via `WorldcupPredictionStore` quality guard.  
2. Legacy `predictions` + `prediction_markets` (5 fixtures) → reconstruct payloads for admin inventory only.  
3. Do **not** promote shadow JSONL or verification logs into public performance.  
4. Fix inventory script path bug: `scripts/phase45b_legacy_prediction_inventory.py` scans wrong JSONL path (`data/prediction_history.jsonl` vs canonical `data/predictions/prediction_history.jsonl`).

---

## 2. Live Match Status Audit

### 2.1 Pipeline (post–Phase 45B)

```
systemd worldcup-evaluate-results.timer (every 30 min)
  → main.py worldcup-auto-evaluation
    → result_refresh.refresh_stored_prediction_results()
    → evaluation_trust.run_evaluation_quarantine_pass()
    → result_evaluation_job.run_evaluate_worldcup_results()
      → FixtureOutcomeResolver.resolve(fixture_id)
```

**Production timer status (read-only):** `active`  
- Last trigger: 2026-06-21 19:31:20 UTC  
- Next elapse: 2026-06-21 20:00:14 UTC  

### 2.2 How finished matches are detected

| Priority | Source | Finished when |
|----------|--------|---------------|
| 1 | `data/results/match_results.jsonl` | Status in `FT/AET/PEN` or winner known |
| 2 | SQLite `fixture_results` | Row exists with goals |
| 3 | SQLite `fixtures.status` | `FT/AET/PEN` but may lack score → `unknown` |

**Refresh path:** `result_refresh.py` calls `ApiFootballClient.get_fixture_by_id()` per stored prediction past kickoff → upserts `fixtures` + `fixture_results` + JSONL on finished.

**Not in evaluation path:** `build_match_center()` live enrichment (events, stats, red cards) — UI only.

### 2.3 Why matches stay pending

| Cause | Symptom |
|-------|---------|
| Kickoff not passed | Skipped in refresh |
| Match still live (1H/HT/2H/ET) | No JSONL write; resolver `is_finished=False` |
| No row in `worldcup_stored_predictions` | Never scanned by refresh/eval |
| 30-minute timer gap | Up to **~30 min** after FT before eval |
| API key missing / placeholder | `skipped_no_api`; stale `NS` in SQLite |
| Score missing at FT | `unknown` evaluation status |
| PG `user_prediction_history.result` column | May stay `pending` while SQLite eval exists (read-time enrichment only) |

### 2.4 Real latency estimate

| Stage | Typical latency |
|-------|-----------------|
| API-Football status update | External (minutes after FT) |
| `result_refresh` (timer-bound) | **0–30 min** after FT |
| Evaluation + summary rebuild | Same timer run (< seconds locally) |
| **End-to-end (FT → public accuracy UI)** | **~5–35 min** under normal ops |

First production refresh run (Phase 45B): 6 API fetches, 6 fixtures updated, **0 results** (no finished WC matches yet).

### 2.5 Bottlenecks and recommendations

| Bottleneck | Severity | Recommendation |
|------------|----------|----------------|
| 30-min timer only | HIGH | Add post-kickoff webhook or 5-min window for due fixtures |
| Sequential API calls (1/fixture) | MEDIUM | Batch fixtures endpoint where API allows |
| Stored-first scope only | MEDIUM | Document that only archived predictions evaluate |
| Match center not feeding eval store | LOW | Optional: write finished snapshots from match center poll |
| JSONL vs SQLite precedence confusion | MEDIUM | Single write path on refresh (already partially done) |

---

## 3. Prediction Coverage Audit

### 3.1 Markets in stored payloads (production, 12 rows)

From payload structure analysis (representative of Phase 33+ background predictions):

| Market | In payload (`detailed_markets` / probabilities) | Evaluated by `pick_evaluator` | Public accuracy column |
|--------|--------------------------------------------------|--------------------------------|------------------------|
| **1X2** | ~100% | **Yes** | `market_1x2_status` |
| **Over/Under 2.5** | ~100% | **Yes** | `market_ou_status` |
| **BTTS** | ~100% | **Yes** | `market_btts_status` |
| **Double Chance** | Partial (~1+ rows) | **Yes** | `market_dc_status` |
| **Halftime (HT bucket)** | In payload metadata | **No** in pick_evaluator | Legacy JSONL only |
| **Correct Score** | In `detailed_markets` as `correct_scores` | **No** | Not in WC eval table |
| **First Goal Team** | Partial | **No** | Summary key exists but rarely populated |
| **Goal Minute** | Unknown / rare | **No** | — |
| **Goalscorer** | Partial | **No** | — |
| Safe/Value/Aggressive/Caution picks | Most rows | **Yes** (pick tier) | In `detail_json` |

### 3.2 Legacy engine coverage (17 market rows × 5 fixtures)

| Market | Legacy rows |
|--------|------------:|
| 1x2 | 17 |
| over_under_2_5 | 17 |
| halftime_goals | 17 |
| first_goal_team | 17 |
| scoreline_exact | 17 |

Legacy has **richer market coverage** than current WC evaluation pipeline, but lives in **disconnected tables**.

### 3.3 Coverage summary

| Category | Count (production) |
|----------|-------------------:|
| Stored predictions | 12 |
| With 1X2 + O/U + BTTS | ~12 |
| With extended markets (DC, HT, FG, scorer) | Partial (subset) |
| **Public evaluated by market** | **0** (all quarantined or pending) |
| Unavailable for eval (no FT result) | 12 (all upcoming NS) |

---

## 4. Accuracy System Audit

### 4.1 Three parallel accuracy systems

| System | Data source | Used by | Status |
|--------|-------------|---------|--------|
| **A. SQLite WC evals** | `worldcup_prediction_evaluations` + `worldcup_accuracy_summary` | Performance Center (`/api/performance/summary`), Admin Accuracy | **Primary post-Phase 33**; quarantine-aware after 45B |
| **B. JSONL AccuracyTracker** | `data/predictions/prediction_history.jsonl` | `/api/accuracy/summary` fallback, CLI `accuracy-report`, Streamlit GUI | **Legacy**; 101 lines prod |
| **C. Verification layer** | `verification_results` + JSONL | CLI verify, research | Audit only |

### 4.2 UI vs API mapping

| UI surface | API | Backend builder |
|------------|-----|-----------------|
| **Performance Center** (`AccuracyCenter.jsx`) | `/api/performance/summary` | `performance_center.build_performance_summary()` |
| **Accuracy API (unused in UI)** | `/api/accuracy/summary` | `public_accuracy_summary.build_public_accuracy_summary()` |
| **Admin Accuracy Center** | `/api/admin/accuracy/evaluations` | `accuracy_center.list_accuracy_center_rows()` |
| **Learning Dashboard** | `/api/admin/learning/dashboard` | `learning_engine` + `accuracy_optimization` |

### 4.3 Duplicated / inconsistent metrics

| Issue | Detail |
|-------|--------|
| **Two public summary endpoints** | `/api/performance/summary` vs `/api/accuracy/summary` — different fallbacks (WC SQLite vs JSONL tracker) |
| **Performance rebuild on read** | `build_performance_summary()` may call `rebuild_accuracy_summary()` if evaluated=0 |
| **Learning attributes fixture-level outcome to all agents** | Inflates agent winrates when n is tiny (mitigated by n<20 guard after 45B) |
| **PG history vs global eval** | User history `result` column can disagree with SQLite eval |
| **Stale summary table** | `worldcup_accuracy_summary` only refreshed on eval/rebuild — not on quarantine until rebuild runs |
| **Best Tips** | Uses performance summary market blocks — empty when 0 public evals |

### 4.4 Post–45B state (production)

- Public evaluated: **0**
- Quarantined: **2**
- Performance Center shows empty state (correct)
- Learning Dashboard: insufficient data (correct)

---

## 5. Frontend Dead Features Audit

### Critical / high severity

| Page / component | Issue |
|------------------|-------|
| `StatsSection.jsx`, `TestimonialsSection.jsx`, `HeroSection.jsx` | **Hardcoded fake stats/users/win rates** |
| `ApiSettingsPage.jsx` | **Fully stubbed** — no backend, fake save/status |
| `ContactPage.jsx` | Form fakes success — no API |
| `FavoritesPage.jsx` | **No add-favorite UI** in Match Center |
| `PredictionHistoryDetailPage.jsx` | Premium sections "coming soon" placeholders |
| `SettingsPage.jsx` | 2FA toggle stored but non-functional |

### Medium severity

| Issue | Location |
|-------|----------|
| `/pricing` route orphaned (nav uses `#pricing` anchor) | `PricingPage.jsx` |
| Pricing copy says "no payment processing" while Stripe live exists | `PricingContent.jsx` |
| Dark mode / push prefs saved but not applied | `SettingsPage.jsx` |
| Notification bell always shows red dot | `DashboardLayout.jsx` |
| `DEV_ACCURACY_DEMO` fallback in dev builds | `AccuracyCenter.jsx` |
| Admin Leagues/Predictions tabs placeholder | `AdminPanel.jsx`, `SuperAdminPanel.jsx` |

### Unused API client functions

`fetchAccuracySummary`, `fetchPredictionHistoryPage`, `fetchPredictionHistoryResults`, `fetchAdminLearningOptimization`, `fetchAdminAccuracyAudit`, `fetchHealth`

---

## 6. API Audit

**~95 route handlers** across 12 routers (`worldcup_predictor/api/main.py`).

### Active core routes

- Auth, user settings, favorites, alerts, notifications, dashboard  
- `/api/predict/{fixture_id}`, `/api/matches/upcoming`  
- `/api/history`, `/api/performance/summary`, `/api/best-tips`  
- Billing: readiness, checkout session, portal, webhook (Stripe live)  
- Admin + gate + accuracy + learning  

### Deprecated / legacy / duplicate

| Route | Status |
|-------|--------|
| `/api/billing/checkout`, `/api/subscription/checkout`, `/api/stripe/create-checkout-session` | Placeholder compat |
| `/api/predictions/{id}` | Intentional 404 typo trap |
| `/api/auth/resend-verification` | Duplicate of `-email` variant |
| `/api/user/prediction-history*` | Superseded by `/api/history` for UI |
| `/api/accuracy/summary` | Active but **UI uses performance instead** |

### Backend-only (no frontend client)

`/api/version`, `/api/health/providers`, `/api/admin/accuracy/quarantined`, `/api/admin/accuracy/summary`, `/api/admin/email/diagnostics`

### OpenAPI / docs exposure

FastAPI default **`/docs` and `/redoc` likely enabled** (no `docs_url=None` in `main.py`) — verify nginx blocks in production.

---

## 7. Database Audit

### PostgreSQL (SaaS) — 11 tables

`users`, `user_settings`, `user_favorites`, `user_alerts`, `user_notifications`, `subscriptions`, `user_prediction_history`, `billing_invoices`, `stripe_webhook_events`, `email_verification_tokens`, `password_reset_tokens`

**Classification:** All **active** for SaaS.

### SQLite intelligence (~40+ tables)

**Active:** `fixtures`, `fixture_results`, `worldcup_stored_predictions`, `worldcup_prediction_evaluations`, `worldcup_accuracy_summary`, enrichment caches, Sportmonks tables, learning reports.

**Legacy (same DB file):** `app_users`, `user_entitlements`, `user_usage_limits`, `remember_tokens`, `admin_session_lock` — Tkinter/GUI era.

**Overlapping storage (risk):**

| Domain | Overlap |
|--------|---------|
| User identity | PG `users` vs SQLite `app_users` |
| Subscriptions | PG `subscriptions` vs SQLite `user_entitlements` |
| Quota | 3 mechanisms: GUI limits, daily usage, billing-period usage |
| Predictions | `predictions` vs `worldcup_stored_predictions` |
| User history | PG per-user vs SQLite global archive |

---

## 8. Prediction Engine Audit

### Pipeline

`PredictPipeline` → `MatchIntelligenceBuilder` + `EnrichmentService` → `SpecialistOrchestrator` (22 agents) → `ScoringEngine` → **WDE** → post-fusion metadata.

### Provider consumption matrix (summary)

| Provider | Fetched | Consumed in WDE/scoring | Largely ignored |
|----------|---------|-------------------------|-----------------|
| **API-Football** | fixtures, stats, H2H, injuries, lineups, odds, events, standings | stats, H2H, injuries, lineups, odds | **events** (quality score only); deep predictions (trace only) |
| **Weather** | temp, rain, wind, alerts, etc. | impact score, rain_probability | feels_like, gust, visibility, alerts detail |
| **xG** | API-Football stats, Sportmonks xGFixture | XGChanceQuality → tactics factor; Sportmonks via **gated promotion** | Raw Sportmonks xG without promotion pass |
| **Odds** | API-Football, The Odds API, Sportmonks, Rapid | consensus → WDE odds factor | **OddsMovementAgent** not wired to WDE |
| **Sportmonks** | scores, participants, state, statistics, lineups, events, odds, predictions, xG | lineups/injuries gap-fill; gated prediction/xG promotion | **scores, events, state**; most flat statistics |

### WDE factors (9)

`data_quality`, `team_form`, `injuries_suspensions`, `lineup_strength`, `tactics_matchup`, `player_quality`, `odds_market_signal`, `motivation_psychology`, `weather_referee_context`

Promotion adapters (24A–C): expected lineup, tournament context, xG, Sportmonks prediction — **shadow/gated**, not always live.

---

## 9. Scalability Audit

### Architecture constraints

- **Single-process FastAPI** + **SQLite** for intelligence (write contention)  
- **PostgreSQL** for SaaS (connection pool default)  
- **In-memory rate limits** (lost on restart; not shared across workers)  
- **Sequential API refresh** in evaluation timer  
- **Full payload JSON** in SQLite rows (large blobs)  
- **No CDN** mentioned for frontend (static nginx)

### Load estimates

| Users | Predict/day (est.) | Risk areas |
|-------|-------------------|------------|
| **100** | 200–500 | Low — current architecture sufficient |
| **1,000** | 2,000–5,000 | **SQLite write lock** on predict cache + stored predictions; PG pool; API-Football quota |
| **10,000** | 20,000–50,000 | **Critical** — SQLite must shard or move archive to PG; multi-worker rate limits broken; predict pipeline CPU; sequential eval refresh |

### Expensive operations

| Operation | Cost driver |
|-----------|-------------|
| `POST /api/predict/{id}` | Full specialist orchestrator + enrichment API calls |
| `build_match_center` | Full fixture list + live enrichment |
| `result_refresh` | N × `get_fixture_by_id` per timer run |
| Admin learning dashboard | Full scan of evaluations + payload parse |
| Shadow replay JSONL | 28k lines local — not prod |

### Memory risks

- Large `payload_json` loaded per request  
- In-memory resolver caches per job  
- Recharts + large admin tables in browser  

---

## 10. Security Audit

### Stripe live mode

**Production verified (read-only audit):** `stripe_mode: live`, `checkout_enabled: true`, `stripe_production_ready: true`

### JWT

- `worldcup_predictor/auth/jwt_tokens.py`  
- Bearer on protected routes; `token_version` invalidation on logout/kick/ban  
- Production guard: min 32-char secret (`production_guard.py`)

### Admin / super-admin

- Role check + **gate tokens** (`X-Admin-Gate-Token`, `X-Super-Admin-Gate-Token`)  
- Brute-force lockout: 5 failures → 300s (in-memory)  
- Super-admin: role changes, ban/kick, commercial analytics

### Public endpoints

`/api/health`, `/api/performance/summary`, `/api/best-tips`, `/api/matches/upcoming`, `/api/accuracy/summary`, auth login/register

### Rate limiting (in-memory, per-process)

| Area | Limit |
|------|-------|
| Login | 5 failures → 15 min lockout |
| Register | 5/IP/hour |
| Checkout | checkout_rate_limit |
| Contact admin | 3/hour |
| Admin gate | 5 failures → 300s |

**Gap:** No global API middleware rate limiter (SlowAPI).

### Docs exposure

FastAPI **`/docs` / `/redoc` default enabled** — confirm nginx deny rules.

### Other

- Webhook: Stripe signature verification (no JWT)  
- Legacy billing placeholders: no Stripe session (safe)  
- `VITE_DEV_AUTH_BYPASS` — dev only; must not ship in prod build  
- CORS: production uses `CORS_ALLOWED_ORIGINS` env only  

---

## Final sections

See **`PHASE_45C_PRIORITY_MATRIX.md`** for:

- TOP 25 ISSUES  
- TOP 25 QUICK WINS  
- TOP 10 REVENUE IMPROVEMENTS  

---

**Audit completed.** No code, database, or deployment changes were made.
