# Phase 28 — Sportmonks Production Coverage Audit

**Mode:** Audit only — no code changes, no deploy, no WDE/calibration/promotion changes  
**Project:** WorldCup Predictor 2026  
**Date:** 2026-06-20  
**Server:** Hetzner production (`/opt/worldcup-predictor`)  
**Goal:** Explain why `sportmonks_prediction_agent` and `xg_intelligence_agent` return `status=unavailable` despite Phase 22 agents executing

---

## Executive Summary

Both agents are **correctly executing** but **correctly reporting unavailable** because **production Sportmonks API calls for Phase 22C/22D includes are blocked by plan access (HTTP 403)**.

| Root cause | Evidence |
|------------|----------|
| **Plan lacks `odds` include** | `403 — You do not have access to the 'odds' include` (code 5002) |
| **Plan lacks `predictions` include** | `403 — You do not have access to the 'predictions' include` |
| **Plan lacks `xGFixture` include** | `403 — You do not have access to the 'xgfixture' include` |
| **Full enrichment fetch fails** | Unified path falls back to date-lookup payload (no odds/predictions/xG) |
| **SQLite enrichment cache empty** | `sportmonks_fixture_enrichment` has **0 rows** on production |

This is **not** an orchestrator bug, cache-schema bug, or agent registration failure. It is a **Sportmonks subscription / include entitlement gap**.

---

## 1. Coverage Audit — Next 50 World Cup Fixtures

**Fixtures scanned:** 40 (all non-placeholder upcoming WC 2026 fixtures available in schedule at audit time; fewer than 50 exist in the upcoming window).

### Coverage table

| Metric | Count | Coverage |
|--------|------:|----------|
| Fixtures scanned | 40 | 100% |
| SQLite `sportmonks_fixture_enrichment` row | 0 | **0.0%** |
| SQLite row with complete includes (`odds;predictions;metadata;xGFixture`) | 0 | **0.0%** |
| Sportmonks enrichment payload consumed | 0 | **0.0%** |
| Raw `odds` key present | 0 | **0.0%** |
| Raw `predictions` key present | 0 | **0.0%** |
| Raw `xGFixture` key present | 0 | **0.0%** |
| Statistics xG fallback present | 0 | **0.0%** |
| Parsed Sportmonks odds available | 0 | **0.0%** |
| Parsed Sportmonks predictions available | 0 | **0.0%** |
| Parsed Sportmonks xG available | 0 | **0.0%** |
| `sportmonks_prediction_agent` would be available | 0 | **0.0%** |
| `xg_intelligence_agent` would be available | 0 | **0.0%** |

### Interpretation

Across all 40 upcoming fixtures:

- No fixture has a persisted full Sportmonks enrichment payload.
- No fixture has odds, predictions, or xGFixture data in the consumed pipeline path.
- **100% of fixtures** would produce `unavailable` for both Phase 22C/22D agents given current production state.

Other Sportmonks layers **do work**:

- WC league connectivity (`GET /leagues/732`) → **200 OK**
- Date lookup → resolves Sportmonks fixture IDs (e.g. API-Football `1539007` → SM `19609176`)
- Lookup fallback payload includes: `participants`, `lineups`, `formations`, `sidelined`, `metadata` (partial)
- `tournament_context_agent` can use Sportmonks standings (separate path) — observed **available** in Phase 27 orchestrator audit

---

## 2. Plan Capability Audit

### Runtime configuration (production)

| Setting | Value |
|---------|-------|
| `sportmonks_configured` | **True** |
| Token present | Yes (length 60) |
| Base URL | `https://api.sportmonks.com/v3/football` |
| WC league access | **Yes** — `GET /leagues/732` → 200, "World Cup" |
| xG plan probe file | **Not found** (no successful full enrichment save yet) |

### Include access matrix (live probe, fixture SM `19609176`)

| Include set | HTTP | Result |
|-------------|------|--------|
| Base (`scores;participants;state;statistics;lineups`) | **200** | OK — no odds/predictions/xG |
| `metadata` only | **200** | OK — empty for agent purposes |
| `odds` only | **403** | **Blocked** — code 5002 |
| `predictions` only | **403** | **Blocked** — code 5002 |
| `xGFixture` only | **403** | **Blocked** — code 5002 |
| `odds;predictions;metadata` | **403** | **Blocked** (fails on `odds`) |
| Full Phase 22 bundle (incl. odds + predictions + xGFixture) | **403** | **Blocked** |
| Bundle without odds but with predictions + xGFixture | **403** | **Blocked** (fails on `predictions`) |

**Sportmonks error (representative):**

```json
{
  "message": "You do not have access to the 'odds' include",
  "code": 5002,
  "link": "https://docs.sportmonks.com/football/api/response-codes/other-exceptions"
}
```

### Inferred plan level

| Capability | Production access |
|------------|-------------------|
| World Cup league metadata (732) | **Yes** |
| Fixture lookup by date/teams | **Yes** |
| Base fixture includes (lineups, participants, statistics, sidelined) | **Yes** |
| **`odds` include** | **No** |
| **`predictions` include** | **No** |
| **`xGFixture` include (xG add-on)** | **No** |
| Subscription introspection API | Not available (`/my/enrichment` → 404) |

**Conclusion:** Production token is on a plan tier that supports **core World Cup fixture data** but **not** the premium includes required by Phase 22C (`odds`, `predictions`) and Phase 22D (`xGFixture`).

---

## 3. API Response Audit — Sample Fixtures

### Netherlands vs Sweden (API-Football `1539007`, Sportmonks `19609176`)

| Check | Result |
|-------|--------|
| SQLite cache row | **None** |
| Live `GET /fixtures/19609176` with full includes | **403** (odds blocked) |
| Lookup fallback used in pipeline | **Yes** — `['lookup_cache', 'enrichment_failed_lookup_fallback']` |
| Lookup payload fields | `participants`, `lineups`, `formations`, `sidelined`, `details`, `metadata` flags — **no `odds`, `predictions`, `xGFixture`** |
| `supplemental_raw_odds_present` | **False** |
| `supplemental_raw_predictions_present` | **False** |
| `supplemental_xg_available` | **False** |
| `sportmonks_prediction_agent` | **unavailable** |
| `xg_intelligence_agent` | **unavailable** |

### Germany vs Ivory Coast (API-Football `1489393`)

| Check | Result |
|-------|--------|
| SQLite cache row | **None** |
| Consumed SM payload with odds/predictions/xG | **None** |
| Both agents | **unavailable** |

### Spain vs Saudi Arabia (API-Football `1489397`)

| Check | Result |
|-------|--------|
| SQLite cache row | **None** |
| Consumed SM payload with odds/predictions/xG | **None** |
| Both agents | **unavailable** |

### Missing / empty includes pattern (all samples)

| Include | In lookup fallback | In full API (current plan) |
|---------|-------------------|----------------------------|
| `odds` | **Missing** | **403 — not entitled** |
| `predictions` | **Missing** | **403 — not entitled** |
| `metadata` | Partial flags only | 200 but no prediction content |
| `xGFixture` | **Missing** | **403 — not entitled** |
| `statistics` | Not in lookup payload | 200 in base bundle; **no xG values pre-match** |

---

## 4. Cache Audit — `sportmonks_fixture_enrichment`

**Database:** `/opt/worldcup-predictor/data/football_intelligence.db`

| Metric | Value |
|--------|------:|
| Total rows | **0** |
| Rows with complete includes | **0** |
| Rows with incomplete includes | **0** |
| Expired rows | **0** |
| Rows containing `odds` key | **0** |
| Rows containing `predictions` key | **0** |
| Rows containing `xGFixture` key | **0** |

### Why cache is empty

`fetch_worldcup_fixture_enrichment()` only persists to SQLite on **successful** full API responses. Because every full-include request returns **403**, **nothing is ever saved**. The unified path then uses lookup fallback, which is **not written** to `sportmonks_fixture_enrichment`.

### Cache limitation impact

Even if code were fixed to split includes, the current cache provides **zero** fallback for odds/predictions/xG. Agents depend entirely on live enrichment or lookup metadata — both paths lack Phase 22C/22D data today.

---

## 5. Agent Availability Audit

### Data flow (production)

```
DataCollectorAgent
  └─ EnrichmentService._maybe_enrich_sportmonks()
       └─ unified fixture path
            ├─ GET /fixtures/{id}?include=…;odds;predictions;metadata;xGFixture
            │     └─ 403 PLAN BLOCK → enrichment FAILED
            └─ lookup_world_cup_fixture() fallback
                  └─ minimal payload (no odds/predictions/xGFixture)
       └─ apply_sportmonks_consumption()
            └─ supplemental.sportmonks_odds_prediction  → odds/predictions unavailable
            └─ supplemental.sportmonks_xg_intelligence    → xg unavailable

SpecialistOrchestrator
  ├─ SportmonksPredictionAgent  → reads supplemental → status=unavailable
  └─ XGIntelligenceAgent          → reads supplemental → status=unavailable
```

### `sportmonks_prediction_agent` — why `unavailable`

**Code gate** (`sportmonks_prediction_agent.py`):

```python
has_data = result.sportmonks_odds_available or result.sportmonks_prediction_available
status = "unavailable" if not has_data else "available"
```

**Production state for all audited fixtures:**

| Prerequisite | Status |
|--------------|--------|
| `supplemental_sources.sportmonks_odds_prediction` populated | Yes (consumption runs) |
| `raw_odds_present` | **False** — no `odds` key in payload |
| `raw_predictions_present` | **False** — no `predictions` key in payload |
| `odds.available` (parsed) | **False** |
| `predictions.available` (parsed) | **False** |
| `sportmonks_odds_available` | **False** |
| `sportmonks_prediction_available` | **False** |

**Precise cause:** Sportmonks API returns **403** for `odds` and `predictions` includes on the production subscription. Enrichment never retrieves these fields; lookup fallback does not contain them. Agent correctly reports unavailable.

### `xg_intelligence_agent` — why `unavailable`

**Code gate** (`xg_intelligence_agent.py`):

```python
status = "unavailable" if not xg_block or not xg_block.get("available") else "available"
```

**Production state:**

| Prerequisite | Status |
|--------------|--------|
| `supplemental_sources.sportmonks_xg_intelligence` populated | Yes |
| `xg_block.available` | **False** |
| `xGFixture` in raw payload | **Absent** (403 on include) |
| Statistics xG fallback | **Absent** on upcoming fixtures |
| `plan_support` | **`none`** |

**Precise cause:** Sportmonks API returns **403** for `xGFixture` include. No xGFixture data → `parse_sportmonks_xg_from_fixture()` sets `available=False` → agent unavailable.

### Important distinction

| Agent | Executes? | Has data? | Status |
|-------|-----------|-----------|--------|
| `sportmonks_prediction_agent` | **Yes** | **No** | unavailable |
| `xg_intelligence_agent` | **Yes** | **No** | unavailable |
| `tournament_context_agent` | Yes | Yes (standings) | available |
| `expected_lineup_agent` | Yes | Yes (API-Football + SM lineups) | available |

Agents are **deployed and running**; they are **data-starved** by plan entitlements, not missing from orchestrator.

---

## 6. Opportunity Score

Estimates assume agents remain **shadow/trace-only** (no WDE weight changes), consistent with Phase 23–27 policy.

### Sportmonks Prediction Agent (`sportmonks_prediction_agent`)

| Scenario | Expected value |
|----------|----------------|
| **Current plan (no odds/predictions includes)** | **Low** — agent always unavailable; zero benchmark signal |
| **If `predictions` include added** | **Medium** — external 1X2 benchmark vs internal consensus; useful for conflict audit and shadow promotion metrics; duplicates some API-Football odds signal |
| **If both `odds` + `predictions` added** | **Medium** — richer disagreement detection; marginal lift over existing `market_consensus_agent` / API-Football odds stack |

**Rationale:** Internal pipeline already has strong odds coverage via API-Football (14 bookmakers observed on NL vs SE). Sportmonks prediction benchmark is most valuable as an **independent cross-check**, not a primary signal.

### xG Intelligence Agent (`xg_intelligence_agent`)

| Scenario | Expected value |
|----------|----------------|
| **Current plan (no xGFixture)** | **Low** — agent always unavailable |
| **If `xGFixture` add-on activated** | **Medium–High** — independent xG vs internal/xG-v2 comparison; supports calibration shadow, O/U tendency validation, Phase 24C promotion telemetry |
| **Statistics-only xG (in-match/post-match)** | **Low–Medium** — limited for **upcoming** fixtures; useful only after kickoff |

**Rationale:** xG benchmark fills a gap not fully covered by API-Football alone; higher marginal value than odds/predictions duplicate — but only if xG add-on is purchased and populated pre-match.

---

## 7. Recommendations

### P0 — Plan / entitlement (business decision)

Upgrade Sportmonks subscription to include:

1. **`odds`** include (Phase 22C)
2. **`predictions`** include (Phase 22C)
3. **`xGFixture`** include / xG add-on (Phase 22D)

Until these are on the token, **both agents will remain unavailable on 100% of fixtures** regardless of code deploys.

### P1 — Engineering (after plan upgrade — requires separate approval)

Not implemented in this audit:

- Split include requests so a single 403 on `odds` does not block persisting base + xG payloads
- Backfill `sportmonks_fixture_enrichment` for upcoming WC fixtures once includes succeed
- Save xG plan probe on first successful enrichment

### P2 — Monitoring

- Log Sportmonks **403 code 5002** distinctly from empty-data responses
- Track `enrichment_failed_lookup_fallback` rate in `sportmonks_unified` metadata
- Alert when `sportmonks_fixture_enrichment` row count stays at 0 after plan change

### Do not pursue (low ROI under current plan)

- WDE weight changes to compensate for missing SM agents
- Gated promotion enablement for 24C Sportmonks/xG — no signal to promote
- Repeated live API probing beyond audit (quota conservation)

---

## Audit Commands Used (production, read-only)

```bash
# Environment + connectivity
python scripts/audit_sportmonks_production_env.py

# Coverage + cache + pipeline (temporary /tmp audit script)
python /tmp/phase28_audit.py

# Include-level plan probe
python /tmp/phase28_inc.py

# Deep API 403 confirmation
python /tmp/phase28_probe.py
```

**Audit timestamp (UTC):** 2026-06-20T10:56–10:57

---

## Final Verdict

| Question | Answer |
|----------|--------|
| Are Phase 22 agents deployed? | **Yes** |
| Do they execute? | **Yes** |
| Why unavailable? | **Sportmonks plan blocks `odds`, `predictions`, and `xGFixture` includes (HTTP 403)** |
| Is SQLite cache helping? | **No — 0 rows; full fetch never succeeds** |
| Is lookup fallback sufficient? | **No — lacks Phase 22C/22D fields** |
| Fix without plan change? | **No meaningful fix** — agents need entitled includes |

---

*End of Phase 28 audit. No code changes implemented. Awaiting approval before any fixes.*
