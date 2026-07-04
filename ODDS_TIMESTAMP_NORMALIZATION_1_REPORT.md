# ODDS-TIMESTAMP-NORMALIZATION-1 — Report

**Phase:** ODDS-TIMESTAMP-NORMALIZATION-1  
**Host:** Hetzner `/opt/worldcup-predictor`  
**Run date:** 2026-07-04  
**Final recommendation:** `FIXTURE_1567310_CONFIRMED_STALE_ODDS`

Also: `ODDS_TIMESTAMP_NORMALIZATION_READY` · `DO_NOT_ENABLE_TIMERS`

---

## Root Cause

Production odds freshness used `freshness_policy.parse_timestamp()`, which only called `datetime.fromisoformat()` after replacing `Z`.

This **failed** on timestamps written by the daily odds import path:

```text
2026-07-04 00:55:59 UTC
```

That format is produced by `euro_c_odds_import._utc_now_iso()` (space-separated + ` UTC` suffix). When parsing failed, `calculate_odds_age_hours()` returned `None` → classification **`ODDS_FRESHNESS_UNKNOWN`** even though valid odds data existed.

---

## Part A — Timestamp Format Audit

Script: `scripts/audit_odds_timestamp_formats.py`  
Artifact: [`ODDS_TIMESTAMP_NORMALIZATION_1_AUDIT.md`](ODDS_TIMESTAMP_NORMALIZATION_1_AUDIT.md)

| Finding | Detail |
|---------|--------|
| Rows scanned | 1464 (recent) |
| Legacy parse failures | **319** |
| Fixed by new parser | **+3** (`space_separated_utc_suffix`) |
| Remaining unparseable | **316** Sportmonks label strings (e.g. `sportmonks_wc2026_2026-06-27`) — not timestamps |

---

## Part B — Parser Implementation

**New module:** `worldcup_predictor/odds/timestamp_normalization.py`

| Function | Purpose |
|----------|---------|
| `normalize_timestamp` / `parse_timestamp_utc` | Safe UTC parsing, never raises |
| `timestamp_age_hours` | Age calculation |
| `format_timestamp_utc` | Canonical write format `YYYY-MM-DDTHH:MM:SS+00:00` |
| `classify_timestamp_format` | Audit format families |
| `explain_timestamp_parse` | Debug/audit helper |

**Updated:** `worldcup_predictor/odds/freshness_policy.py` — uses central normalizer.

**Supported inputs:**

- ISO-8601 with `Z` or offset
- Naive ISO (assumed **UTC**)
- `YYYY-MM-DD HH:MM:SS UTC` (production import format)
- Unix seconds / milliseconds
- datetime objects

---

## Part C — Non-Destructive Migration

| Rule | Status |
|------|--------|
| Bulk rewrite historical `snapshot_at` | **Not done** |
| Parser supports existing formats | ✅ |
| Future writes canonical ISO UTC | ✅ Updated `_utc_now_iso()` in `euro_c_odds_import.py` |
| Predictions preserved | ✅ WDE + ECSE for 1567310 unchanged |

---

## Part D — Fixture 1567310 Re-Audit (0 provider calls)

```bash
export APP_ENV=production
.venv/bin/python scripts/run_odds_freshness_refresh.py \
  --mode audit --fixture-id 1567310 --dry-run --max-provider-calls 0
```

| Field | Before (1B) | After (this run) |
|-------|-------------|------------------|
| Freshness status | `ODDS_FRESHNESS_UNKNOWN` | **`STALE_ODDS`** |
| odds_age_hours | null | **7.44** |
| would_refresh | true | true |
| Provider calls | 0 | **0** |

**Interpretation:** Timestamp now parses correctly. Odds are **not fresh** for knockout (7.44h > 6h threshold) — correct classification, not UNKNOWN.

Latest snapshot: `2026-07-04T00:58:12.671642` (iso8601_naive, assumed UTC).

---

## Part E — Regression Audit

| Provider / source | Sample format | Legacy | New parser |
|-----------------|---------------|--------|------------|
| API-Football import | `2026-07-04 00:55:59 UTC` | ❌ | ✅ |
| live/cache | `2026-07-04T00:58:12.671642` | ✅ | ✅ |
| Sportmonks | `sportmonks_wc2026_2026-06-27` | ❌ | ❌ (not a timestamp) |

No provider calls. No DB writes.

---

## Part F — Validation

```bash
.venv/bin/python scripts/validate_odds_timestamp_normalization_1.py
```

**Result:** **all_passed: true** (full checklist)

Confirmed:

- ISO Z, offset, naive, Unix s/ms parse
- Malformed values return None safely
- Fixture 1567310 parses; not UNKNOWN
- DB row counts unchanged
- WDE + ECSE predictions for 1567310 preserved
- Timers not enabled
- Provider calls: **0**

Artifact: `artifacts/odds_timestamp/odds_timestamp_normalization_1_validation.json`

---

## DB Mutation Status

**No odds snapshots deleted or rewritten.**  
**No predictions regenerated.**

---

## Warnings

1. **316 Sportmonks rows** store non-timestamp labels — will remain UNKNOWN until those rows are re-imported with proper timestamps (separate data-quality task).
2. **Fixture 1567310 odds are STALE** (7.44h) — do not claim `FRESH_ODDS` without a new bounded refresh.
3. **Do not enable timers.**

---

## Next Actions

### After Colombia vs Ghana finishes

1. `results-only` pipeline  
2. `eval-only` pipeline  
3. Evaluation report (ECSE snapshot id=1, WDE 1567310)

### Optional (not in this phase)

- Bounded odds refresh for 1567310 if fresh knockout odds needed before kickoff
- Sportmonks snapshot_at data-quality cleanup (separate phase)

---

## Final Recommendation

### `FIXTURE_1567310_CONFIRMED_STALE_ODDS`

Timestamp normalization is production-ready. Fixture **1567310** now classifies correctly as **`STALE_ODDS`** with numeric age (7.44h), not `ODDS_FRESHNESS_UNKNOWN`. Freshness policy works; odds need refresh if `FRESH_ODDS` is required before prediction use.

**Do not refresh odds or regenerate prediction in this phase.**
