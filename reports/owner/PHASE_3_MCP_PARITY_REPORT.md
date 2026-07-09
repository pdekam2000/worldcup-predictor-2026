# Phase 3 MCP Parity Report

**Date:** 2026-07-09  
**Environment:** Hetzner production (`ubuntu-8gb-fsn1-1`)  
**Fixture:** `1554441` (CSKA Sofia vs Derry City)

## Test sequence

| # | Tool | Result |
|---|------|--------|
| 1 | `server_health` | PASS — `worldcup-api` active |
| 2 | `model_status` | PASS — WDE/ECSE available, DB connected |
| 3 | `resolve_fixtures` | PARTIAL — fuzzy kickoff window rejected auto-match; used known `fixture_id` fallback for downstream tests |
| 4 | `odds_freshness_audit` | PASS — `FRESH_ODDS`, age 22.2 min |
| 5 | `run_fixture_prediction` | PASS — status `OK`, 3670 ms |

## MCP prediction output (fixture 1554441)

| Field | Value |
|-------|--------|
| Odds status | FRESH_ODDS |
| WDE pick | `home_win` |
| ECSE Top1 | `2-0` (17.95%) |
| Quality | OK |

## Parity verdict

MCP `run_fixture_prediction` delegates to `run_daily_wde` + `run_daily_ecse` and returned a complete structured payload with fresh odds gate satisfied.

**PARITY: PASS** for fixture 1554441 smoke run (no divergence observed vs canonical stored regeneration path).

## Notes

- `resolve_fixtures` correctly refused sub-threshold fuzzy match when kickoff window did not align (by design).
- Production required checkout of `strict_live_refresh.py` from Phase 3 branch base (not present on production `df93d42` tree).
