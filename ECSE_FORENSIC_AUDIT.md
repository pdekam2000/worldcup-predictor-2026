# ECSE Forensic Audit

**Phase:** EESO-SHADOW-RESEARCH-1  
**Mode:** Read-only documentation — confirms canonical ECSE isolation

## 1. Odds snapshot inputs

Prematch closing odds feed the research replay path:

- `oddsFT_1` / `oddsFT_X` / `oddsFT_2` (1X2)
- BTTS yes/no, O/U 1.5/2.5/3.5/4.5, team goal lines
- Mapped via `external_row_to_ecse_odds_features` → `extract_lambdas`

Production path uses `odds_snapshots` table; replay uses historical CSV rows with identical lambda extraction (`ECSE-1C-v1`).

## 2. Lambda extraction

`worldcup_predictor/research/ecse_lambda_extraction.py`:

- Combines O/U 2.5 (40%), O/U 1.5 (20%), O/U 3.5 (15%), team sum (25%)
- Floors/ceilings: λ ∈ [0.15, 6.0]
- BTTS odds inform λ indirectly — not used in Top5 ranking

## 3. Score distribution generation

`worldcup_predictor/research/ecse_score_distribution.py` (`ECSE-1D-B-v1`):

- Poisson grid to MAX_GOALS=7 with Dixon–Coles τ adjustment (ρ default −0.13)
- Probabilities normalized to sum 1.0
- `OTHER` bucket for tail mass

## 4. Canonical sorting

Scores sorted by **descending probability** — pure probability ranking.

## 5. Top1 / Top3 / Top5 / Top10 selection

| Output | Selection rule |
|---|---|
| Top1 | Highest-probability scoreline |
| Top3 | Ranks 1–3 by probability |
| Top5 | Ranks 1–5 by probability |
| Top10 | Ranks 1–10 by probability |

## 6. Top3 Mass

Sum of probabilities of the top 3 scorelines in the full distribution.

## 7. Top5 Mass

Sum of probabilities of the top 5 scorelines.

## 8. Entropy

Shannon entropy over the full distribution (replay uses top ~65 lines).

## 9. WDE relationship

- WDE uses form points, season stats, goal timing — **separate agent path**
- WDE 1X2 decision does **not** rerank canonical ECSE Top5 in production
- EESO shadow `wde_aligned_top5` reorders within canonical grid only (research)

## 10. BTTS relationship

- BTTS odds used in λ estimation
- BTTS agent output independent of ECSE Top5 ranking
- No BTTS feature in canonical Top5 sort key

## 11. O/U relationship

- O/U odds primary driver of total-goals λ component
- O/U agent independent of Top5 ranking

## 12. Last8 relationship

- **Not consumed** by canonical ECSE (`ecse_live/prediction_builder.py`)
- Last8 used only in EESO/Last8 **shadow selectors** (research)
- Confirmed: `ecse_uses_recent_scoring_profiles = False`

## 13. xG relationship

- Not available in historical CSV replay path
- Not used in canonical Top5 ranking
- Optional field in EESO dataset — explicit `null`

## 14. League prior relationship

- No league-specific scoring prior in canonical ECSE distribution
- League context available for shadow scenario profiling only

## 15. Known over-concentration failure mode

When λ_home >> λ_away, Poisson mass clusters on home clean-sheet lines (e.g. 3-0, 2-0, 4-0, 1-0, 5-0). Coverage flags:

- `ALL_TOP5_CLEAN_SHEET`
- `TOP5_OVER_CONCENTRATED`
- `NO_OPPONENT_ONE_GOAL_COVERAGE`

Historical hit rate may still be high in these segments — concentration alone is not penalized without evidence.

## Explicit Confirmations

| Claim | Status |
|---|---|
| Canonical ECSE Top5 is pure probability ranking | **Confirmed** |
| WDE does not rerank canonical Top5 | **Confirmed** |
| Last8 does not affect canonical Top5 | **Confirmed** |
| xG does not affect canonical Top5 | **Confirmed** |

## Forensic reference cases

### Djurgårdens IF vs Halmstad (fixture 1494202)

Canonical Top5: 3-0, 2-0, 4-0, 1-0, 5-0 — all home clean-sheet cluster. Last8 away scoring frequency and home clean-sheet history must be weighed against whether 2-1/3-1 existed in Top10.

### KA Akureyri vs IA Akranes (fixture 1508804)

Actual 3-2 — failure may originate in probability generation (3-2 outside Top10) rather than Top5 selection alone.
