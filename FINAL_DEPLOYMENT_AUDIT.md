# FINAL DEPLOYMENT AUDIT

**Release branch:** `release/football-strength-shadow-infra-20260730T151432Z`  
**Validated commit:** `537266d`  
**Parent (origin/main):** `a1962d1`  
**Audit date (UTC):** 2026-07-30

## Scope verdict

Release `537266d` contains **approved infrastructure + shadow research modules + tests/docs** only.  
It does **not** promote Lambda V2, Exact V2, or adaptive selector to canonical.

## Diff inventory (a1962d1..537266d)

| Area | Present? | Classification |
|------|----------|----------------|
| `migrations/research_football_strength_lambda_v2.sql` | Yes | Additive migration |
| `migrations/research_alternate_totals_capture_status.sql` | Yes | Additive migration |
| `worldcup_predictor/research/football_strength_foundation/*` | Yes | Infra / shadow runtime |
| `worldcup_predictor/research/infra_l2f_forward/*` | Yes | Infra / shadow runtime |
| `worldcup_predictor/research/lambda_team_strength/*` | Yes | Shared helpers (dependency) |
| `worldcup_predictor/research/ecse_live/odds_merge.py` | Yes | Additive O/U 4.5 field mapping only |
| `worldcup_predictor/research/ecse_live/prediction_builder.py` | Yes | Additive O/U 4.5 field mapping only |
| `tests/forward_evaluation/test_result_sync_and_market_evaluation.py` | Yes | Test harness fix only |
| `deployment/systemd/worldcup-forward-evaluation.timer` | Yes | Comment-only safety note |
| Research orchestrator scripts | Yes | Optional; not required for canonical |
| Docs / FINAL_* reports | Yes | Report only |

## Explicit unchanged confirmations

| Surface | Changed in release? | Evidence |
|---------|---------------------|----------|
| Canonical lambda generation (`extract_lambdas`) | **No** | Still uses O/U 1.5/2.5/3.5 only; O/U 4.5 ignored. Local proof: identical λ with/without 4.5 fields. |
| Canonical Exact Score engine | **No** | No ECSE exact-score engine files in release diff. |
| Canonical WDE | **No** | No WDE runtime modules in release diff. |
| Canonical BTTS | **No** | No BTTS rule changes in release diff. |
| Canonical O/U (2.5/3.5 used by λ) | **No** | O/U 4.5 mapping is additive capture only. |
| Canonical freeze serialization | **No** | No freeze service / schema mutation in release diff. |
| Canonical API responses | **No** | No `worldcup_predictor/api` changes in release diff. |
| GPT Actions public schema | **No** | No `worldcup_predictor/gpt_actions` changes in release diff. |
| Frontend contracts | **No** | No `base44-d` / frontend changes in release diff. |

## Additive odds mapping (only production-adjacent code change)

`odds_merge.py` / `prediction_builder.py` add:

- `ou_over_45_closing`
- `ou_under_45_closing`

Comments in-code state these are for alternate-totals shadow capture and are unused by `extract_lambdas`.

## Must remain shadow-only after deploy

- Lambda V2 families (L2-A..F)
- Exact V2
- Adaptive blend / selector
- Shadow orchestration outputs

## Local validation gate

- Command: `pytest tests/forward_evaluation tests/research/infra_l2f_forward tests/research/football_strength_foundation -q`
- Result: **113/113 PASS** at `537266d`

## Deploy decision

**APPROVED for infrastructure-only production deploy** once SSH/production access is available.  
No canonical model promotion in this release.
