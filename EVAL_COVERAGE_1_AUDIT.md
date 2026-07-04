# EVAL-COVERAGE-1 — Evaluation Coverage Audit (Before)

Phase: **EVAL-COVERAGE-1** | Audited: **2026-07-04 00:24:51 UTC**

## Coverage Table

| Category | Count | Data Source | Newest Timestamp | Notes |
|----------|------:|-------------|------------------|-------|
| Total fixtures (all competitions) | 2161 | fixtures | 2026-07-04T00:00:15.503756 | is_placeholder=0 |
| Total WC 2026 fixtures | 329 | fixtures | 2026-07-04T00:00:15.503756 | competition_key=world_cup_2026 |
| Finished fixtures (all competitions) | 2149 | fixtures | 2026-07-04T00:00:15.503756 | status in ('FT', 'AET', 'PEN') |
| Finished WC fixtures | 317 | fixtures | 2026-07-04T00:00:15.503756 | status in ('FT', 'AET', 'PEN') |
| Finished WC with real result (90' goals) | 317 | fixtures + fixture_results | 2026-06-29T11:02:01.570855 | home_goals/away_goals NOT NULL |
| Finished WC without real result | 0 | fixtures LEFT JOIN fixture_results | — | finished status but missing fixture_results goals |
| Finished WC with WDE stored prediction | 33 | worldcup_stored_predictions | — |  |
| Finished WC with ECSE snapshot | 0 | ecse_prediction_snapshots | — |  |
| Finished WC with any stored prediction | 33 | worldcup_stored_predictions / ecse_prediction_snapshots | — | WDE and/or ECSE |
| Finished WC with prediction but no WDE evaluation | 0 | worldcup_stored_predictions LEFT JOIN worldcup_prediction_evaluations | — | pending WDE eval |
| Finished WC with ECSE+result but no ECSE evaluation | 0 | ecse_prediction_snapshots LEFT JOIN ecse_prediction_evaluations | — | pending ECSE eval |
| Finished WC with prediction but no any evaluation | 0 | combined | — | missing both WDE and ECSE eval rows |
| WDE stored predictions pending evaluation | 0 | worldcup_stored_predictions | — | finished + stored + no worldcup_prediction_evaluations row |
| ECSE snapshots pending evaluation | 0 | ecse_prediction_snapshots | — | finished + result + no ecse_prediction_evaluations row |
| WDE evaluations (WC) | 34 | worldcup_prediction_evaluations | 2026-07-02T16:43:50.202696 |  |
| ECSE evaluations (all) | 0 | ecse_prediction_evaluations | — |  |
| Evaluated WDE+ECSE WC knockout (both eval rows) | 0 | combined | — | research knockout sample (dual-eval) |
| Evaluated WDE+ECSE WC all stages (both eval rows) | 0 | combined | — | dual-eval finished WC |
| ECSE research sample (finished+result+snapshot) | 0 | ecse_prediction_snapshots + fixture_results | — | used by shadow optimizers (actual_90min required) |

## Summary

- Finished WC fixtures: **317**
- Finished with 90' result: **317**
- ECSE research sample (finished+snapshot+result): **0**
- ECSE pending evaluation: **0**
- WDE pending evaluation: **0**


---

# EVAL-COVERAGE-1 — Evaluation Coverage Audit (After)

Phase: **EVAL-COVERAGE-1** | Audited: **2026-07-04 00:24:53 UTC**

## Coverage Table

| Category | Count | Data Source | Newest Timestamp | Notes |
|----------|------:|-------------|------------------|-------|
| Total fixtures (all competitions) | 2161 | fixtures | 2026-07-04T00:00:15.503756 | is_placeholder=0 |
| Total WC 2026 fixtures | 329 | fixtures | 2026-07-04T00:00:15.503756 | competition_key=world_cup_2026 |
| Finished fixtures (all competitions) | 2149 | fixtures | 2026-07-04T00:00:15.503756 | status in ('FT', 'AET', 'PEN') |
| Finished WC fixtures | 317 | fixtures | 2026-07-04T00:00:15.503756 | status in ('FT', 'AET', 'PEN') |
| Finished WC with real result (90' goals) | 317 | fixtures + fixture_results | 2026-06-29T11:02:01.570855 | home_goals/away_goals NOT NULL |
| Finished WC without real result | 0 | fixtures LEFT JOIN fixture_results | — | finished status but missing fixture_results goals |
| Finished WC with WDE stored prediction | 33 | worldcup_stored_predictions | — |  |
| Finished WC with ECSE snapshot | 0 | ecse_prediction_snapshots | — |  |
| Finished WC with any stored prediction | 33 | worldcup_stored_predictions / ecse_prediction_snapshots | — | WDE and/or ECSE |
| Finished WC with prediction but no WDE evaluation | 0 | worldcup_stored_predictions LEFT JOIN worldcup_prediction_evaluations | — | pending WDE eval |
| Finished WC with ECSE+result but no ECSE evaluation | 0 | ecse_prediction_snapshots LEFT JOIN ecse_prediction_evaluations | — | pending ECSE eval |
| Finished WC with prediction but no any evaluation | 0 | combined | — | missing both WDE and ECSE eval rows |
| WDE stored predictions pending evaluation | 0 | worldcup_stored_predictions | — | finished + stored + no worldcup_prediction_evaluations row |
| ECSE snapshots pending evaluation | 0 | ecse_prediction_snapshots | — | finished + result + no ecse_prediction_evaluations row |
| WDE evaluations (WC) | 34 | worldcup_prediction_evaluations | 2026-07-02T16:43:50.202696 |  |
| ECSE evaluations (all) | 0 | ecse_prediction_evaluations | — |  |
| Evaluated WDE+ECSE WC knockout (both eval rows) | 0 | combined | — | research knockout sample (dual-eval) |
| Evaluated WDE+ECSE WC all stages (both eval rows) | 0 | combined | — | dual-eval finished WC |
| ECSE research sample (finished+result+snapshot) | 0 | ecse_prediction_snapshots + fixture_results | — | used by shadow optimizers (actual_90min required) |

## Summary

- Finished WC fixtures: **317**
- Finished with 90' result: **317**
- ECSE research sample (finished+snapshot+result): **0**
- ECSE pending evaluation: **0**
- WDE pending evaluation: **0**
