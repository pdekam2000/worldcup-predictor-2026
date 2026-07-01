# EURO-C4 — OddAlerts UEFA Odds Truth Audit + Import Report

**Phase:** EURO-C4 (owner/internal only)  
**Generated:** 2026-06-30  
**Scope:** 121 `owner_euro_b` UEFA fixtures (Champions League, Europa League, Conference League)  
**ECSE generation:** None  
**Public changes:** None  

---

## Executive summary

EURO-C4 implemented the full OddAlerts audit pipeline (config audit, crosswalk, odds scan, import, ECSE readiness, validation). OddAlerts API calls were **attempted and logged** (4 calls, cap respected). However, the configured OddAlerts token returns **`Incorrect Permissions`** on all probed endpoints, so **no fixtures could be discovered, no odds could be scanned, and nothing could be imported**.

**Final recommendation:** `ODDALERTS_CONFIG_MISSING`  
*(Token env var is set, but API access is denied — upgrade/fix OddAlerts subscription or token scope before re-running.)*

---

## Why EURO-C3 had OddAlerts calls = 0

| # | Reason |
|---|--------|
| 1 | `OddAlertsClient.is_configured` gate — EURO-C3 did not load `.env` in all paths; when token absent, OddAlerts branch was skipped entirely |
| 2 | **No OddAlerts crosswalk** — EURO-C3 passed API-Football `fixture_id` to `fetch_oddalerts_odds_history()`, which requires an **OddAlerts fixture ID** |
| 3 | EURO-C3 summary confirms `provider_calls.oddalerts = 0` |

EURO-C4 addresses items 2–3 with a dedicated crosswalk and direct endpoint audit. Item 1 is addressed via `load_dotenv()` in pipeline scripts. The remaining blocker is **API permission denial**, not missing integration code.

---

## Part A — OddAlerts config and endpoint audit

**Artifact:** `artifacts/euro_c4_oddalerts_config_audit.json`

| Check | Status |
|-------|--------|
| Token/env configured | **Yes** (`ODDALERTS_API_KEY` present) |
| Base URL configured | **Yes** (`https://data.oddalerts.com/api`) |
| Client implemented | **Yes** (`worldcup_predictor/providers/oddalerts_provider.py`) |
| Fixture search endpoint | **Yes** (`fixtures/upcoming`, `value/upcoming`, `competitions`) |
| Odds endpoint | **Yes** (`odds/history`, `odds/latest`) |
| Value-bets endpoint | **Yes** (`value/upcoming`, `trends/*`) |
| Supported market names/IDs known | **Partial** — CL=51, EL=32 in `ODDALERTS_LEAGUE_MAP`; Conference League ID not in map (runtime search attempted) |
| API permissions | **Denied** — all connectivity probes return `info: Incorrect Permissions` |

**Endpoints probed (live):**

- `competitions` → Incorrect Permissions  
- `value/upcoming` → Incorrect Permissions  
- `fixtures/upcoming` → Incorrect Permissions  
- `odds/latest` → Incorrect Permissions  

---

## Part B — OddAlerts fixture crosswalk

**Script:** `scripts/build_uefa_oddalerts_crosswalk.py`  
**Artifact:** `artifacts/euro_c4_oddalerts_crosswalk.json`

| Metric | Count |
|--------|------:|
| API-Football UEFA fixtures targeted | 121 |
| OddAlerts pool discovered | 0 |
| Crosswalk **accepted** (confidence ≥ 0.90) | 0 |
| Crosswalk **rejected** | 121 |
| Ambiguous matches | 0 |

**Rejection reason:** `no_match` for all 121 — discovery pool empty due to permission denial, not fuzzy-match failure.

Matching logic implemented: competition key, kickoff ±3h, normalized/fuzzy team names, ambiguous rejection, confidence ≥ 0.90.

---

## Part C — Direct OddAlerts odds scan

**Script:** `scripts/scan_oddalerts_uefa_odds.py`  
**Artifact:** `artifacts/euro_c4_oddalerts_odds_availability.json`

| Metric | Value |
|--------|------:|
| Fixtures scanned | 0 |
| Provider calls | 0 (scan skipped — no accepted crosswalk) |
| Parser gaps | 0 |
| Provider empty | 0 |

Markets detection logic is implemented for: 1X2, O/U 2.5, BTTS, O/U 1.5, O/U 3.5, Double Chance, Correct Score — **not exercised** due to zero crosswalk matches.

---

## Part D — OddAlerts odds import

**Script:** `scripts/import_oddalerts_uefa_odds.py`  
**Pipeline:** `scripts/run_euro_c4_oddalerts_pipeline.py`

| Metric | Value |
|--------|------:|
| Fixtures scanned | 121 |
| Odds imported | 0 |
| Skipped (mapping_missing) | 121 |
| Provider calls (import phase) | 0 |

Import path is cache-first, accepts only high-confidence crosswalk rows, normalizes to existing odds snapshot schema, preserves raw payload refs — **not triggered** without crosswalk.

---

## Part E — ECSE readiness after OddAlerts

**Artifact:** `artifacts/euro_c4_ecse_readiness_after_oddalerts.json`

| Status | Count |
|--------|------:|
| READY_FULL | 0 |
| READY_PARTIAL | 0 |
| ODDS_PARTIAL_1X2_ONLY | 5 |
| MAPPING_MISSING | 116 |
| PROVIDER_EMPTY | 0 |
| MARKET_PARSER_GAP | 0 |
| STORAGE_GAP | 0 |

**Comparison vs EURO-C3:**

| Provider | 1X2 | O/U 2.5 | BTTS | ECSE-ready |
|----------|----:|--------:|-----:|-----------:|
| API-Football | ~0 | 0 | 0 | 0 |
| Sportmonks | 5 | 0 | 0 | 0 |
| OddAlerts | 0 | 0 | 0 | 0 |

OddAlerts did not change readiness — existing Sportmonks 1X2-only partial (5 fixtures) unchanged.

---

## Part F — Parser/storage gap analysis

| Gap type | Count | Notes |
|----------|------:|-------|
| MARKET_PARSER_GAP | 0 | No raw odds received — cannot distinguish parser bug from provider empty |
| STORAGE_GAP | 0 | No import attempts |

**Critical:** Provider permission denial was **not** mislabeled as provider-empty or parser gap.

---

## Part G — Validation

**Script:** `scripts/validate_euro_c4_oddalerts_odds_integration.py`  
**Artifact:** `artifacts/euro_c4_oddalerts_validation.json`  
**Result:** **PASSED** (23/23 checks)

Verified:

- Config audit + artifacts present  
- OddAlerts calls attempted when token configured (4 calls logged)  
- API cap respected (≤ 100)  
- High-confidence crosswalk enforced; ambiguous rejected  
- No fake odds; no invalid probabilities  
- WDE predictions unchanged (121)  
- ECSE snapshots unchanged (0 UEFA)  
- ECSE baseline, EGIE, billing unchanged  
- Public output unchanged  

---

## Provider call log

**Log:** `logs/euro_c4_oddalerts_20260630_155803.jsonl`

| Provider | Calls |
|----------|------:|
| OddAlerts | 4 |

Actions: Conference League competition search (3) + `fixtures/upcoming` discovery probe (1, permission denied).

---

## Deliverables created

| Item | Path |
|------|------|
| Core module | `worldcup_predictor/owner/euro_c4_oddalerts.py` |
| Config audit CLI | `scripts/audit_euro_c4_oddalerts_config.py` |
| Crosswalk CLI | `scripts/build_uefa_oddalerts_crosswalk.py` |
| Odds scan CLI | `scripts/scan_oddalerts_uefa_odds.py` |
| Import CLI | `scripts/import_oddalerts_uefa_odds.py` |
| Full pipeline | `scripts/run_euro_c4_oddalerts_pipeline.py` |
| Validation | `scripts/validate_euro_c4_oddalerts_odds_integration.py` |

---

## Final recommendation

### `ODDALERTS_CONFIG_MISSING`

The OddAlerts integration code path is complete and validated, but the **API token lacks data permissions**. Until OddAlerts grants access (or a valid data-tier token is configured):

1. Re-run: `python scripts/run_euro_c4_oddalerts_pipeline.py --max-api-calls 100`  
2. Expect crosswalk matches > 0 if UEFA fixtures exist in OddAlerts  
3. Only then can O/U 2.5 and BTTS coverage be truth-tested vs API-Football/Sportmonks  

**Do not run ECSE** on UEFA fixtures until at least one provider supplies 1X2 + O/U 2.5 + BTTS with verified mappings.

---

## Next steps (owner action required)

1. **Fix OddAlerts subscription/token** — resolve `Incorrect Permissions` with OddAlerts support  
2. Re-run EURO-C4 pipeline after token fix  
3. If crosswalk accepts fixtures but markets remain 1X2-only → investigate `ODDALERTS_MARKETS_INSUFFICIENT`  
4. If raw odds present but normalized empty → investigate `ODDALERTS_PARSER_FIX_REQUIRED`  
5. Continue Sportmonks market fix (`NEED_SPORTMONKS_MARKET_FIX` from EURO-C3) in parallel  

**No ECSE generation was performed in this phase.**
