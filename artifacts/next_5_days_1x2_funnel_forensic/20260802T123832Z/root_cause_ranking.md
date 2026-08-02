# Root cause ranking

Recommendation: **FUNNEL_MIXED_ROOT_CAUSES**

## 890 vs 93

Owner ~890 most closely matches the worldwide/provider football fixture volume (raw=1070, unsupported+friendly=911) NOT the owner Tier A/B prediction universe (93).

## Causes

### 1. discovery_universe_intentionally_narrow_vs_worldwide
- Affected: 911 (exclusive≈911)
- Severity: HIGH · Confidence: 0.95
- Type: EXPECTED_POLICY
- Action: Document that ~890–1070 worldwide/provider fixtures are not the prediction universe; owner Tier A/B allowlist yields 93.

### 2. no_bet_hard_exclusion_dominates_post_agreement
- Affected: 76 (exclusive≈25)
- Severity: HIGH · Confidence: 0.93
- Type: EXPECTED_POLICY_POSSIBLY_OVERSTRICT
- Action: Keep production no_bet; research Policy F for advisory mode. Audit CONFIDENCE_BELOW_60 dominance.

### 3. dna_unweighted_top5_sole_dissent_blocks_partial_to_final
- Affected: 16 (exclusive≈16)
- Severity: HIGH · Confidence: 0.9
- Type: DIRECTION_INFERENCE_DEFECT_OR_OVERSTRICT
- Action: Prefer DNA winner_distribution when present; treat DNA/Twins as advisory (Policy G) after historical validation.

### 4. strict_agreement_requires_extras_alignment
- Affected: 52 (exclusive≈36)
- Severity: MEDIUM · Confidence: 0.85
- Type: EXPECTED_POLICY
- Action: Counterfactual core-model agreement (Policy D/G) before any production change.

### 5. legitimate_scarcity_among_no_bet_false
- Affected: 2 (exclusive≈1)
- Severity: MEDIUM · Confidence: 0.8
- Type: EXPECTED
- Action: Only 2 fixtures have no_bet=false; after DNA gate, 1 remains — scarcity is real inside curated+canonical gates.

### 6. missing_output_denominator
- Affected: 15 (exclusive≈15)
- Severity: LOW · Confidence: 0.75
- Type: EXPECTED_TECHNICAL
- Action: Keep missing ≠ disagreement; blocked/incomplete already separated.

### 7. reporting_aggregation_bug
- Affected: 1 (exclusive≈1)
- Severity: LOW · Confidence: 0.85
- Type: MINOR_REPORTING_DEFECT
- Action: Deduplicate discovered_universe by fixture_id across days; document Vienna date-boundary duplicates (1498692).

### 8. selection_undercount_of_final_1x2
- Affected: 0 (exclusive≈0)
- Severity: LOW · Confidence: 0.9
- Type: NOT_FOUND
- Action: None — baseline reproduces 1 final 1X2 (Djurgården).

## Counterfactual candidate counts
- A_baseline: 1
- B_available_unanimity: 1
- C_supermajority_80: 2
- D_core_plus_market: 2
- E_weighted_proxy: 2
- F_no_bet_advisory: 26
- G_partial_one_lowinfo: 2
- G_plus_F_partial_one_lowinfo_no_bet_advisory: 41
- F_no_bet_advisory_conf_ge_60: 10
- G_plus_F_conf_ge_60: 13