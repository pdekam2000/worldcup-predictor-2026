# Phase 45C — Priority Matrix

**Companion to:** `PHASE_45C_FULL_SYSTEM_DEEP_AUDIT.md`  
**Mode:** READ ONLY — audit conclusions only, no implementation  

Priority legend: **P0** = trust/revenue blocker · **P1** = high impact · **P2** = medium · **P3** = polish

---

## TOP 25 ISSUES

| # | Priority | Issue | Area | Impact |
|---|----------|-------|------|--------|
| 1 | **P0** | Landing page shows **hardcoded fake stats** (24k predictions, 73% accuracy, fake testimonials) | Frontend | Legal/trust risk; contradicts honest empty accuracy |
| 2 | **P0** | **39 cache files vs 12 stored** predictions — historical payloads not in global archive | Data | Lost recoverable prediction history |
| 3 | **P0** | **~40+ fixture artifacts** across legacy JSONL/SQLite never migrated to archive | Data | User expectation gap ("where are my predictions?") |
| 4 | **P1** | **30-minute eval timer** — up to 30 min latency after FT | Live results | Poor UX for result updates |
| 5 | **P1** | **Three accuracy systems** (SQLite evals, JSONL tracker, verification) with different fallbacks | Accuracy | Confusing metrics if re-enabled incorrectly |
| 6 | **P1** | **`/api/accuracy/summary` vs `/api/performance/summary`** — duplicate public accuracy paths | API | Divergent numbers possible |
| 7 | **P1** | **`ApiSettingsPage` fully stubbed** but linked in admin nav | Frontend/Admin | Operators think they control API keys |
| 8 | **P1** | **`ContactPage` fakes success** — no backend delivery | Frontend | Support leads lost |
| 9 | **P1** | **Favorites: no add UI** despite nav + empty state promise | Frontend | Broken feature surface |
| 10 | **P1** | **SQLite as intelligence DB** — write contention at scale | Scalability | Blocks 1k+ concurrent users |
| 11 | **P1** | **In-memory rate limits** — not shared across workers/restarts | Security | Brute-force window after deploy |
| 12 | **P1** | **HT, Correct Score, First Goal, Goalscorer** in payloads but **not evaluated** in WC pipeline | Coverage | Incomplete performance story |
| 13 | **P2** | **PG `user_prediction_history.result`** may stay pending while SQLite eval exists | Accuracy | User history inconsistency |
| 14 | **P2** | **Sequential API refresh** (1 call/fixture) in timer | Live results | Quota + latency under many stored preds |
| 15 | **P2** | **Pricing page** says "no payment" while Stripe live active | Frontend/Billing | Conversion confusion |
| 16 | **P2** | **OddsMovementAgent** fetched/run but **not wired to WDE** | Engine | Unused intelligence spend |
| 17 | **P2** | **Sportmonks scores/events/state** largely ignored | Engine | Premium API underutilized |
| 18 | **P2** | **FastAPI `/docs` likely exposed** if nginx not blocking | Security | API surface enumeration |
| 19 | **P2** | **Legacy GUI tables** (`app_users`, entitlements) coexist with PG SaaS | Database | Confusion, stale data risk |
| 20 | **P2** | **Triple quota tracking** (GUI, daily, billing-period) | Database | Inconsistent limit enforcement |
| 21 | **P2** | **Learning dashboard** historically inflated agent winrates (n=2); guard added but data still thin | Accuracy | Misleading admin insights until n≥20 |
| 22 | **P2** | **Premium history detail** sections are static "coming soon" | Frontend | Premium value not visible |
| 23 | **P2** | **2FA toggle** saves preference but does nothing | Security/UX | False security signal |
| 24 | **P3** | **Unused API client functions** (6+ in saasApi.js) | Frontend | Maintenance dead weight |
| 25 | **P3** | **Inventory script wrong JSONL path** | Tooling | Wrong counts in automated reports |

---

## TOP 25 QUICK WINS

*Low effort, high clarity — ordered by impact/effort ratio*

| # | Quick win | Effort | Benefit |
|---|-----------|--------|---------|
| 1 | Replace landing **hardcoded stats** with real API counts or honest "early access" copy | S | Immediate trust fix |
| 2 | **Hide or banner** `ApiSettingsPage` until backend exists | S | Stop admin confusion |
| 3 | Wire **ContactPage** to existing `contactAdmin` pattern or mailto | S | Real support intake |
| 4 | Add **"Add to favorites"** button on Match Center cards | S | Complete favorites flow |
| 5 | **Unify public accuracy** — deprecate `/api/accuracy/summary` or make Performance Center sole source | S | Single metric truth |
| 6 | **Diff cache vs stored** fixture IDs; report recoverable count in admin audit | S | Visibility before migration |
| 7 | Block **`/docs` and `/redoc`** in nginx production config | S | Reduce attack surface |
| 8 | Fix **notification bell** to use unread count from API | S | UI polish |
| 9 | Link **`/pricing`** in nav or remove orphan route | S | Navigation consistency |
| 10 | Update **PricingContent** copy when `checkout_enabled=true` | S | Align with Stripe live |
| 11 | Remove or disable **2FA toggle** until implemented | S | Honest settings |
| 12 | Add admin link to **`/admin/accuracy/quarantined`** diagnostics | S | Ops visibility |
| 13 | Document **30-min refresh** on Dashboard history table too | S | User expectation setting |
| 14 | Fix **phase45b inventory script** JSONL path | S | Accurate tooling |
| 15 | Delete unused **saasApi.js exports** or wire them | S | Code hygiene |
| 16 | **`translate="no"`** on remaining chart panels (Admin Learning) | S | Translation artifact prevention |
| 17 | Show **"Insufficient data (n=X)"** on Performance Center market rows when n<5 | S | Honest micro-metrics |
| 18 | Admin **Predictions Today** card — hide until tracking exists | S | Remove "coming soon" noise |
| 19 | Expose **`GET /api/health/providers`** on admin health panel | S | Ops monitoring |
| 20 | Run **quarantine pass** on schedule (already in auto-eval — verify timer enabled) | S | Already done post-45B |
| 21 | Add **dry-run cache import** CLI report (read-only list of recoverable fixtures) | M | Safe recovery prep |
| 22 | Consolidate **admin accuracy rebuild** button label: "Refresh Results & Evaluate" | S | Operator clarity |
| 23 | **Mark legacy `/api/user/prediction-history`** deprecated in OpenAPI description | S | API clarity |
| 24 | Super-admin **email diagnostics** — add minimal admin page or remove endpoint | S | Close backend-only gap |
| 25 | **Best Tips** empty state when 0 evals — already implicit; add explicit copy | S | UX clarity |

*Effort: S = hours, M = 1–2 days*

---

## TOP 10 REVENUE IMPROVEMENTS

| # | Improvement | Rationale | Depends on |
|---|-------------|-----------|------------|
| 1 | **Fix landing → register → predict funnel** — remove fake 73% accuracy; show real platform state + WC countdown | Trust drives conversion more than fake social proof | Quick win #1 |
| 2 | **Stripe checkout from `/pricing` and landing CTAs** — not register-only | Stripe live but public pricing doesn't use it | Pricing copy + CTA wiring |
| 3 | **Recover cache predictions into archive** — more history = more retention | 39 cache vs 12 stored; users see richer history | Safe import pipeline |
| 4 | **Premium history detail** — ship specialist votes, odds snapshot (data already in payload) | Paywall differentiation vs "coming soon" | Read payload fields only |
| 5 | **Faster result updates** (5–10 min post-FT window) | Users who see wins return and upgrade | Timer/refresh tuning |
| 6 | **Honest Performance Center with growing sample** — market reliability badges | Builds credibility for Pro tier "analytics" | Real WC matches finishing |
| 7 | **Quota upgrade prompts** at predict time with live checkout | Already partially wired; optimize copy + readiness | Billing UX polish |
| 8 | **Customer portal prominence** on Subscription page when `portal_enabled` | Reduces churn, enables upsell | Already backend-ready |
| 9 | **Email verification + onboarding** to first prediction | Verified users convert higher | Auth flow (existing) |
| 10 | **Best Tips** as Pro feature once n≥20 evals per market | Monetize curated picks with real track record | Accumulated evaluations |

---

## Suggested phase sequencing (informational)

| Phase | Focus | Issues addressed |
|-------|-------|------------------|
| **45D** | Trust & marketing honesty | #1, #15, #9, #10 |
| **45E** | Cache → archive recovery (read-only audit first, then import) | #2, #3, #6 |
| **45F** | Live results latency | #4, #14 |
| **46A** | Accuracy unification | #5, #6, #13 |
| **46B** | Frontend dead features | #7, #8, #9, #22 |
| **47** | Scalability (PG archive or SQLite WAL + workers) | #10, #11 |

---

## Risk matrix (summary)

| Risk | Likelihood | Severity | Mitigation status |
|------|------------|----------|-------------------|
| Fake marketing stats discovered by users | High | Critical | **Open** |
| Metric distrust if JSONL fallback re-enabled | Medium | High | Partial (45B quarantine) |
| SQLite lock under load | Low now / High at 1k users | High | **Open** |
| API quota exhaustion from refresh | Medium during WC | Medium | Partial (stored-first scope) |
| Admin stub pages cause misconfiguration | Medium | Medium | **Open** |

---

**End of priority matrix.** No fixes applied in this phase.
