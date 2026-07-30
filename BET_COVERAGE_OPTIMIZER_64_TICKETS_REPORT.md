# Bet Coverage Optimizer — Research Implementation Report

**Branch:** `feature/bet-coverage-optimizer-64-tickets`  
**Status:** Local validation complete — **not deployed to production** (awaits explicit owner approval)  
**Scope:** Research-only, owner-only. No canonical WDE/ECSE/BTTS/O/U changes. No freeze mutation. No shadow promotion.

## 1. Implementation summary

Additive package `worldcup_predictor/research/bet_coverage_optimizer/` converts each fixture’s multi-model Top-N exact-score distribution plus **REAL** bookmaker markets into exactly **4** selections (3 Exact + 1 Smart Coverage), then expands three fixtures to **4×4×4 = 64** tickets.

- Consensus exact ranking: appearance count → weighted probability → canonical rank → Exact V2 rank
- Smart coverage: deterministic `settles_as_win(...)` mapping + configurable `coverage_score` (utility, not confidence)
- Missing/stale/unmappable markets → `COVERAGE_MARKET_UNAVAILABLE` (never invents replacements)
- GPT Actions owner endpoints + CLI ticket generator
- Reuses `multi_market_odds_loader` for REAL odds; does not modify `exact_score_coverage_advisor`

## 2. Exact files changed

**New**
- `worldcup_predictor/research/bet_coverage_optimizer/` (`__init__.py`, `models.py`, `market_semantics.py`, `score_mapping.py`, `exact_consensus.py`, `candidate_builder.py`, `scoring.py`, `optimizer.py`, `evidence.py`, `service.py`, `generate_tickets.py`)
- `tests/research/bet_coverage_optimizer/test_market_settlement.py`
- `tests/research/bet_coverage_optimizer/test_optimizer_core.py`
- `scripts/run_bet_coverage_optimizer_three_fixtures.py`
- `artifacts/coverage_optimizer/<timestamp>/` (immutable research run)
- `BET_COVERAGE_OPTIMIZER_64_TICKETS_REPORT.md` (this file)

**Modified**
- `worldcup_predictor/gpt_actions/app.py` — owner research job routes
- `worldcup_predictor/gpt_actions/schemas.py` — `CoverageOptimizerJobRequest`
- `worldcup_predictor/gpt_actions/policies.py` — allowlist new + existing research routes
- `tests/gpt_actions/test_gpt_actions_bridge.py` — dry-test route assertions

## 3. Tests and pass counts

```
tests/research/bet_coverage_optimizer .......... 46 passed
tests/gpt_actions/test_gpt_actions_bridge.py::test_dry_test_manifest  passed
```

Coverage includes: settlement boundary cases, consensus ranking, 64 unique tickets, stale rejection, no invented fallbacks, evidence hash stability, owner auth, API schema, freeze/canonical no-write flags.

## 4–6. Three-fixture research recommendations

Artifact root: `artifacts/coverage_optimizer/20260730T223202Z/`

Research markets are **synthetic ResearchBook-shaped** payloads for offline regression (`skip_db_odds=True`). Production use must load live provider odds only.

### 1556628 Dundee United vs Rangers

| # | Selection | Notes |
|---|---|---|
| 1 | Exact **0-2** | Consensus count 3 |
| 2 | Exact **0-1** | Consensus count 3 |
| 3 | Exact **1-2** | Consensus count 3 |
| 4 | **Under 3.5** @ 1.85 (`coverage_score≈0.819`) | Beat Away & Under 4.5 @ 1.72 (`≈0.522`) |

- **Why #4 won:** Higher Top8 mass (includes 1-1, 0-0), full exact overlap, better odds than low-priced Under 4.5 (rejected `<1.55`), and higher `coverage_score` than Away & U4.5 despite the prompt’s narrative preference for Rangers Win & U4.5 when comparing only that family.
- **Covered by #4:** 0-2, 0-1, 1-2, 0-3, 1-1, 0-0  
- **Uncovered Top8:** 1-3, 2-2

### 1494717 Bodø/Glimt vs Lillestrøm

| # | Selection | Notes |
|---|---|---|
| 1 | Exact **2-0** | |
| 2 | Exact **3-0** | |
| 3 | Exact **1-0** | |
| 4 | **Home & Under 4.5** @ 1.68 (`coverage_score≈0.764`) | Beat Home & Over 2.5 and Home Over 2.5 Team Goals |

- Candidate comparison (real ResearchBook odds): Home & U4.5 > Home & O2.5 > Team Over 2.5  
- **Covered by #4:** 2-0, 3-0, 1-0, 4-0, 3-1, 2-1  
- **Uncovered:** 5-0, 0-0

### 1567860 Admira Wacker vs Rapid Wien II

| # | Selection | Notes |
|---|---|---|
| 1 | Exact **1-1** | |
| 2 | Exact **1-0** | |
| 3 | Exact **0-0** | |
| 4 | **Under 3.5** @ 1.78 (`coverage_score≈0.915`) | Beat BTTS Yes, Draw & U4.5, X2 & U4.5 on score |

- **Covered by #4:** 1-1, 1-0, 0-0, 0-1, 2-1, 1-2, 2-0  
- **Uncovered:** 3-1

## 7. Generated 64-ticket artifact paths

Under `artifacts/coverage_optimizer/20260730T223202Z/` (gitignored local research output; regenerate with the runner/CLI):

- `summary.json`
- `recommendations.json`
- `candidate_markets.json`
- `coverage_matrix.csv`
- `tickets_64.csv`
- `tickets_64.json`
- `validation_report.json`
- `run_manifest.json`

CLI:

```text
python -m worldcup_predictor.research.bet_coverage_optimizer.generate_tickets \
  --fixture-ids 1556628 1494717 1567860 \
  --stake-per-ticket 1.00 \
  --output-dir artifacts/coverage_optimizer/<timestamp>/
```

## 8. Proof canonical predictions and freezes unchanged

- No edits to WDE / ECSE / BTTS / O/U formula modules
- Optimizer is read-only vs freezes; `validation_report.json` flags:
  - `canonical_formulas_unchanged: true`
  - `freezes_unchanged: true`
  - `shadow_not_promoted: true`
  - `research_only: true` / `owner_only: true`

## 9. Commit hash and push status

- **Commit:** `050df42`
- **Branch:** `feature/bet-coverage-optimizer-64-tickets` pushed to `origin`
- PR link (optional): https://github.com/pdekam2000/worldcup-predictor-2026/pull/new/feature/bet-coverage-optimizer-64-tickets

## 10. Deployment status

**Not deployed.** Feature branch only. Production deploy requires explicit owner approval after validation review. Local/GitHub/prod parity deferred until that approval.
