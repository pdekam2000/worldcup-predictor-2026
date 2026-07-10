# Phase 7B Selective Port Matrix

Audit date: 2026-07-10  
Source workspace: `C:\Users\kaman\Desktop\Footbal` (forensic only)  
Target workspace: `C:\Users\kaman\Desktop\worldcup-predictor-source-recovery` (canonical)

| File | Classification | Notes |
|------|----------------|-------|
| `worldcup_predictor/forward_evaluation/__init__.py` | PORT_AS_IS | Module bootstrap |
| `worldcup_predictor/forward_evaluation/constants.py` | PORT_WITH_TIER_A_COMPLETION | Renamed phase to UNIFIED-FORWARD-EVAL-A-B |
| `worldcup_predictor/forward_evaluation/db.py` | PORT_WITH_TIER_A_COMPLETION | Added validation_tier, display_status, competition_family, domain_type, validation_note migrations |
| `worldcup_predictor/forward_evaluation/discovery.py` | PORT_WITH_TIER_A_COMPLETION | Unified fixture model + broad listing hook |
| `worldcup_predictor/forward_evaluation/gates.py` | PORT_AS_IS | Tier A+B gates via owner scope |
| `worldcup_predictor/forward_evaluation/freeze.py` | PORT_WITH_TIER_A_COMPLETION | Stores unified metadata fields |
| `worldcup_predictor/forward_evaluation/results.py` | PORT_AS_IS | Regulation score sync |
| `worldcup_predictor/forward_evaluation/evaluate.py` | PORT_AS_IS | Market + rank evaluation |
| `worldcup_predictor/forward_evaluation/context.py` | PORT_AS_IS | Analysis buckets |
| `worldcup_predictor/forward_evaluation/batch.py` | PORT_AS_IS | Daily manifest |
| `worldcup_predictor/forward_evaluation/runner.py` | PORT_WITH_TIER_A_COMPLETION | A+B daily runner |
| `worldcup_predictor/forward_evaluation/weekly_report.py` | PORT_WITH_TIER_A_COMPLETION | A/B split sections |
| `worldcup_predictor/forward_evaluation/safety.py` | PORT_AS_IS | Read-only boundary |
| `worldcup_predictor/forward_evaluation/automation.py` | PORT_AS_IS | Timers disabled |
| `worldcup_predictor/forward_evaluation/fixture_model.py` | PORT_WITH_TIER_A_COMPLETION | **NEW** unified fixture model |
| `worldcup_predictor/forward_evaluation/lock.py` | PORT_AS_IS | **NEW** single-process lock |
| `worldcup_predictor/forward_evaluation/orchestrator.py` | PORT_WITH_TIER_A_COMPLETION | **NEW** unified automation cycle |
| `scripts/run_daily_forward_evaluation.py` | PORT_AS_IS | Daily runner CLI |
| `scripts/sync_forward_evaluation_results.py` | PORT_AS_IS | Result sync CLI |
| `scripts/generate_weekly_forward_evaluation_report.py` | PORT_AS_IS | Weekly report CLI |
| `scripts/query_forward_evaluation_summary.py` | PORT_WITH_TIER_A_COMPLETION | --tier, --compare-tiers, --competition-family |
| `scripts/run_forward_evaluation_automation_cycle.py` | PORT_WITH_TIER_A_COMPLETION | **NEW** orchestrator CLI |
| `scripts/validate_unified_forward_evaluation_canonicalization.py` | PORT_WITH_TIER_A_COMPLETION | **NEW** 75-check validator |
| `scripts/validate_phase7b_daily_auto_freeze_and_evaluation_db.py` | OBSOLETE | Superseded by unified validator |
| `scripts/run_phase7a_tier_b_forward_freeze_and_evaluation.py` | OBSOLETE | Phase 7A forensic only |
| `scripts/freeze_tier_b_forward_batch_20260712.py` | RUNTIME_ONLY_EXCLUDE | One-off batch |
| `scripts/evaluate_tier_b_forward_batch_20260712.py` | RUNTIME_ONLY_EXCLUDE | One-off batch |
| `worldcup_predictor/owner_predict_eval/tier_b_forward_eval.py` | OBSOLETE | Phase 7A forensic — not recurring authority |
| `data/evaluation/forward_prediction_tracking.db` | RUNTIME_ONLY_EXCLUDE | Never commit |
| `artifacts/daily_forward_evaluation/**` | RUNTIME_ONLY_EXCLUDE | Runtime manifests |
| `artifacts/tier_b_forward_eval_20260712/**` | RUNTIME_ONLY_EXCLUDE | Phase 7A forensic artifacts (preserve locally) |
| `worldcup_predictor/gpt_actions/owner_scope.py` | PORT_WITH_OWNER_FLOW_FIX | Display labels, trusted/test_phase scope aliases |
| `worldcup_predictor/gpt_actions/delegation.py` | PORT_WITH_OWNER_FLOW_FIX | Broad listing + unified labels |
| `worldcup_predictor/gpt_actions/worker.py` | PORT_WITH_OWNER_FLOW_FIX | Owner A+B default, combo warning |
| `worldcup_predictor/gpt_actions/app.py` | PORT_WITH_OWNER_FLOW_FIX | listTodayMatches endpoint |
| `worldcup_predictor/gpt_actions/schemas.py` | PORT_WITH_OWNER_FLOW_FIX | ListMatchesQuery |
| `worldcup_predictor/gpt_actions/policies.py` | PORT_WITH_OWNER_FLOW_FIX | Approved route for list |
| `deploy/systemd/worldcup-forward-evaluation-*.timer` | PORT_AS_IS | **NEW** templates, disabled |

## Excluded from port (by design)

- Evaluation SQLite DB bytes
- Cache, logs, secrets, provider output
- Phase 7A recurring automation authority
- Duplicate evaluators or schedulers
