# TWO-FIXTURE EXACT-SCORE PORTFOLIO RESEARCH

**Mode:** Research / shadow only — no production deployment, no automatic betting, no ECSE/freeze changes.

**Final status:** `TWO_FIXTURE_PORTFOLIO_REAL_ODDS_DATA_REQUIRED`

**Generated:** 2026-07-15 21:38:57 UTC

## Prior research locked

- Canonical Top5 untouched-test ≈ **43.34%**
- Shift Both +1 Top5 ≈ **23.66%** (not a model)
- Canonical ∪ Shifted ≤10 ≈ **53.24%**
- Policy: `ECSE_SCORE_SHIFT_COMPLEMENTARY_ONLY_FOR_TOP10_OR_HEDGE`

Canonical Top5 is **never replaced**. Shifted scores appear only in the hedge candidate pool.

## Odds inventory

| Source | Count / flag |
|---|---|
| Correct-score import rows | 0 |
| Real exact-score odds available | **False** |
| Over 3.5 clean rows | 9584 |
| BTTS yes clean rows | 47104 |

No historical correct-score market rows found in CSV imports/clean. Profitability research uses labeled SYNTHETIC exact-score odds only. Over 3.5 / BTTS closing odds from ecse_training_dataset are real when present.

## Structural result (25 primary combos)

For eligible fixtures A and B:

```text
5 canonical scores(A) × 5 canonical scores(B) = 25 primary tickets
ComboOdds(i,j) = OddsA(i) × OddsB(j)   # when real odds exist
P(Ai ∧ Bj) ≈ P(Ai)×P(Bj)               # independence approximation
```

Joint probability uses independence approximation P(A)·P(B); same-day / same-league dependence may inflate or reduce realized joint coverage.

Exact-score Top5×Top5 is **incomplete** outcome space → inverse-sum on 25 tickets is **not** arbitrage.

## Walk-forward coverage (chronological, prematch features only)

Best selection gate by hedge-enhanced hit rate: **highest_expected_joint**

| Metric | Value |
|---|---|
| Portfolios | 411 |
| Primary 25 hit rate | 0.38929440389294406 |
| Hedge-enhanced hit rate | 0.8004866180048662 |
| Avg model joint Top5×Top5 | 0.3442009553009059 |
| Avg model joint union10×union10 | 0.7188373862207772 |
| Full-loss rate (vs hedge union) | 0.19951338199513383 |
| ROI (currency) | UNAVAILABLE (no historical CS odds) |

## Over 3.5 hedge

Over 3.5 **does not** cover: 2-1, 1-2, 3-0, 0-3.

Real Over 3.5 closing odds were used for market-hedge structure comparisons when present.
Primary exact-score payouts in those comparisons are **synthetic** and labeled as such.

## Answers (1–20)

1. Viable mathematically as a **coverage structure**? **Yes as a coverage/upside structure; not proven as a profitable betting system**
2. Historical primary 25-combo hit rate? **0.38929440389294406 (best gate); mean across gates ≈ 0.24957937113307763**
3. Approx joint Top5 coverage (model)? **0.148306558779411 on demo pair; walk-forward avg 0.3442009553009059**
4. Shifted/hedge pool coverage gain? **demo Δjoint=0.2585260299318361; walk-forward union avg 0.7188373862207772**
5. Optimal hedge ticket count (marginal)? **~5 extra tickets by gain/ticket on curve (research)**
6. Best hedge type per unit? **canonical_top6_10**
7. Over 3.5 useful recovery? **inconclusive_without_cs_odds**
8. Uncovered three-goal scenarios? **2-1, 1-2, 3-0, 0-3**
9. Can hedge recover full stake? **Only if hedge odds × stake ≥ total portfolio stake; not guaranteed; not proven with real CS odds**
10. Under what odds/stake conditions? **Requires stake_h ≥ TotalStake / Odds_h and non-overlapping win conditions; bookmaker min stake may block**
11. Worst-case loss? **Full stake loss on uncovered outcomes (demo −€50.0 if budget=50.0)**
12. Full-loss probability estimate? **≈ 1 − joint_union_model (demo 0.5931674112887528); WF full-loss 0.19951338199513383**
13. Equal staking vs optimized? **EQUAL expected_net=-7.627 min_covered=138.876; MINIMAX expected_net=-7.627 min_covered=235.711 (SYNTHETIC only)**
14. Minimax reduce drawdown? **Minimax equalizes covered-scenario return (synthetic); does not eliminate uncovered full-loss drawdown**
15. Exact-score odds after margin? **Unknown historically — no CS odds; synthetic medium margin implies negative EV on average**
16. Historical CS odds for ROI? **NO — trustworthy currency ROI test blocked**
17. Best fixture-selection gate? **highest_expected_joint**
18. Daily pipeline owner-only? **Yes — owner-only shadow report after real CS odds wired; never public auto-bet**
19. Production deployment justified? **NO**
20. Exact next step? **Ingest legitimate prematch exact-score odds (bookmaker+timestamp+settlement) then rerun stake/ROI validation**

## Daily pipeline (design only — not deployed)

Command concept: `دو بازی مناسب امروز برای پکیج ۲۵تایی و پوشش‌ها را نشان بده`

1. Use already frozen daily predictions  
2. Select two highest-quality exact-score fixtures  
3. Fetch **current legitimate** exact-score odds  
4. Build 25 primary tickets + limited hedges  
5. Optimize stakes / show worst-case  
6. Manual owner approval only  
7. Never auto-place bets  
8. Keep separate from public SaaS predictions  

## Constraints respected

- No production model change  
- No freeze edits  
- No automatic betting  
- No fabricated historical CS odds  
- Synthetic sensitivity clearly separated  
- Shadow research only  

## Artifacts

See `artifacts/two_fixture_portfolio/`.

## Final status

`TWO_FIXTURE_PORTFOLIO_REAL_ODDS_DATA_REQUIRED`

STOP.
