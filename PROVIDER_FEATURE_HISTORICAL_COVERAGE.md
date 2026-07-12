# Provider Feature Historical Coverage

Audited: 2026-07-12T02:51:17.144387+00:00
Completed fixtures: 2236

## Feature coverage (SQLite)

| Feature | Eligible | With feature | Coverage % |
|---------|----------|--------------|------------|
| odds_snapshots | 2236 | 868 | 38.82% |
| xg_snapshots | 2236 | 24 | 1.07% |
| fixture_enrichment | 2236 | 1913 | 85.55% |
| enrichment_lineups | 2040 | 1531 | 75.05% |
| enrichment_statistics | 2040 | 1531 | 75.05% |
| oddalerts_probability_rows | 2236 | 547 | 24.46% |
| predictions | 2236 | 5 | 0.22% |

## By competition (odds)

| Competition | Completed | With odds | Coverage % |
|-------------|-----------|-----------|------------|
| bundesliga | 1232 | 72 | 5.84% |
| premier_league | 380 | 380 | 100.0% |
| world_cup_2026 | 334 | 333 | 99.7% |
| conference_league | 118 | 23 | 19.49% |
| champions_league | 116 | 30 | 25.86% |
| europa_league | 56 | 30 | 53.57% |

## Historical CSV staging (stored)

- WDE shadow dataset: **77,023** rows (2022-09-20 → 2026-07-01)
- OddAlerts probability rows: **8.7M+** (crosswalk-limited to ~547 completed fixtures in SQLite)
- SportMonks enrichment: **51** fixtures
- xG snapshots: **26** fixtures

**Gap:** Pre-match xG and lineup/injury snapshot coverage insufficient for promotion.
