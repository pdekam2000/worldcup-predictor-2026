# TFPS CANONICAL COMMIT INVENTORY

**Local HEAD before:** `435f8ee6cf9a9886724f8732faeabaa9c460de48`  
**origin/main before:** `435f8ee6cf9a9886724f8732faeabaa9c460de48`  
**Date:** 2026-07-16

## Classification

### SOURCE (stage)

| Path | Class |
|---|---|
| `worldcup_predictor/research/correct_score_odds/` | SOURCE |
| `worldcup_predictor/research/two_fixture_forward_shadow/` | SOURCE |
| `worldcup_predictor/research/two_fixture_portfolio/` | SOURCE |
| `worldcup_predictor/database/migrations.py` | SOURCE |
| `worldcup_predictor/owner_daily/pipeline/orchestrator.py` | SOURCE |
| `scripts/run_correct_score_odds_ingestion.py` | SOURCE |
| `scripts/run_two_fixture_exact_score_portfolio_research.py` | SOURCE |
| `scripts/run_two_fixture_portfolio_real_odds_research.py` | SOURCE |
| `scripts/run_two_fixture_forward_shadow_cycle.py` | SOURCE |
| `scripts/validate_correct_score_odds_ingestion.py` | VALIDATOR |
| `scripts/validate_two_fixture_exact_score_portfolio_research.py` | VALIDATOR |
| `scripts/validate_two_fixture_forward_shadow_collection.py` | VALIDATOR |
| `scripts/validate_two_fixture_forward_shadow_production_deploy.py` | VALIDATOR |
| `deployment/systemd/worldcup-two-fixture-shadow.service` | SYSTEMD_TEMPLATE |
| `deployment/systemd/worldcup-two-fixture-shadow.timer` | SYSTEMD_TEMPLATE |

### DOCUMENTATION (force-add approved owner docs only)

| Path | Class |
|---|---|
| `reports/owner/TFPS_CANONICAL_COMMIT_INVENTORY.md` | DOCUMENTATION |
| `reports/owner/TWO_FIXTURE_FORWARD_SHADOW_PREFLIGHT.md` | DOCUMENTATION |
| `reports/owner/TWO_FIXTURE_FORWARD_SHADOW_ACTIVATION_REPORT.md` | DOCUMENTATION |
| `reports/owner/TWO_FIXTURE_FORWARD_SHADOW_PRODUCTION_DEPLOY_REPORT.md` | DOCUMENTATION |
| `reports/owner/CORRECT_SCORE_ODDS_PROVIDER_CAPABILITY_AUDIT.md` | DOCUMENTATION |
| `reports/owner/CORRECT_SCORE_ODDS_INGESTION_REPORT.md` | DOCUMENTATION |
| `reports/owner/CORRECT_SCORE_ODDS_INGESTION_REPORT_FA.md` | DOCUMENTATION |
| `reports/owner/TWO_FIXTURE_EXACT_SCORE_PORTFOLIO_RESEARCH.md` | DOCUMENTATION |
| `reports/owner/TWO_FIXTURE_EXACT_SCORE_PORTFOLIO_RESEARCH_FA.md` | DOCUMENTATION |
| `reports/owner/TWO_FIXTURE_PORTFOLIO_REAL_ODDS_RESEARCH.md` | DOCUMENTATION |
| `reports/owner/TWO_FIXTURE_PORTFOLIO_REAL_ODDS_RESEARCH_FA.md` | DOCUMENTATION |

### EXCLUDED (do not stage)

| Path / pattern | Class | Reason |
|---|---|---|
| `artifacts/**` | RUNTIME_DATA | gitignored |
| `reports/owner/portfolio/daily/**` | REPORT | generated daily runtime |
| `data/shadow/**` | RUNTIME_DATA | unrelated / runtime |
| `data/validation/**` | RUNTIME_DATA | unrelated |
| `PHASE_3_2A_*.md`, `PHASE_3_2B_*.md` | UNRELATED | not TFPS |
| `scripts/_prod_*`, `scripts/_probe_*`, odds_map, ecse_top5 research scripts | UNRELATED | out of scope for this commit |
| `worldcup_predictor/research/odds_map_full_profile/` | UNRELATED | separate research |
| `*.db`, `.env*`, credentials | SECRET/DATABASE | forbidden |
| API_FOOTBALL_*, FORWARD_EVALUATION_*, ODDS_MAP_* root docs | UNRELATED | not TFPS |

## Notes

- Sample unit remains **ONE EXECUTABLE TWO-FIXTURE PORTFOLIO** (not CS line count).
- Timer templates keep Install disabled.
- No betting execution path.
- Strategy version remains `tfps-v1`; Cohort A unlocked only by completed count.
