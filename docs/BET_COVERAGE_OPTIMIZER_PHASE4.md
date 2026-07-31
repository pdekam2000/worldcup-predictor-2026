# Bet Coverage Optimizer — Phase 4: Forward Shadow Audit

**Status string:** `BET_COVERAGE_OPTIMIZER_PHASE4_FORWARD_SHADOW_READY`  
**Branch:** `feature/bet-coverage-optimizer-64-tickets`  
**Deploy:** **NOT DEPLOYED** (research-only / owner-only)

## Purpose

Phase 4 does **not** add new betting logic. It proves that Main + Insurance tickets are:

1. Fully auditable (ticket forensic trail)
2. Traceable to real bookmaker markets (no ResearchBook / synthetic / fabricated odds)
3. Measurably better at reducing complete coupon failure (historical replay)
4. Ready for ongoing forward-shadow evaluation (SQLite store)

## Hard constraints

- Research only / owner only
- No production deploy
- No schema migration
- No canonical / ECSE / WDE / freeze modifications
- No shadow promotion

## Artifacts

`artifacts/coverage_optimizer/phase4_<timestamp>/` (gitignored):

| Artifact | Part |
|---|---|
| `ticket_audit.json` / `.csv` | Ticket forensic audit |
| `coverage_explanation.json` | Scoreline-level coverage (Primary / Insurance / Residual) |
| `insurance_validation.json` | Uncovered-mass + alternative market comparison |
| `real_market_validation.json` | Bookmaker source / timestamp / market id trail |
| `historical_replay.json` / `.md` | ≥100 fixture replay, no leakage |
| `forward_shadow.db` | Prediction-day store + evaluations |
| `forward_shadow_summary.json` | Daily / weekly / monthly ROI summary |
| `owner_phase4_report.html` / `.md` | Owner visual report |
| `final_recommendations.json` | Exact1–3 + Main + Insurance + stakes |
| `validation_report.json` | Success criteria + deployment status |

## Runner

```bash
python scripts/run_bco_phase4_research.py \
  --real-odds-json worldcup_predictor/research/bet_coverage_optimizer/fixtures/interwetten_three_fixture_markets.json \
  --stake-mode score_weighted
```

## Success criteria

Phase 4 is complete only when:

- Main + Insurance reduces complete coupon-failure frequency vs Main-only (historical replay)
- All generated tickets are auditable and priced markets trace to real bookmaker data
- No synthetic / fabricated odds are used for priced coverage/insurance markets
- Forward shadow DB + summary are ready
- Production remains unchanged (**NOT DEPLOYED**)
