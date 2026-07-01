# DB-AUDIT-1 — Coverage Report

**Audit:** PHASE DB-AUDIT-1  
**Mode:** Read-only  
**Database:** `data/football_intelligence.db`  
**Generated:** 2026-06-29 UTC

---

## Overview

| Dataset | Rows | Date range | Bookmakers |
|---------|------|------------|------------|
| Raw odds imports | 2,063,334 | 2024-08-01 → 2026-06-28 | Bet365 only |
| Fixture registry | 223,215 | 2024-08-01 → 2026-06-28 | — |
| Fixture results | 222,985 | (derived from registry) | — |
| Clean pre-match odds | 1,908,702 | (same kickoffs) | Bet365 only |
| Production fixtures | 2,161 | (World Cup scope) | — |

**Clean retention rate:** 1,908,702 / 2,063,334 = **92.47%** (154,632 rows excluded for post-kickoff leakage)

**Results coverage on clean odds:** 1,907,698 / 1,908,702 = **99.95%**

---

## Coverage by Market

### Raw odds (`historical_csv_odds_imports`)

| Market | Rows | % of total |
|--------|------|------------|
| `over_under` | 580,920 | 28.2% |
| `double_chance` | 482,298 | 23.4% |
| `corners_over_under` | 449,996 | 21.8% |
| `team_over_under` | 337,139 | 16.3% |
| `ft_result` | 100,679 | 4.9% |
| `btts` | 77,435 | 3.8% |
| `first_half_winner` | 34,867 | 1.7% |
| **Total** | **2,063,334** | **100%** |

### Clean pre-match odds (`historical_csv_odds_prematch_clean`)

| Market | Rows | % of clean | Retention vs raw |
|--------|------|------------|------------------|
| `over_under` | 524,706 | 27.5% | 90.3% |
| `corners_over_under` | 442,239 | 23.2% | 98.3% |
| `double_chance` | 438,366 | 23.0% | 90.9% |
| `team_over_under` | 313,341 | 16.4% | 92.9% |
| `ft_result` | 87,337 | 4.6% | 86.8% |
| `btts` | 71,139 | 3.7% | 91.9% |
| `first_half_winner` | 31,574 | 1.7% | 90.6% |
| **Total** | **1,908,702** | **100%** | **92.5%** |

`ft_result` has the lowest clean retention (86.8%) — likely higher in-play closing odds movement near kickoff for 1X2 markets.

---

## Coverage by League (Top 20)

From `historical_fixture_registry` (223,215 fixtures):

| Rank | League | Fixtures |
|------|--------|----------|
| 1 | Premier League | 8,618 |
| 2 | Primera Division | 3,618 |
| 3 | Super League | 2,413 |
| 4 | League Two | 1,964 |
| 5 | League One | 1,876 |
| 6 | Championship | 1,857 |
| 7 | Ligue 1 | 1,791 |
| 8 | Club Friendlies 3 | 1,719 |
| 9 | Division 1 | 1,560 |
| 10 | U19 League | 1,537 |
| 11 | Ligue 2 | 1,524 |
| 12 | Superliga | 1,511 |
| 13 | Serie B | 1,504 |
| 14 | Serie A | 1,503 |
| 15 | 2. Liga | 1,402 |
| 16 | First League | 1,245 |
| 17 | Pro League | 1,219 |
| 18 | Primera B Nacional | 1,207 |
| 19 | Enterprise National League | 1,100 |
| 20 | Enterprise National League South | 1,098 |

**Note:** League names are as imported from OddAlerts CSV (not normalized to a single global league ID). Name collisions across countries exist (e.g. multiple "Premier League", "Super League" entries from different nations).

---

## Coverage by Season

From `historical_fixture_registry`:

| Season | Fixtures | % of registry |
|--------|----------|---------------|
| 2024 | 115,053 | 51.5% |
| 2025 | 108,162 | 48.5% |
| **Total** | **223,215** | **100%** |

Data spans roughly two football seasons (Aug 2024 – Jun 2026 calendar dates).

---

## Coverage by Bookmaker

| Bookmaker | Raw odds rows | Clean odds rows |
|-----------|---------------|-----------------|
| Bet365 | 2,063,334 (100%) | 1,908,702 (100%) |

**Single-bookmaker dataset** — all historical CSV odds are Bet365-sourced. No multi-bookmaker arbitrage or consensus odds coverage in this import.

---

## Date Range

| Source | Min date | Max date |
|--------|----------|----------|
| `historical_fixture_registry.match_date` | 2024-08-01 | 2026-06-28 |
| `historical_csv_odds_imports.match_date` | 2024-08-01 | 2026-06-28 |

Approximately **22 months** of historical odds and results coverage.

---

## Production vs Historical Coverage

| Layer | Fixtures | Notes |
|-------|----------|-------|
| Production `fixtures` | 2,161 | World Cup / app scope |
| Historical registry | 223,215 | Global OddAlerts CSV scope |
| Registry → production links | 242 | 0.11% of registry |
| Registry with results | 222,985 | 99.90% of registry |
| Registry without results | 230 | Cancelled/deleted matches |

Historical data is **~100× larger** than production fixtures. ECSE should treat historical tables as the primary modeling corpus; production fixtures are a small live subset.

---

## Join Coverage Matrix

| Join path | Matching rows | Coverage |
|-----------|---------------|----------|
| Clean odds → results (`registry_fixture_id`) | 1,907,698 / 1,908,702 | 99.95% |
| Raw odds → results (`registry_fixture_id`) | 2,062,130 / 2,063,334 | 99.94% |
| Registry → results | 222,985 / 223,215 | 99.90% |
| Registry → production fixtures | 242 / 223,215 | 0.11% |

---

## xG & Snapshot Coverage

| Table | Rows | Coverage note |
|-------|------|---------------|
| `odds_snapshots` | 1,443 | Live/production snapshot store; not part of historical CSV import |
| `xg_snapshots` | 0 | **No xG snapshot data** in database |

ECSE cannot rely on `xg_snapshots` for features — table is empty. xG must come from other feature stores or external providers if needed.

---

## ECSE Coverage Implications

### Strengths
- **1.9M clean pre-match odds rows** across 7 markets
- **223K fixtures** with **223K result labels** (99.9% registry coverage)
- **Two full seasons** of Bet365 odds history
- **Global league breadth** — top leagues well represented

### Gaps
- **Single bookmaker** (Bet365 only)
- **No xG snapshots** in DB
- **Minimal production fixture overlap** (242 links) — historical modeling is largely independent of production `fixtures`
- **230 cancelled fixtures** without result labels
- **1,004 clean odds rows** without matching result (0.05%)

### Recommended modeling filters for ECSE
```sql
-- Primary modeling corpus
SELECT c.*, r.*
FROM historical_csv_odds_prematch_clean c
INNER JOIN historical_fixture_results r
  ON r.registry_fixture_id = c.registry_fixture_id
WHERE c.prematch_verified = 1;
```

Expected usable rows: **~1,907,698**

---

## Market Selection Guidance

| Market | Clean rows | ECSE suitability |
|--------|------------|------------------|
| `over_under` | 524,706 | High volume; primary goal-market corpus |
| `corners_over_under` | 442,239 | High volume; corner-specific models |
| `double_chance` | 438,366 | High volume; derived from 1X2 |
| `team_over_under` | 313,341 | Medium; team-specific totals |
| `ft_result` | 87,337 | Lower volume; core 1X2 market |
| `btts` | 71,139 | Medium; binary outcome |
| `first_half_winner` | 31,574 | Lower volume; half-time market |

---

*Read-only audit. No modifications performed.*
