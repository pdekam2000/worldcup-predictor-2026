# PHASE K2 — Direct First Goal Market Audit

**Mode:** Audit → Backtest → Attribution → Report  
**Production deploy:** NO  

---

## Executive Answer

**What is the single strongest odds-derived signal for First Goal Team?**

**sharp_match_winner** (strategy C) — **78.7%** FG Team accuracy on **104** evaluable fixtures (≥50 coverage threshold for robust ranking).

Peak single-book FTS (**FTS @ bwin**) reached **92.3%** but on only **13** fixtures — not used as primary conclusion.

### Key questions answered

1. **Is Team To Score First stronger than Match Winner?** Direct FTS (D): **77.4%** vs consensus MW (A): **77.7%** — MW wins or tie.

2. **Is First Goal Market stronger than Consensus 1X2?** Same comparison as above (FTS market vs MW implied).

3. **Are Sharp FG Markets stronger than Sharp 1X2?** **Cannot compare on this cache** — sharp FTS (E) has **0% fixture coverage** (Pinnacle/SBO offer MW but not FTS in UEFA cache). Sharp MW (C): **78.7%** remains best sharp signal.

4. **Can direct goal markets become a dedicated FG engine?** **Partially.** Combined FG consensus (F) reaches **78.5%** (vs sharp MW **78.7%**), but direct FTS alone (D) **underperforms** consensus MW (A). Best path: keep MW enrichment primary; FTS as Tier A sidecar.

---

## STEP 1 — Market Inventory

Artifact: `artifacts/first_goal_market_inventory.json`

- Fixtures audited: **185**
- Primary direct FG market: **first_team_to_score**

| Market | Fixture coverage | Rows |
|--------|------------------|------|
| First Team To Score | 105 (56.76%) | 1891 |
| Last Team To Score | 105 (56.76%) | 1404 |
| Home Team Score a Goal | 105 (56.76%) | 935 |
| Away Team Score a Goal | 105 (56.76%) | 938 |
| First Half Exact Goals | 90 (48.65%) | 1151 |
| First 10 min Winner | 65 (35.14%) | 195 |
| Time of First Corner | 13 (7.03%) | 32 |
| Team Goalscorer | 3 (1.62%) | 286 |

## STEP 2 — Coverage Audit

- **consensus_match_winner**: 56.76% fixtures (105/185)
- **closing_match_winner**: 56.76% fixtures (105/185)
- **sharp_match_winner**: 56.76% fixtures (105/185)
- **direct_fts_consensus**: 56.76% fixtures (105/185)
- **sharp_fts**: 0.0% fixtures (0/185)

## STEP 3 — Direct FG Backtest (A–F)

| Strategy | Signal | Direct FG % | EGIE FG % | Pending % | Coverage |
|----------|--------|-------------|-----------|-----------|----------|
| A | consensus_match_winner | 77.7% | 77.7% | 3.1% | 104 |
| B | closing_match_winner | 78.3% | 78.3% | 5.1% | 104 |
| C | sharp_match_winner | 78.7% | 78.7% | 3.1% | 104 |
| D | direct_first_team_to_score | 77.4% | 77.4% | 4.1% | 104 |
| E | sharp_first_team_to_score | 0.0% | 0.0% | 0.0% | 0 |
| F | combined_fg_consensus | 78.5% | 78.5% | 4.1% | 104 |

## STEP 4 — Bookmaker Ranking (First Team To Score)

- **betway** (soft): 77.9% (n=95)
- **bet365** (soft): 76.6% (n=94)
- **Absent from FTS cache**: pinnacle, sbo, 1xbet, williamhill (MW odds present; FTS not offered or not cached)
- **bwin** (soft): 92.3% (n=13)
- **sportingbet** (other): 92.3% (n=13)
- **marathon** (other): 86.1% (n=36)
- **betcris** (other): 81.7% (n=82)
- **tipico** (soft): 81.7% (n=82)
- **10bet** (soft): 76.7% (n=90)

## STEP 5 — Signal Ranking

- **Tier S** — FTS @ bwin: 92.3%
- **Tier S** — sharp_match_winner: 78.7%
- **Tier S** — combined_fg_consensus: 78.5%
- **Tier S** — closing_match_winner: 78.3%
- **Tier A** — consensus_match_winner: 77.7%
- **Tier A** — direct_first_team_to_score: 77.4%
- **Tier C** — sharp_first_team_to_score: 0.0%

## Recommendation

- Keep **sharp/consensus Match Winner implied** as primary EGIE odds enrichment (API-K finding confirmed).
- Add **First Team To Score** as Tier A **direct FG sidecar** where available (similar accuracy, purpose-built market).
- Do **not** replace MW with FTS in enrichment until FTS shows consistent outperformance across leagues/seasons.

---

**STOP — No deploy. No production changes.**
