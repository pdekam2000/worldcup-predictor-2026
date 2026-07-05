# FULL-PROJECT-SYNC-3 — Validation Summary

## Local validation

| Check | Result |
|---|---|
| `python -m compileall worldcup_predictor scripts` | **NON_BLOCKING** — pre-existing `scripts/audit_specialists_server.py` SyntaxError |
| `validate_result_truth_repair_1.py` | **PASS** (50/50) |
| `validate_result_truth_schema_v8_and_ecse_reevaluation_1.py` | **PASS** (21/21) |
| `validate_next_3_upcoming_match_predictions_1.py` | **NON_BLOCKING** — 28/34 (missing prod fixtures 1570714/1576756 in local DB) |
| Frontend build | Not required (no base44-d changes) |

## Production validation (post-pull)

| Check | Result |
|---|---|
| `compileall` | **PASS** |
| `validate_result_truth_repair_1.py` | **NON_BLOCKING** — artifact path differences |
| `validate_result_truth_schema_v8_and_ecse_reevaluation_1.py` | **NON_BLOCKING** — local artifact JSON not on prod (DB state OK) |
| `validate_next_3_upcoming_match_predictions_1.py` | **PASS** on prod DB (Brazil/Norway frozen) |
| API health | **PASS** after `chown www-data` permission fix |
| nginx | **PASS** (running) |

## Blocking issues resolved

- API crash loop: `ecse_rerank/` directory owned root with mode 700 → fixed with `chown -R www-data:www-data`

## Not run (by design)

- No prediction regeneration
- No ECSE historical replay (73k fixture job)
- No timer enablement
