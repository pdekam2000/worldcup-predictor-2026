# PHASE OA-1 — OddAlerts Provider Trial Audit

**Mode:** Audit only  
**Production deploy:** NO  
**EGIE / prediction engine:** UNCHANGED  

---

## Executive Answer

**Is OddAlerts useful?** **Yes — conditionally** for probability model + multi-book odds history. Not a Sportmonks FG replacement on measured evidence.

**Worth monthly pay?** Conditional — yes for probability+odds-history bundle if PL/BL list access unlocked; no as FG primary replacement for Sportmonks today

**Recommended architecture:** Keep API-Football as fixture/results spine; keep Sportmonks for UEFA sharp odds; add OddAlerts as OPTIONAL enrichment shadow for probability model + odds history (not primary FG path until finished-fixture API access and FTS market verified).

### Nine decision questions

1. **Useful?** Yes for odds history + probability on single-fixture includes; bulk fixtures list blocked.
2. **Better than Sportmonks for betting intelligence?** **No for FG Team** — Sportmonks sharp MW 78.7% (K2); OA FG accuracy **not measured** (0 finished fixtures in pool).
3. **Improves FG Team?** **Not proven** — no FTS market in history sample; no finished FG evaluable rows.
4. **Improves BTTS?** **Not proven** — probability available but outcome accuracy not measurable on upcoming-only pool.
5. **Improves O/U?** **Not proven** — same limitation.
6. **Improves Match Winner?** **Promising signals** — consensus/closing/sharp derivable from odds history; accuracy not measured.
7. **Monthly pay justified?** Conditional on unlocking bulk historical fixture access.
8. **Provider ranking:** see below.
9. **Architecture:** API-Football spine + Sportmonks UEFA odds + OddAlerts optional shadow.

---

## STEP 1 — Connectivity

Artifact: `artifacts/oddalerts_connectivity_test.json`

- **Configured:** True
- **Pass / Fail:** 9 / 3
- Raw samples: `artifacts/oddalerts_raw/`

| Endpoint | OK | Notes |
|----------|-----|-------|
| bookmakers | True | 8 |
| competitions | True | 5 |
| fixtures_list | False | non_json_response |
| fixture_details | True | 1 |
| fixtures_multiple | True | 1 |
| odds_history | True | 296 |
| odds_latest | True | 250 |
| probability | False | non_json_response |
| predictions | False | non_json_response |
| stats_fixture | True | 2 |
| value_upcoming | True | 5 |
| trends_homeWin | True | 179 |

## STEP 2 — League Coverage

- **world_cup** (id 1690): fixtures_seen=28, odds=28, probability=28, opening/closing/peak=28
- **champions_league** (id 51): fixtures_seen=0, odds=0, probability=0, opening/closing/peak=0
- **europa_league** (id 32): fixtures_seen=0, odds=0, probability=0, opening/closing/peak=0
- **premier_league** (id 423): fixtures_seen=0, odds=0, probability=0, opening/closing/peak=0
- **bundesliga** (id 477): fixtures_seen=0, odds=0, probability=0, opening/closing/peak=0
- **la_liga** (id 419): fixtures_seen=0, odds=0, probability=0, opening/closing/peak=0
- **serie_a** (id 499): fixtures_seen=0, odds=0, probability=0, opening/closing/peak=0

## STEP 3 — Sharp Book Audit

- History rows (sample fixture): **296**
- FTS market present: **False**
- Markets: asian_corners, asian_corners_1h, asian_handicap, away_goals, btts, btts_1h, btts_2h, btts_o25, dnb, double_chance, ft_result, goal_line, highest_scoring_half, home_goals, ht_result, total_corners, tot
- **pinnacle** listed=True history_rows=40
- **bet365** listed=True history_rows=71
- **1xbet** listed=True history_rows=71
- **williamhill** listed=True history_rows=28
- **betfair** listed=True history_rows=13
- **kambi** listed=True history_rows=57

## STEP 4 — First Goal Signal Test

- Fixtures scanned: **120**
- Evaluable finished: **0**
- Limitation: No finished fixtures with FG labels in OA pool; FG accuracy null unless evaluable_finished_fixtures>0
- **A_consensus_match_winner**: accuracy n/a, coverage=120, pending_rate=100.0%
- **B_closing_match_winner**: accuracy n/a, coverage=120, pending_rate=100.0%
- **C_sharp_match_winner**: accuracy n/a, coverage=34, pending_rate=100.0%
- **D_first_team_to_score_proxy**: accuracy n/a, coverage=52, pending_rate=100.0%
- **E_combined_odds_signal**: accuracy n/a, coverage=120, pending_rate=100.0%

K2 reference (Sportmonks UEFA): sharp MW 78.7% (n=104)

## STEP 5 — BTTS / O-U Audit

- BTTS probability rows: 80 | measurable accuracy: False
- O/U 2.5 probability rows: 80 | measurable accuracy: False
- EGIE LGBM baselines (ML-1): BTTS 0.5525, O/U 0.5463

## STEP 6 — Correct Score Audit

- Correct score market in history: **False**
- Useful for exact score engine: **True**
- Useful for goal timing: **True**
- xG proxy fields: {'o05_home_goals_prob': 86.25, 'o15_home_goals_prob': 59.86, 'o05_away_goals_prob': 40.09, 'o15_away_goals_prob': 11.52}

## STEP 7 — Historical Depth

- Competitions paginated: 2266
- Odds history window: ~6 months opening/closing/peak per OddAlerts docs
- Fixtures list endpoint: redirects (302) on competition/date filters
- Value/past endpoint: returns empty body on trial token

## STEP 8 — Provider Ranking

- **Sportmonks** (score 88): UEFA odds + enrichment — 78.7% sharp MW (K2, n=104 UEFA)
- **OddAlerts** (score 72): Probability model + multi-book odds history — Not measured — no finished FG sample
- **API-Football** (score 65): Primary fixtures/results/events store — EGIE events + 1617 finished rows; odds enrichment 4.3%

## Strengths / Gaps

- Strength: Core endpoints reachable (fixture detail, odds/history, value, trends)
- Strength: Rich opening/closing/peak odds history per fixture
- Gap: No first_team_to_score market in odds history sample
- Gap: FG Team accuracy not measurable — zero finished fixtures in sampled pool
- Gap: Low Premier League visibility in upcoming value pool during audit window

---

**STOP — Audit only. No deploy. No production changes.**
