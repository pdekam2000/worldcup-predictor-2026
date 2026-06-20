# Phase 28B — Sportmonks Include Split + 403 Safe Cache

**Status:** Implementation complete — validation passed locally. **Not deployed** (awaiting approval).

## Problem

Phase 28 audit showed production Sportmonks token allows World Cup base fixture data but returns **HTTP 403 (code 5002)** for premium includes (`odds`, `predictions`, `xGFixture`). The previous single combined request failed entirely, triggering lookup-only fallback and leaving `sportmonks_fixture_enrichment` empty — blocking all base enrichment (lineups, statistics, sidelined, etc.).

## Solution

Split Sportmonks fixture includes into **base** and **premium** groups. Fetch and cache base first; attempt premium separately. Premium 403 is recorded but does **not** fail base enrichment or trigger lookup fallback.

---

## Files Changed

| File | Change |
|------|--------|
| `worldcup_predictor/providers/sportmonks_enrichment.py` | Base/premium include constants; split fetch; merge; cache flags; `_cache_base_includes_complete`; premium access helpers |
| `worldcup_predictor/database/migrations.py` | Non-destructive `PHASE42B_SPORTMONKS_COLUMNS` (7 INTEGER flags on `sportmonks_fixture_enrichment`) |
| `worldcup_predictor/database/repository.py` | `save_sportmonks_fixture_enrichment()` extended with premium/base flag columns |
| `worldcup_predictor/providers/sportmonks_consumption.py` | `_premium_access_for_report()`; premium flags in supplemental block; base-complete cache resolution |
| `worldcup_predictor/providers/sportmonks_client.py` | Trace includes `premium_access` |
| `worldcup_predictor/providers/enrichment_service.py` | Stores `sportmonks_premium_access` in provider metadata |
| `worldcup_predictor/agents/specialists/status_reasons.py` | `sportmonks_plan_no_predictions_access`, `sportmonks_plan_no_xg_access` |
| `worldcup_predictor/agents/specialists/sportmonks_prediction_agent.py` | Sets `status_reason` when plan blocks odds/predictions |
| `worldcup_predictor/agents/specialists/xg_intelligence_agent.py` | Sets `status_reason` when plan blocks xG |
| `scripts/validate_phase28b_sportmonks_include_split.py` | Local validation (mocked provider) |

**Out of scope (unchanged):** WDE, calibration, promotion adapters, deployment.

---

## Request Strategy

```
1. Cache hit (base_enrichment_available OR base includes in include_params)?
   → Return cached payload + premium_access flags (0 API calls)

2. GET /fixtures/{id}?include=<BASE_INCLUDES>
   → On success: validate WC league 732, proceed
   → On failure: return error (may fall back to lookup only here)

3. GET /fixtures/{id}?include=odds;predictions;xGFixture
   → On 200: merge premium fields into base payload
   → On 403: set premium_*_access_denied flags; keep base payload
   → On other error: log warning; keep base payload

4. UPSERT sportmonks_fixture_enrichment with raw JSON + flags
```

### Include Groups

**Base:** `scores`, `participants`, `state`, `statistics`, `lineups`, `events`, `formations`, `sidelined.sideline`, `metadata`

**Premium:** `odds`, `predictions`, `xGFixture`

---

## Cache Impact

New SQLite columns (safe `ALTER TABLE` via `_add_column_if_missing`):

- `base_enrichment_available`
- `premium_odds_available`
- `premium_predictions_available`
- `premium_xg_available`
- `premium_odds_access_denied`
- `premium_predictions_access_denied`
- `premium_xg_access_denied`

Cache completeness now keyed on **base** includes only (`_cache_base_includes_complete`). Rows with base data + premium 403 are valid cache hits.

Provider metadata gains `sportmonks_premium_access` (from unified trace). Supplemental `sportmonks` block carries `premium_access` for agents.

---

## Quota Impact

| Scenario | Before (28) | After (28B) |
|----------|-------------|-------------|
| Cold fetch, premium blocked | 1 combined call → **403, no cache** | 2 calls (base 200 + premium 403) → **base cached** |
| Warm cache (base complete) | N/A (empty cache) | **0 calls** |
| Repeat requests | Lookup fallback each time | Cache hit |

Net: slightly more calls on **first** touch per fixture (+1 premium attempt), but eliminates repeated failed combined requests and empty-cache loops. Premium 403 flags prevent unnecessary premium retries on cache hits.

---

## Agent Behavior

When premium blocked and no odds/predictions/xG in payload:

| Agent | `status_reason` |
|-------|-----------------|
| `sportmonks_prediction_agent` | `sportmonks_plan_no_predictions_access` |
| `xg_intelligence_agent` | `sportmonks_plan_no_xg_access` |

Agents remain `unavailable` for premium data (correct — plan limitation), but base Sportmonks enrichment (injuries, lineups, statistics) can now flow through consumption.

---

## Validation Result

```text
python scripts/validate_phase28b_sportmonks_include_split.py
→ All 22 Phase 28B checks passed
```

Validated:

- Base payload caches when premium returns 403
- Premium 403 does not trigger lookup-only fallback
- SQLite `base_enrichment_available=1` persisted
- Cache hit uses 0 API calls
- Agents emit correct `status_reason` values
- Unified path succeeds with participants in fixture payload

---

## Remaining Business Limitation

Production Sportmonks plan still **does not include** `odds`, `predictions`, or `xGFixture`. Phase 28B fixes the **infrastructure** failure mode; it does not grant premium data access.

To enable `sportmonks_prediction_agent` and `xg_intelligence_agent` with live data:

1. Upgrade Sportmonks subscription to include odds, predictions, and xG add-on for World Cup 732
2. Redeploy this change
3. Allow cache refresh (or `force_refresh`) — premium fetch will succeed and flags will flip to `premium_*_available=1`

Until then, agents correctly report plan-blocked status while base WC enrichment (lineups, sidelined, statistics, formations) is available.

---

## Deploy Gate

**STOP — do not deploy until approved.**

Recommended post-approval steps:

1. Deploy code to production
2. Run Alembic/SQLite schema compat on server (automatic on first DB connection)
3. Trigger one WC fixture predict/enrich to warm base cache
4. Confirm `sportmonks_fixture_enrichment` row count > 0 and agents show plan-blocked reasons (not generic missing-data)
