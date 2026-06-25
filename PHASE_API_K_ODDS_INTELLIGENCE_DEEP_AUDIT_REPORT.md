# PHASE API-K — Odds Intelligence Deep Audit

**Mode:** Audit → Attribution → Backtest → Ranking → Report  
**Production deploy:** NO  

---

## Executive Answer

**Which odds signals generated the +28.7pp API-J improvement?**

Evidence points to **consensus 1X2 implied probabilities routed into `first_goal_pressure`** — not a dedicated first-goal market or movement field.

Mechanism (unchanged from API-J, confirmed in API-K isolation):

1. Strategy D enrichment sets `first_goal_pressure` from `odds_implied_home` / `odds_implied_away`.
2. Baseline `_pick_first_goal_team` adds **+0.05** to the side with `pressure_edge`.
3. This breaks the **0.04 tie band** that otherwise returns `"none"` → evaluation `pending`.

- API-J Strategy D FG: **74.5%** vs A **45.8%**
- API-K best EGIE odds variant: **D7 (sharp 1X2) 75.3%** | D2 closing **75.0%** | D4 consensus **74.3%** | D3 movement-only **51.7%**

**Primary driver:** `consensus_implied_home` / `consensus_implied_away` (Match Winner / Fulltime Result).  
**Secondary (smaller EGIE lift):** `First Team To Score` market (D5/D6).  
**Not a driver in current enrichment:** `odds_movement` field (parsed but not wired to Strategy D).

---

## STEP 1 — Odds Inventory

Artifacts: `artifacts/odds_inventory_audit.json`

- Fixtures audited: **185**
- With match-winner odds: **105**

### EGIE fields today

- `odds_implied_home` — 56.76% coverage — **enrich_agent_outputs -> first_goal_pressure (Strategy D)**
- `odds_implied_away` — 0.0% coverage — **enrich_agent_outputs -> first_goal_pressure**
- `odds_implied_draw` — 0.0% coverage — **odds_goal_intelligence agent signal only (not FG pick path)**
- `first_goal_odds` — 56.76% coverage — **parsed but not used in production enrichment**
- `odds_movement` — 56.76% coverage — **stored on ProviderFeatureVector; not applied in Strategy D enrichment**

## STEP 2 — Odds Feature Attribution (direct market vs actual)

- **sharp_1x2**: FG hit 78.7% (n=94)
- **closing_1x2**: FG hit 78.3% (n=92)
- **consensus_1x2**: FG hit 77.7% (n=94)
- **opening_1x2**: FG hit 77.7% (n=94)
- **soft_1x2**: FG hit 77.7% (n=94)
- **first_team_to_score**: FG hit 77.4% (n=93)
- **favorite_strength**: FG hit 77.3% (n=97)
- **movement_direction**: FG hit 48.4% (n=97)

## STEP 3 & 7 — D1–D8 Backtest

| Strategy | FG Team | Pending | Goal Range | Soft Min | Coverage |
|----------|---------|---------|------------|----------|----------|
| A | 45.8% | 110 | 23.1% | 28.4% | 168 |
| D1 | 74.3% | 33 | 23.1% | 28.4% | 98 |
| D2 | 75.0% | 30 | 23.1% | 28.4% | 98 |
| D3 | 51.7% | 47 | 23.1% | 28.4% | 98 |
| D4 | 74.3% | 33 | 23.1% | 28.4% | 98 |
| D5 | 74.0% | 34 | 23.1% | 28.4% | 98 |
| D6 | 74.0% | 34 | 23.1% | 28.4% | 98 |
| D7 | 75.2% | 33 | 23.1% | 28.4% | 98 |
| D8 | 70.5% | 29 | 23.1% | 28.4% | 98 |

## STEP 4 — Market Efficiency

- **match_winner_favorite**: 77.3% (n=97)
- **first_team_to_score**: 78.3% (n=97)
- **over_25_favorite**: 52.4% (n=105)
- Favorite scores first: **77.3%**

## STEP 5 — Sharp vs Soft

- **sharp**: FG 78.7% (n=94)
- **soft**: FG 77.7% (n=94)
- **consensus**: FG 77.7% (n=94)

## STEP 6 — Odds Movement

- Closing static: **78.3%**
- Movement direction: **48.4%**
- Movement outperforms static: **False**

## STEP 8 — Signal Ranking

- **S** — Direct market: sharp_1x2: EGIE FG None (Δ vs A n/a)
- **S** — Direct market: closing_1x2: EGIE FG None (Δ vs A n/a)
- **S** — Direct market: consensus_1x2: EGIE FG None (Δ vs A n/a)
- **S** — Direct market: opening_1x2: EGIE FG None (Δ vs A n/a)
- **S** — Direct market: soft_1x2: EGIE FG None (Δ vs A n/a)
- **S** — Direct market: first_team_to_score: EGIE FG None (Δ vs A n/a)
- **S** — Direct market: favorite_strength: EGIE FG None (Δ vs A n/a)
- **B** — Direct market: movement_direction: EGIE FG None (Δ vs A n/a)
- **S** — consensus_odds_only: EGIE FG 0.7525 (Δ vs A +29.4pp)
- **S** — closing_odds_only: EGIE FG 0.75 (Δ vs A +29.2pp)
- **S** — opening_odds_only: EGIE FG 0.7426 (Δ vs A +28.4pp)
- **S** — implied_probabilities_only: EGIE FG 0.7426 (Δ vs A +28.4pp)

## STEP 9 — Recommendation

**A) Odds-Augmented Intelligence** is supported by measured evidence for UEFA EGIE at current coverage (~48% odds).

xG-centric path (B) showed no FG lift at 3.6% xG coverage in API-J.

Roadmap:
1. Promote **consensus 1X2 implied** as Tier S FG driver (already active in Strategy D).
2. Add **First Team To Score** as Tier A supplemental signal (D5/D6).
3. Wire **closing vs opening** only after movement analysis shows edge (currently static ≈ movement).
4. Keep xG as secondary until season-filtered xG holdout exceeds 30% coverage.

---

**STOP — No deploy. No production changes.**
