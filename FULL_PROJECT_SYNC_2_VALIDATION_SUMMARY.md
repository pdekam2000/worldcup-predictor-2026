# FULL-PROJECT-SYNC-2 — Validation Summary

**Environment:** Local PC · `APP_ENV=local` · pre-commit

## compileall

| Scope | Result |
|-------|--------|
| `worldcup_predictor/` | pass |
| `scripts/` (full) | **pre-existing fail** — `scripts/audit_specialists_server.py` SyntaxError (not introduced by this sync) |
| New modules spot-check | pass |

## Validator suite

| Script | Exit | Classification |
|--------|------|----------------|
| validate_claude_ops_1_access_and_prediction_inspection.py | 0 | pass |
| validate_owner_predictions_ui_2_end_result_display.py | 1 | **non-blocking** — 29/31; local missing production freshness backend |
| validate_ecse_rerank_1_shadow_layer.py | 0 | pass |
| validate_top3_endresult_optimizer_1.py | 0 | pass |
| validate_top10_coverage_1.py | 0 | pass |
| validate_top10_to_top3_selector_1.py | 0 | pass |
| validate_eval_coverage_1.py | 0 | pass |
| validate_odds_freshness_1.py | 0 | pass |
| validate_odds_timestamp_normalization_1.py | 0 | pass |
| validate_fixture_sync_1.py | 1 | **environment-dependent** — systemctl/nginx checks on Windows |
| validate_controlled_knockout_predictions_2.py | 1 | **environment-dependent** — requires production DB state |
| validate_controlled_knockout_predictions_3.py | — | **missing script** (phase not created) |

## Frontend

| Step | Result |
|------|--------|
| `npm run build` (base44-d) | **pass** (exit 0) |

## Verdict

No **blocking** failures in new consolidated source. Production-only validators scheduled post-pull on Hetzner.

**Proceed** with commit/push/deploy.
