# PHASE DL-0 — Deep Learning Dataset Readiness Audit

**Mode:** Audit → Feasibility → Architecture → Report  
**Training:** NO  
**Production deploy:** NO  

---

## Executive Answer

**Is Deep Learning justified today?**

**No.** Current datasets are too small, too sparse on xG/pressure/injuries, and recent audits show **parser fixes + sharp odds intelligence** deliver larger gains than ML. Classical survival (+3.2pp goal range) has not yet justified deep survival.

**If only ONE system could be built next, what generates the largest improvement?**

**Option F — Hybrid ML + Market Intelligence** (score 88/100). Extend **Hybrid ML + Market Intelligence** (odds-primary routing, sharp MW enrichment) — measured **+28–29pp FG Team** on UEFA (API-K) vs baseline, vs survival shadow **−1.5pp FG** (Phase 52A).

Do **not** build FT-Transformer or Deep Survival yet: survival parquet has **380 rows** (need 10,000+) and **0% first_goal_minute labels** populated.

### Six key decisions

1. **DL justified?** No — data pipeline first.
2. **First DL market?** None yet; if forced: **Goal Range** via classical survival before deep survival.
3. **Highest ROI architecture?** **Market Intelligence + LightGBM hybrid**, not neural.
4. **Stay rule-based?** **Goal Minute** (3.4% exact), **Goalscorer** (no labels).
5. **Stay odds-driven?** **First Goal Team**, **Match Winner** (sharp MW 78.7% FG).
6. **Become neural?** **Nothing today** — thresholds fail on all neural options.

---

## STEP 1 — Dataset Inventory

Artifact: `artifacts/dl_dataset_inventory.json`

| Dataset | Rows | Features | Key gap |
|---------|------|----------|---------|
| EGIE Survival | 380 | 36 | FG minute 100% null in parquet |
| Goal Events | 1621 | 8 | OK for events |
| API-Football Historical | 1905 | 12 | Odds enrichment 4.3% |
| UEFA Club | 220 | 45 | xG 96.4% missing |
| Odds | 1240 | 15 | Strong in UEFA cache only |
| Lineups | 1531 | 6 | EGIE provider 3.16% |
| Injuries | 0 | 4 | 0% coverage |
| Match Statistics | 1531 | 20 | 91% enrichment coverage |
| xG | 0 | 8 | Critical bottleneck |
| Pressure | 0 | 4 | 0% in store |
| Prediction History | 108 | 22 | Mostly live WC |
| Accuracy Tracker | 134 | — | 70 verified markets |

## STEP 2 — Market Readiness

- **first_goal_team**: **PARTIAL** — samples=380; Labels exist but EGIE baseline 51%; odds enrichment 79% — DL unlikely to beat market intelligence
- **goal_range**: **PARTIAL** — samples=380; Survival shadow +3.2pp but below 35% target; needs more timing labels
- **goal_minute**: **NOT READY** — samples=0; Timing labels missing in survival parquet; exact minute 3.4% baseline
- **next_goal_team**: **NOT READY** — samples=499; No dedicated in-play label store
- **btts**: **READY** — samples=1617; 1617 labels; classical ML sufficient
- **over_1_5**: **READY** — samples=1617; 
- **over_2_5**: **READY** — samples=1617; 
- **over_3_5**: **READY** — samples=1617; 
- **match_winner**: **READY** — samples=1617; 1617 results; odds-driven approaches dominate
- **correct_score**: **PARTIAL** — samples=1617; Needs Poisson/neural Poisson; sample OK but high cardinality
- **first_half_goal**: **PARTIAL** — samples=499; Events exist; half-time labels need extraction
- **anytime_goalscorer**: **NOT READY** — samples=0; 0 player_stats_snapshots; no player history store
- **first_goalscorer**: **NOT READY** — samples=0; No scorer label dataset; prediction_history has sparse scorer fields

## STEP 3 — Feature Coverage

- **odds**: coverage 4.28%, usable 84.09% — API-Football enrichment odds 4.3%; UEFA Sportmonks cache strong
- **closing_odds**: coverage 56.76%, usable 56.76% — UEFA K2 closing MW coverage on mapped fixtures
- **sharp_odds**: coverage 56.76%, usable 56.76% — Sharp MW 78.7% FG accuracy; primary signal
- **events**: coverage 90.97%, usable 94.47% — fixture_goal_events + enrichment events
- **lineups**: coverage 90.91%, usable 3.16% — Enrichment lineups high; EGIE provider lineups 3.16%
- **injuries**: coverage 0.0%, usable 0.0%
- **statistics**: coverage 90.91%, usable 90.9%
- **xg**: coverage 0.0%, usable 3.6% — Primary bottleneck per API-J
- **pressure**: coverage 0.0%, usable 0.0%
- **predictions**: coverage 6.41%, usable 4.16% — Live WC predictions; limited verified outcomes

## STEP 4 — DL Suitability Ranking

- **Tier C** — fg_team: Odds intelligence 78.7% vs baseline 51%; DL adds complexity without beating sharp MW
- **Tier B** — goal_range: Kaplan-Meier survival +3.2pp; classical survival may suffice before deep survival
- **Tier C** — goal_minute: Labels missing in parquet; 3.4% exact accuracy; data fix required first
- **Tier A** — btts: 1600+ labels, balanced; tabular ML likely optimal
- **Tier A** — over_under: 1600+ labels; Poisson/LightGBM standard approach
- **Tier B** — correct_score: High cardinality; neural Poisson possible but needs more seasons
- **Tier C** — goalscorer: No player-level history store

## STEP 5 — Architecture Matching

- **first_goal_team**: market_intelligence, logistic_regression, lightgbm
- **goal_range**: kaplan_meier, hazard_model, lightgbm
- **goal_minute**: hazard_model, temporal_survival
- **btts**: logistic, lightgbm, poisson_btts
- **over_under**: poisson, lightgbm, market_intelligence
- **correct_score**: poisson, dixon_coles
- **goalscorer**: player_embeddings
- **match_winner**: market_intelligence, elo, lightgbm

## STEP 6 — Data Threshold Check

- **ft_transformer**: FAIL
- **temporal_transformer**: FAIL
- **deep_survival_network**: FAIL
- **player_embedding_engine**: FAIL
- **lightgbm_tabular**: PASS
- **neural_tabular**: FAIL

## STEP 7 — Roadmap Decision (ranked)

- **A. No Deep Learning yet** (score 95): Data quality + odds intelligence outperform ML; fix labels/xG/odds pipeline first
- **F. Hybrid ML + Market Intelligence** (score 88): Extend odds-primary + EGIE enrichment; proven +28pp FG lift on UEFA
- **B. Deep Survival Network** (score 35): Timing labels insufficient; classical survival only +3.2pp so far
- **D. Temporal Transformer** (score 25): Events exist but sequential training pipeline not built
- **C. FT-Transformer** (score 15): 380 rows vs 10000 required
- **E. Player Embedding Engine** (score 10): 0 player stats snapshots

## Recommendation

**Primary:** Option **A** — No Deep Learning yet.
**Secondary:** Option **F** — Hybrid ML + Market Intelligence.

Before any neural work:
- Populate `first_goal_minute` in survival parquet from `fixture_goal_events`
- Expand xG and odds coverage beyond UEFA/Bundesliga silos
- Ingest injuries + player history for goalscorer markets

---

**STOP — No training. No deploy. No production changes.**
