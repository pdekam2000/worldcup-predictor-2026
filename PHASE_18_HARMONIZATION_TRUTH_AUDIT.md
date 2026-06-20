# Phase 18 — Harmonization Truth Audit

Generated: 2026-06-19T18:16:10.449191+00:00

## Mode

- **Read-only audit** — no code, weight, or deploy changes
- Same replay methodology as Phase 17

## 1. Dataset

- Fixtures analyzed: **207**
- Sources: {'historical_csv': 12, 'db_bundesliga': 180, 'live_wc': 15}

## 2. Accuracy comparison

| Layer | Accuracy |
|-------|----------|
| WDE (pre-harmonization) | **34.8%** |
| Scoreline-implied 1X2 | **30.0%** |
| Harmonized final (production) | **30.0%** |

- WDE − Final delta: **+4.8%** (positive = harmonization hurts vs WDE-only)
- Scoreline ≡ Final on all fixtures (harmonization always aligns 1X2 to scoreline)

## 3. Conflict & override statistics

| Metric | Value |
|--------|-------|
| WDE vs scoreline conflict rate | 91.8% |
| Override rate (WDE ≠ final) | 91.8% |
| Helpful overrides (WDE wrong → final right) | 53 (27.9% of overrides) |
| Harmful overrides (WDE right → final wrong) | 63 (33.2% of overrides) |
| Neutral overrides (both wrong) | 74 |

## 4. Override analysis

Total overrides: **190** / 207

### Helpful override examples

- **1375862** 1. FC Heidenheim vs SV Elversberg: WDE `home_win` → Final `draw` | Actual `draw`
- **1224278** FSV Mainz 05 vs Bayer Leverkusen: WDE `home_win` → Final `draw` | Actual `draw`
- **1224266** Eintracht Frankfurt vs FC St. Pauli: WDE `home_win` → Final `draw` | Actual `draw`
- **1224267** Werder Bremen vs RB Leipzig: WDE `home_win` → Final `draw` | Actual `draw`
- **1224268** VfL Wolfsburg vs 1899 Hoffenheim: WDE `home_win` → Final `draw` | Actual `draw`

### Harmful override examples

- **1224273** Borussia Dortmund vs Holstein Kiel: WDE `home_win` → Final `draw` | Actual `home_win`
- **1224264** VfB Stuttgart vs FC Augsburg: WDE `home_win` → Final `draw` | Actual `home_win`
- **1224265** Bayern München vs Borussia Mönchengladbach: WDE `home_win` → Final `draw` | Actual `home_win`
- **1224255** Borussia Dortmund vs VfL Wolfsburg: WDE `home_win` → Final `draw` | Actual `home_win`
- **1224248** Eintracht Frankfurt vs RB Leipzig: WDE `home_win` → Final `draw` | Actual `home_win`
- **1224253** Holstein Kiel vs Borussia Mönchengladbach: WDE `home_win` → Final `draw` | Actual `home_win`
- **1224247** Bayern München vs FSV Mainz 05: WDE `home_win` → Final `draw` | Actual `home_win`
- **1224245** Bayer Leverkusen vs FC Augsburg: WDE `home_win` → Final `draw` | Actual `home_win`

## 5. Cohort analysis

| Cohort | n | WDE | Scoreline | Final | Override % | Harmful % | Helpful % |
|--------|---|-----|-----------|-------|------------|-----------|-----------|
| World Cup | 27 | 40.7% | 51.9% | 51.9% | 37.0% | 20.0% | 50.0% |
| Bundesliga | 180 | 33.9% | 26.7% | 26.7% | 100.0% | 33.9% | 26.7% |
| With odds | 25 | 36.0% | 52.0% | 52.0% | 36.0% | 11.1% | 55.6% |
| Without odds | 182 | 34.6% | 26.9% | 26.9% | 99.5% | 34.3% | 26.5% |
| High data quality (≥60%) | 13 | 30.8% | 61.5% | 61.5% | 61.5% | 12.5% | 62.5% |
| Low data quality (<45%) | 192 | 34.4% | 27.6% | 27.6% | 94.3% | 33.7% | 26.5% |

## 6. When harmonization helps vs hurts

- **Conflicts where WDE was right:** 63 fixtures
- **Conflicts where scoreline/final was right:** 53 fixtures

**Harmonization helps** when WDE disagrees with scoreline and scoreline matches actual (53 cases, 27.9% of overrides).

**Harmonization hurts** when WDE was correct but scoreline override was wrong (63 cases, 33.2% of overrides).

## 7. Architecture recommendation

**Remove or gate harmonization** on this sample: WDE-only accuracy (34.8%) beats harmonized final (30.0%) by 4.8%.

Suggested WDE-win conditions (from harmful override cohorts):
- Prefer **WDE** when odds/consensus available and WDE ≠ scoreline draw forced by low λ spread
- Prefer **scoreline** when WDE conflicts with market consensus and scoreline aligns with odds
- **Bundesliga offline replays**: high override rate with majority **harmful** — do not force scoreline 1X2

## Success criteria answers

**Q1 — If harmonization removed entirely, does accuracy improve?** **YES** — WDE-only would be **34.8%** vs final **30.0%** (+4.8%).

**Q2 — When does harmonization help?** When scoreline-implied 1X2 is correct and WDE is wrong (53 overrides, 27.9% of override events). More common when WDE over-commits to draws or wrong side.

**Q3 — When does harmonization hurt?** When WDE is correct but scoreline λ forces wrong 1X2 (63 overrides, 33.2% of override events). Dominant on Bundesliga bulk replay.

**Q4 — Conditions where WDE should win?** Fixtures with **odds available**, **WDE ≠ scoreline**, and **λ spread below median** (draw-collapse path). WDE was right in **63** conflict fixtures vs scoreline **53**.

**Q5 — What percentage of overrides are harmful?** **33.2%** of all overrides (63 / 190). Helpful: **27.9%**. Neutral (both wrong): **38.9%**.

**Stop — audit only. No implementation. No deploy.**
