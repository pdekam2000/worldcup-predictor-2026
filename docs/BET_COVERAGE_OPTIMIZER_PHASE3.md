# Bet Coverage Optimizer — Phase 3: Insurance Pick & Real Odds Validation

**Status string:** `BET_COVERAGE_OPTIMIZER_PHASE3_INSURANCE_VALIDATED`  
**Branch:** `feature/bet-coverage-optimizer-64-tickets`  
**Deploy:** **NOT DEPLOYED** (research-only / owner-only)

## Purpose of Insurance Pick

Insurance is a **second protection layer**. It does **not** replace Main Coverage.

| Layer | Role |
|---|---|
| Exact 1–3 | Model consensus exact scores |
| Main Coverage | Best single market covering remaining Top-N mass + overlap |
| **Insurance** | Covers **still-uncovered** Top-N outcomes after the four primary selections |

Full **5×5×5 = 125** expansion is **not** the default. Insurance tickets are selective (default max **15**, min **3** when candidates exist), prioritizing **single-insurance-leg** tickets.

## Uncovered probability mass

For each fixture, using the existing Top-N ECSE/consensus matrix (unchanged):

```
primary_covered = Exact1 ∪ Exact2 ∪ Exact3 ∪ MainCoverageScores
primary_uncovered_mass = Σ p(score) for score in TopN \ primary_covered
```

Also reports uncovered result-direction and goal-profile distributions.

## Real odds sources

Supported JSON/CSV with required fields: `fixture_id`, `bookmaker`, `captured_at_utc`, `source_type`, `market_family`, `selection`, `odds`.

- `manual_screenshot_transcription` is allowed **only** when explicitly labeled — **never** presented as API-sourced.
- Stale / missing / non-positive / unmapped / conflicting duplicates are rejected.
- Odds are **never fabricated**.

Sample: `data/research/interwetten_three_fixture_markets.json`

## Stake modes

- `equal` (default)
- `score_weighted`
- `kelly_research` (disabled by default; research-labeled; not guaranteed profit)

## Modeled coverage vs monetary EV

- **Theoretical model coverage** = Top-N probability mass covered by Exact3 + Main [+ best Insurance].
- **Monetary EV** only when all ticket legs have real odds.
- Otherwise use **probability-mass utility** and label clearly: `unknown_due_to_missing_odds`.

**Warning:** This is research tooling. Nothing here is guaranteed profit.

## Artifacts

`artifacts/coverage_optimizer/phase3_<timestamp>/` (gitignored):

- `phase3_research_bundle.json`
- `real_odds_validation.json`
- `uncovered_score_matrix.json`
- `insurance_candidates_ranked.json`
- `insurance_recommendations.json`
- `main_64_tickets.csv` / `.json`
- `insurance_tickets.csv` / `.json`
- `budget_allocation.json`
- `main_vs_insurance_comparison.json`
- `validation_report.json`

## Runner

```text
python scripts/run_bco_phase3_research.py \
  --top-n 8 \
  --real-odds-json data/research/interwetten_three_fixture_markets.json \
  --total-budget 400 \
  --main-budget-ratio 0.80 \
  --max-insurance-tickets 15 \
  --stake-mode score_weighted
```

## Validation

- Phase 2 + Phase 3 tests green
- Canonical WDE/ECSE formulas unchanged
- Freezes unchanged
- No production deploy
