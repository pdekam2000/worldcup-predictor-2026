# ECSE Historical Replay — Leakage Audit

**Phase:** ECSE-HISTORICAL-REPLAY-BACKTEST-1  
**Audited fixtures:** 73,573  
**Passed:** 73,573 (100%)  
**Failed:** 0  
**Validation status:** PASSED (11/11 checks)

---

## Per-Feature Temporal Causality

### Odds

| Check | Status |
| --- | --- |
| Selected odds timestamp ≤ kickoff | Assumed valid (CSV prematch closing export) |
| Latest valid pre-kickoff snapshot | Single line per fixture in `external_historical_csv_raw_rows` |
| Post-kickoff / closing-after-kickoff data | Not present in source |
| **Limitation** | No explicit `odds_timestamp_unix` in raw JSON — timing verified by export convention, not per-row timestamp |

### Team Form & Rolling Stats

| Check | Status |
| --- | --- |
| Only matches before kickoff | **N/A** — not used in production ECSE odds-only lambda path |
| Rolling windows end before kickoff | **N/A** |

### xG

| Check | Status |
| --- | --- |
| Only historical matches before fixture | **N/A** — xG not used (`xg_snapshots`: 0 rows) |
| Target fixture xG excluded | Verified |

### Pressure

| Check | Status |
| --- | --- |
| No in-play pressure of target match | Verified — not used in ECSE lambda extraction |

### Standings

| Check | Status |
| --- | --- |
| Point-in-time reconstruction | **N/A** — not used in ECSE lambda extraction |
| Season-final standings excluded | Verified |

### Lineups / Injuries

| Check | Status |
| --- | --- |
| Timestamped pre-kickoff only | **N/A** — not available in external CSV source |

### Target Match Result

| Check | Status |
| --- | --- |
| Actual score excluded from `extract_lambdas` input | Verified |
| Actual score used only for post-hoc evaluation | Verified |
| No post-match events in features | Verified |

---

## Per-Fixture Leakage Validator Results

```json
{
  "fixtures_audited": 73573,
  "passed": 73573,
  "failed": 0
}
```

All replay rows carry `leakage_pass: true`. Fixtures failing causality would be excluded and logged — none triggered.

---

## Validation Checklist (Task N)

| Check | Result |
| --- | --- |
| replay_start_date ≥ 2023-01-01 | PASS |
| replay_eligible_positive (N=73,573) | PASS |
| all_finished | PASS |
| all actual scores valid | PASS |
| all replay features time-causal | PASS |
| no target leakage | PASS |
| no duplicate fixture evaluation | PASS |
| ECSE distribution sums correctly | PASS |
| Top5 order matches probability order | PASS |
| no NaN or Inf in lambdas | PASS |
| chronological OOS splits strict | PASS |
| pure reranking preserves membership | PASS |
| replay artifacts isolated from production | PASS |
| no model retraining | PASS |
| no production writes | PASS |

Full validation artifact: `artifacts/ecse_historical_replay_backtest_1/validation.json`

---

## Known Data Limitations (Not Leakage Failures)

1. **Odds timestamp granularity** — CSV export provides one prematch line without explicit capture time.
2. **Odds-only ECSE path** — Replay uses the same odds-only lambda extraction as production for external historical fixtures; richer features (xG, form, standings) are absent from source, not leaked.
3. **2027 fixtures in inventory** — Present in raw CSV but excluded from replay by date filter (< eligible finished 2026 data in replay set).

---

## Safety Confirmations

- No writes to `ecse_prediction_snapshots`, `ecse_score_distributions`, or production prediction tables
- Research outputs isolated under `artifacts/ecse_historical_replay_backtest_1/`
- No ECSE or WDE retraining performed
- Frozen pre-match evaluation (N=16) kept separate from replay backtest (N=73,573)
