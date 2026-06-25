# PHASE 54C-2 — Odds Parser Fix + Historical Odds Source Audit

**Mode:** Implement parser fix → Validate existing WC odds → Audit historical alternatives → Report  
**Status:** Complete — parser fixed and validated; PL historical odds still blocked at source  
**Deploy:** Not performed

---

## Executive summary

| Area | Result |
|------|--------|
| Parser bug | **Fixed** — `parse_odds_snapshots()` now reads stored JSON shapes |
| WC odds utilization | **0 → 100%** parseable (1,049/1,049 rows; 85/85 fixtures via EGIE store) |
| PL odds snapshots | **Unchanged** — 0 rows (no backfill rerun per constraints) |
| Historical PL source | **API-Football `/odds` insufficient** — alternatives audited below |
| Recommended next step | **Phase 54C-3:** CSV historical import OR OddAlerts plan upgrade + predict-time capture |

---

## Root cause from Phase 54C-1

1. **Storage alignment:** PL `fixture_id`s (1035037+) had zero `odds_snapshots`; WC/demo ids held 1,055 rows.
2. **Live API gap:** `GET /odds?fixture={pl_id}` returned `results: 0` for all 380 finished PL fixtures (380 API calls consumed).
3. **Parser gap (this phase):** Even WC rows with rich `api_sports.bookmakers` JSON were **unreadable** by EGIE because `parse_odds_snapshots()` called `extract_api_sports_probs()` on a raw dict, which expects `report.odds.bookmakers` — not snapshot payload shapes.

---

## Parser bug details

### Symptom

```python
# Pre-54C-2: always returned empty implied probs
extract_api_sports_probs({"api_sports": {"bookmakers": [...]}})
# → {} because no .odds attribute on dict
```

### Stored payload shapes (measured)

| Shape keys | Row count |
|------------|----------:|
| `api_sports`, `snapshot_at`, `source` | 969 |
| `api_sports`, `snapshot_at`, `source`, `the_odds_api` | 85 |
| `bookmakers`, `cache_source`, `snapshot_at`, `source` | 1 |

### Fix

New module `worldcup_predictor/egie/provider_features/odds_snapshot_parser.py`:

- `extract_bookmakers_from_payload()` — supports `api_sports.bookmakers`, top-level `bookmakers`, `response[].bookmakers`, `the_odds_api.bookmakers`
- `normalize_snapshot_odds_lines()` — stable lines: `fixture_id`, `bookmaker`, `market_name`, `selection`, `odd`, `source`, `captured_at`
- `parse_snapshot_payload()` — implied probs for **1X2**, **O/U 2.5**, **BTTS**

`parse_odds_snapshots()` in `extractors.py` updated to use the new parser (same public return shape + optional OU/BTTS fields).

**Not changed:** WDE, SaaS predict, EGIE enrichment/scoring weights, Goal Timing agent math, DB schema.

---

## Files changed

| File | Change |
|------|--------|
| `worldcup_predictor/egie/provider_features/odds_snapshot_parser.py` | **New** — snapshot normalization + market parsers |
| `worldcup_predictor/egie/provider_features/extractors.py` | `parse_odds_snapshots()` delegates to new parser |
| `scripts/validate_phase54c2_odds_parser_fix.py` | **New** — before/after validation |

---

## Validation results (before / after)

Run: `python scripts/validate_phase54c2_odds_parser_fix.py`  
Artifact: `artifacts/phase54c2_odds_parser_validation.json`

| Metric | Before fix | After fix |
|--------|------------|-----------|
| WC snapshot rows scanned | 1,049 | 1,049 |
| Parseable 1X2 rows | **0** | **1,049** (100%) |
| Parseable O/U 2.5 rows | **0** | **1,049** (100%) |
| Parseable BTTS rows | **0** | **905** (86.3%) |
| EGIE fixtures with `coverage.odds` | **0** | **85 / 85** WC fixtures |
| PL odds fixtures | 0 | 0 (unchanged) |
| WC rows modified/deleted | — | **0** (1,055 before = after) |

**Validation:** 12/12 PASS

---

## WC odds utilization status

| Consumer | Status |
|----------|--------|
| `EgieProviderFeatureStore.build()` | **Ready** — 85/85 WC fixtures with odds implied home/away/draw |
| `parse_odds_snapshots()` integration | **10/10** sample fixtures pass |
| Strategies D/E/F (odds arm) | **Ready for WC cohort** when replay uses fixtures with snapshots |
| World Cup production predict | Unchanged — no production logic touched |

---

## EGIE odds readiness

| Cohort | Snapshots | Parser | EGIE `coverage.odds` |
|--------|-----------|--------|----------------------|
| World Cup (85 fixtures) | Yes | **Fixed** | **100%** |
| Premier League (380 fixtures) | **No** | N/A | **0%** |

EGIE odds strategies **D / E / F** can now activate on **WC fixtures with stored snapshots**. PL backtest cohort remains odds-blind until a historical source is ingested.

---

## Goal Timing odds readiness

| Item | Status |
|------|--------|
| Parser → EGIE store | **Ready** (85/85 WC) |
| `GoalTimingFeatureBuilder.has_reliable_goal_odds` | **PL-scoped only** — builder returns empty features for `world_cup_2026` via `is_goal_timing_allowed_league()` |
| PL Goal Timing odds | **Blocked** — 0 PL snapshots + PL-only scope |

When PL odds rows exist, Goal Timing will pick up `has_reliable_goal_odds` automatically via the same `EgieProviderFeatureStore` path (no Goal Timing math changes required).

---

## PART C — Historical odds source audit

### 1. Predict-time capture only

| Dimension | Assessment |
|-----------|------------|
| Historical coverage | **0%** for finished PL 2023 — forward-looking only |
| Cost / quota | Low — piggyback on existing predict pipeline `OddsSnapshotService` |
| Fixture mapping | **Trivial** — uses live `fixture_id` |
| Markets | Full API-Football bookmaker JSON at capture time |
| Backtest usefulness | **None** for existing 380 PL fixtures |
| Production usefulness | **High** — strongest path for live SaaS confidence |
| Priority | **#1 for production** |

**Recommendation:** Enable mandatory odds snapshot on every PL predict before kickoff (shadow first). Does not solve EGIE PL backtest.

---

### 2. CSV import

| Dimension | Assessment |
|-----------|------------|
| Historical coverage | **Potentially 100%** of PL season if source has date/home/away + odds |
| Cost / quota | **Zero API** after one-time download |
| Fixture mapping | **Medium** — match `date + home_team + away_team` → internal `fixture_id` (380 rows feasible) |
| Markets | Depends on source: football-data.co.uk provides 1X2 + O/U 2.5; Kaggle/paid archives may add BTTS |
| Backtest usefulness | **High** — only viable path for full PL 2023 EGIE odds replay without API history |
| Production usefulness | Low — static archive |
| Priority | **#1 for PL backtest backfill** |

**Candidate sources:**

- [football-data.co.uk](https://www.football-data.co.uk) — free PL CSV, 1X2 + O/U, season 2023/24 available
- Kaggle historical odds datasets — variable quality
- OddAlerts export — if plan exposes PL pool (currently **0 rows** on trial)
- The Odds API historical — paid; sport `soccer_epl` may have archives (key configured in `.env`)

**Safest ingest:** New script writing to `odds_snapshots` with `source: csv_historical_import` — parser already supports `bookmakers` shape.

---

### 3. Third-party API

#### OddAlerts

| Dimension | Assessment |
|-----------|------------|
| Historical coverage | **0 PL rows** on current trial (OA-2, OA-4 audits) |
| Cost | Advanced plan; 902 WC rows proved pipeline works |
| Mapping | Module exists: `oddalerts_historical_odds.py`, `oddalerts_fixture_map` |
| Markets | Rich: ft_result, btts, asian_handicap, total_goals, etc. |
| Backtest | **Blocked** until plan unlocks PL `fixtures/results` |
| Production | Medium — if pool expands |
| Priority | **#3** — revisit after plan upgrade |

#### The Odds API

| Dimension | Assessment |
|-----------|------------|
| Historical coverage | **Unknown for PL 2023** — key present; used in 85 WC snapshot supplements |
| Cost | Per-request; historical endpoints may be paid tier |
| Mapping | Event matching by team names + date |
| Markets | h2h, totals, btts (already parsed in new module) |
| Backtest | **Medium potential** — needs scoped audit (no API calls in this phase) |
| Production | Medium — good for upcoming fixtures |
| Priority | **#2** — audit historical endpoint availability before spend |

#### Sportmonks

| Dimension | Assessment |
|-----------|------------|
| Historical coverage | **0/380 PL mapping**; xG blocked; odds/predictions WC-guarded on live path |
| Cost | High; subscription-dependent |
| Mapping | **0%** today |
| Markets | Odds predictions, xG, pressure (if unblocked) |
| Backtest | Low until mapping fixed |
| Production | Deferred |
| Priority | **#4** |

#### API-Football `/odds` (retest conclusion)

| Dimension | Assessment |
|-----------|------------|
| Historical coverage | **0%** for finished PL (380/380 empty in 54C-1) |
| Upcoming fixtures | **Works** (WC 2026 `results: 1`) |
| Priority | **Capture only** — not a backfill source |

---

### 4. No-odds EGIE baseline

| Dimension | Assessment |
|-----------|------------|
| Historical coverage | N/A — events at 94.5%, odds at 0% |
| Cost | Zero |
| Backtest | Strategies A/B/C remain valid; D/E/F identical to A on odds arm |
| Production | Acceptable short-term with `no_bet` gates |
| Priority | **Fallback** — already operational |

---

## Source priority matrix

| Priority | Source | Best for | Blocker |
|----------|--------|----------|---------|
| **1** | Predict-time capture | Production forward | No PL history |
| **2** | CSV import (football-data.co.uk) | PL 2023 EGIE backtest | Manual ingest script (54C-3) |
| **3** | The Odds API historical audit | PL + multi-book | Endpoint/cost audit needed |
| **4** | OddAlerts upgrade | Multi-market history | Trial pool has 0 PL fixtures |
| **5** | Sportmonks | xG + odds combo | Mapping + plan |
| **—** | API-Football `/odds` backfill | — | **Ruled out** for finished PL |

---

## Safest Phase 54C-3 next step

**Recommended: CSV historical PL odds import (football-data.co.uk)**

1. Download PL 2023/24 CSV (free, proven 1X2 + O/U columns).
2. Map rows → internal `fixture_id` via `kickoff_utc + home_team + away_team` fuzzy match against SQLite `fixtures`.
3. Write `odds_snapshots` with `source: csv_historical_import` and `bookmakers` JSON (parser-ready).
4. Re-run `validate_phase54c2_odds_parser_fix.py` + PL-specific coverage check.
5. **Do not** rerun API-Football live backfill for finished PL fixtures.

**Parallel (production):** Shadow predict-time odds capture for upcoming PL fixtures before kickoff.

**Do not deploy** until 54C-3 ingest is validated and EGIE PL `coverage.odds` > 50% on replay sample.

---

## Commands

```bash
# Validate parser fix (no API calls)
python scripts/validate_phase54c2_odds_parser_fix.py
```

---

## Constraints honored

- No PL odds backfill rerun
- No additional API calls for finished PL fixtures
- No WDE / SaaS / EGIE scoring / Goal Timing math changes
- No migrations
- No deploy
- WC rows preserved (1,055 total, unmodified)

---

**STOP — Await approval for Phase 54C-3 (CSV historical import).**
