# TWO-FIXTURE PORTFOLIO — REAL ODDS RESEARCH

**Final status:** `TWO_FIXTURE_PORTFOLIO_MORE_FORWARD_DATA_REQUIRED`  
**Generated:** 2026-07-16 04:25:53 UTC

## Scope

ROI tables use **REAL** Correct Score odds only (`odds_kind=REAL`).  
Synthetic odds are **not** used in primary result tables.

Joint probability uses independence approximation P(A)·P(B); same-day / same-league dependence may inflate or reduce realized joint coverage.

Exact-score Top5 subsets are **incomplete** — no arbitrage claims.

## Sample

| Metric | Value |
|---|---|
| Pairs | 13 |
| CS fixtures available | 136 |
| Enriched priced fixtures | 53 |
| Best strategy | EQUAL_GROSS_RETURN |
| Best ROI | -0.12345577119657793 |

## Strategy ROI (real odds)

| Strategy | N | ROI | Hit rate | Full-loss | Recovery | Max DD |
|---|---:|---:|---:|---:|---:|---:|
| EQUAL | 13 | -0.2227509593221011 | 0.3076923076923077 | 0.3076923076923077 | 0.07692307692307693 | 348.45641025641027 |
| EQUAL_GROSS_RETURN | 13 | -0.12345577119657793 | 0.3076923076923077 | 0.3076923076923077 | 0.07692307692307693 | 293.7326342132255 |
| MODEL_PROB_WEIGHTED | 13 | -0.19968665660015775 | 0.3076923076923077 | 0.3076923076923077 | 0.07692307692307693 | 346.644593556103 |
| POSITIVE_EDGE | 13 | -0.8639971495500686 | 0.0 | 0.6153846153846154 | 0.15384615384615385 | 584.4564102564102 |
| MINIMAX | 13 | -0.12345577119657793 | 0.3076923076923077 | 0.3076923076923077 | 0.07692307692307693 | 293.7326342132255 |
| TIERED | 13 | -0.36166119214209297 | 0.3076923076923077 | 0.3076923076923077 | 0.07692307692307693 | 390.0458410382578 |


## Over 3.5

Gaps: 2-1, 1-2, 3-0, 0-3  
Over 3.5 never covers 2-1/1-2/3-0/0-3; CS primary ROI uses real CS only

## Answers

1. api_football (+ sportmonks when present in snapshots); OddAlerts/CSV/TheOddsAPI: no CS
2. Yes — mapped as CORRECT_SCORE_90_MINUTES; live/post-kickoff rejected
3. No full provider historical CS archive; local cached snapshot extraction only
4. Leagues present among joinable CS fixtures in local DB (see selected_pairs.csv)
5. Bookmakers present in correct_score_odds_lines / bookmaker_comparison.csv
6. Varies by fixture — see fixture_market_completeness in CS artifacts
7. Pairs retained only when enough combos priced; n_pairs=13
8. Hedges priced when selection present in real CS map; else UNAVAILABLE
9. ≈ €50.0 primary budget (+ hedge share) when portfolios form
10. -0.12345577119657793 (EQUAL_GROSS_RETURN)
11. 0.07692307692307693
12. 0.3076923076923077
13. MINIMAX roi=-0.12345577119657793 dd=293.7326342132255 vs EQUAL roi=-0.2227509593221011 dd=348.45641025641027
14. Prior coverage research suggested ~5; real-odds sample may be too small to reconfirm economically
15. Over 3.5 leaves three-goal gaps; economic recovery not proven as CS substitute
16. Priced availability leader among hedge kinds: canonical_top6_10
17. Any-other markets stored separately when present; not treated as exact scores
18. Often yes for complete Top5 — SINGLE vs CROSS labelled separately
19. n_pairs=13, cs_fixtures=136, enriched=53 — see final_status
20. Owner-only shadow collection justified; production betting NOT justified

## Constraints

- No production betting
- No automatic placement
- No ECSE/WDE changes
- No freeze modification

Artifacts: `artifacts/two_fixture_portfolio_real_odds/`
