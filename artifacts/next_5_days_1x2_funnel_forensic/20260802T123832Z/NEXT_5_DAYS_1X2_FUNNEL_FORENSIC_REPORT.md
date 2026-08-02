# NEXT_5_DAYS_1X2_FUNNEL_FORENSIC_REPORT

Status: **NEXT_5_DAYS_1X2_FUNNEL_FORENSIC_COMPLETE**

## Verdict

**FUNNEL_MIXED_ROOT_CAUSES**

Primary bottlenecks: (1) owner Tier A/B discovery vs worldwide ~890–1070 fixtures → 93 candidates; (2) Canonical `no_bet=true` hard-excludes 25/26 unanimous fixtures; (3) DNA unweighted Top5 sole-dissent creates 16 PARTIAL_AGREEMENT cases including Halmstad (no_bet=false).

## 890 vs 93

Owner ~890 most closely matches the worldwide/provider football fixture volume (raw=1070, unsupported+friendly=911) NOT the owner Tier A/B prediction universe (93).

- Provider raw (5d sum): **1070**
- Unsupported+friendly: **911**
- Owner prediction candidates: **93**

## Stage funnel

| Stage | Name | In | Out | Removed | % | Reason |
|-------|------|----|-----|---------|---|--------|
| F0 | raw_provider_rows | 1070 | 1004 | 66 | 6.17% | deduplicate_provider_rows |
| F1 | deduplicated_fixtures | 1004 | 1004 | 0 | 0.0% | prematch_status_filter |
| F2 | inside_target_vienna_dates | 1004 | 1004 | 0 | 0.0% | already_date_scoped_at_fetch |
| F3 | football_fixture_validity | 1004 | 93 | 911 | 90.74% | tier_a_b_allowlist_vs_unsupported_friendly |
| F4 | supported_competition | 93 | 93 | 0 | 0.0% | owner_tier_a_plus_tier_b |
| F5 | owner_scope | 93 | 92 | 0 | 0.0% | mission_discovered_equals_prediction_candidates |
| F6 | valid_identity_non_duplicate | 92 | 92 | 0 | 0.0% | no_additional_dedupe_in_mission |
| F7 | prematch_status | 92 | 92 | 0 | 0.0% | discovery_already_prematch |
| F8 | legitimate_fresh_odds | 77 | 77 | 0 | 0.0% | fresh_1x2_required |
| F9 | canonical_prediction_complete | 92 | 77 | 15 | 16.3% | prediction_incomplete_or_blocked |
| F10 | immutable_freeze_valid | 77 | 77 | 0 | 0.0% | missing_freeze_id |
| F11 | required_shadow_outputs_available | 77 | 77 | 0 | 0.0% | core_wde_ecse_exact_or_freshness |
| F12 | direction_inference_valid_every_core_model | 77 | 77 | 0 | 0.0% | core_direction_missing |
| F13 | no_severe_forensic_contradiction | 77 | 77 | 0 | 0.0% | forensic_severe |
| F14 | no_severe_direction_conflict | 77 | 42 | 35 | 45.45% | multi_model_direction_conflict |
| F15 | no_bet_false | 42 | 2 | 40 | 95.24% | canonical_no_bet_true_hard_exclude |
| F16 | agreement_status_eligible | 2 | 1 | 1 | 50.0% | requires_unanimous_or_strong |
| F17 | final_ranking_threshold | 1 | 1 | 0 | 0.0% | research_classification_gate |
| F18 | final_shortlist | 1 | 1 | 0 | 0.0% | top12_cap |

## Top exclusion gates (post-discovery)

1. `no_bet=true` among otherwise unanimous (25 exclusive)
2. DNA sole dissent → PARTIAL (16 fixtures)
3. DIRECTION_CONFLICT (36)
4. INSUFFICIENT / blocked incomplete (15)
5. Confidence < 60 among no_bet (majority of abstentions)

## no_bet

Distribution (inferred): {'NO_BET_TRUE_REASON_NOT_EXPOSED_IN_MISSION_ARTIFACT': 11, 'CONFIDENCE_BELOW_60': 64, 'DIRECTION_CONFLICT_OBSERVED': 35}

## Counterfactuals (research-only)

| Policy | Candidates |
|--------|------------|
| A baseline | 1 |
| B available unanimity | 1 |
| C 80% supermajority | 2 |
| D core+market | 2 |
| F no_bet advisory | 26 |
| G one-lowinfo OK | 2 |

Honest 10+ under validated alternative? **True** (requires owner approval + historical validation before any production change)

## Halmstad

DNA replay status: OK · unweighted=draw · winner_dist=None

## Safety

- NOT DEPLOYED
- CANONICAL UNCHANGED
- FREEZES UNCHANGED (snapshot sha 7da7ef31b014b1f0…)
- Gates not weakened
