# PHASE DAILY-OWNER-2 — Daily Odds Import Report

## Summary

Daily odds readiness scanning and cache-first import are implemented and wired into the owner daily cycle. Provider calls are enabled with quota caps; imported odds are normalized for WDE/ECSE consumption.

**Final recommendation: `DAILY_OWNER_CYCLE_READY`**

---

## Files changed / created

| Path | Role |
|------|------|
| `worldcup_predictor/owner_daily/odds_import.py` | Part A/B/C — scan, import, normalized probabilities |
| `worldcup_predictor/owner_daily/provider_call_log.py` | Part F — `market` field on log rows |
| `worldcup_predictor/owner_daily/cycle.py` | Part D — `--fetch-missing-odds` integration |
| `worldcup_predictor/owner_daily/report.py` | Odds source/freshness in daily report |
| `scripts/scan_daily_odds_readiness.py` | Part A CLI |
| `scripts/import_daily_odds.py` | Part B CLI |
| `scripts/validate_daily_owner_odds_import.py` | Part G validation |
| `scripts/run_daily_owner_prediction_cycle.py` | Part D scheduler flags |
| `scripts/owner_daily_predictions.py` | `--fetch-missing-odds`, `--include-shadow` |

---

## Providers used

| Provider | Priority | Usage |
|----------|----------|--------|
| **Local cache / SQLite** | 1 | Disk cache + existing `odds_snapshots` |
| **API-Football** | 2 | Primary live odds fetch (`/odds`) |
| **OddAlerts** | 3 | Fallback via `odds/history` when configured |
| **Sportmonks** | 4 | Enrichment cache odds when crosswalk exists |

All calls logged to `logs/daily_provider_calls_YYYYMMDD.jsonl`.

---

## Fixtures scanned (2026-06-30)

- **1 fixture:** Netherlands vs Morocco (`world_cup_2026`, fixture_id `1562345`)

---

## Odds coverage before / after

| Metric | Before import | After import |
|--------|---------------|--------------|
| has_1x2 | 0 | 1 |
| has_ou25 | 0 | 1 |
| has_btts | 0 | 1 |
| has_ou15 / ou35 / DC / CS | 0 | 1 each |
| wde_ready | 0 | 1 |
| ecse_ready | 0 | 1 |
| lambda_inputs_available | false | true |
| odds_freshness | missing | fresh |

---

## Market coverage table (after)

| Market | Netherlands vs Morocco |
|--------|------------------------|
| 1X2 | yes (ph≈0.42, pd≈0.28, pa≈0.30) |
| O/U 2.5 | yes |
| BTTS | yes |
| O/U 1.5 | yes |
| O/U 3.5 | yes |
| Double Chance | yes |
| Correct Score | yes |

Normalized fields stored in snapshot `flat_probabilities` + `normalized` block (bookmaker count, consensus, overround).

---

## Provider calls used

First successful import run:

- **cache_hits:** 1 (disk cache before live call)
- **imported_count:** 1
- **provider:** api-football
- **raw payload:** `artifacts/daily_owner/raw_odds_payloads/1562345_*_api-football.json`

Subsequent runs (cache-first, only-missing):

- **skipped:** `fresh_complete_odds` — no redundant API calls

---

## Daily report label change

| | Before (DAILY-OWNER-1) | After (DAILY-OWNER-2) |
|--|------------------------|------------------------|
| Owner label | DATA_MISSING | WEAK_SIGNAL |
| WDE confidence | — | 72.9 |
| ECSE Top-1 | 1-0 | 1-0 |
| Odds in report | none | source + freshness |
| DATA_MISSING count | 1 | 0 (for odds-driven label) |

Report: `reports/owner/daily_predictions_20260630.md`

---

## Validation result

```
python scripts/validate_daily_owner_odds_import.py
```

**21 / 21 checks passed** — `artifacts/daily_owner_odds_import_validation.json`

Verified: readiness scan, missing/complete detection, quota caps, cache reuse, provider-backed odds, no fake data, valid normalized probs, no NaN/inf, raw payload refs, ECSE `build_odds_feature_row` readable, public/WDE/ECSE/EGIE/billing unchanged.

---

## Recommended daily command

```bash
python scripts/run_daily_owner_prediction_cycle.py \
  --timezone Europe/Vienna \
  --fetch-missing-odds \
  --max-api-football-calls 100 \
  --max-oddalerts-calls 100 \
  --max-sportmonks-calls 100
```

Standalone odds tools:

```bash
python scripts/scan_daily_odds_readiness.py --date today --timezone Europe/Vienna
python scripts/import_daily_odds.py --date today --timezone Europe/Vienna --max-api-football-calls 100
python scripts/owner_daily_predictions.py --date today --timezone Europe/Vienna --fetch-missing-odds --include-shadow --limit 20
```

---

## Remaining blockers

- **OddAlerts:** `ODDALERTS_API_KEY` not configured — fallback unavailable (`can_fetch_from_oddalerts: false`). Not blocking when API-Football odds exist.
- **Sportmonks live odds:** Uses enrichment cache only; live fetch not required for WC sample after API-Football import.
- **WDE owner stamp:** WDE loads from production store (`generated_by` ≠ `owner_daily_predictions`); label is WEAK_SIGNAL not STRONG (WDE/ECSE 1X2 alignment partial). No prediction logic changed.

---

## Final recommendation

### `DAILY_OWNER_CYCLE_READY`

Odds import pipeline is operational. Run the daily cycle with `--fetch-missing-odds` each morning; cache-first logic avoids wasting API quota when odds are already fresh.

No public exposure. No WDE/ECSE/EGIE/billing changes.
