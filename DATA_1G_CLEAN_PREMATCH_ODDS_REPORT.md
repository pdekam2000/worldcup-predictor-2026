# DATA-1G Clean Pre-Match Odds Report

## Build summary

| Metric | Value |
|--------|-------|
| Source rows scanned | 2063334 |
| Clean rows inserted | 1908702 |
| Skipped (duplicate rerun) | 0 |
| Retention % | 92.5057 |
| Excluded: closing after kickoff | 154614 |
| Excluded: opening after kickoff | 0 |
| Excluded: peak after kickoff | 18 |
| Excluded: missing kickoff unix | 0 |
| Build batch | `749fbc00f3b50338` |

## Integrity audit

- Source `historical_csv_odds_imports` rows: **2063334** (unchanged)
- Clean table rows: **1908702**
- `closing_unix > kickoff_unix` violations: **0**

## Filter rules

- `closing_unix` and `kickoff_unix` required
- `closing_unix <= kickoff_unix` (strict)
- `opening_unix <= kickoff_unix` when present
- `peak_unix <= kickoff_unix` when present
- Valid `closing_odds >= 1.0`
- Original import rows **not modified or deleted**

## Raw vs clean ROI (strategy A)

| Dataset | Bets | ROI % | Hit % |
|---------|------|-------|-------|
| Raw (closing+opening fallback) | 2060830 | -5.262 | 69.2097 |
| Clean pre-match closing only | 1906482 | -5.227 | 69.4113 |

## Strategy C/D impact (clean)

- **C ≥3.5** — raw ROI 9.0859% (3527 bets) → clean ROI 7.8827% (3266 bets)
- **D 3.5–12** — raw ROI 7.3035% (3443 bets) → clean ROI 5.8558% (3184 bets)
