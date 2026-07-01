# ECSE-X2-M7 - Controlled Shadow-Live Enablement Report

**Recommendation:** **READY_FOR_ADMIN_UI_REVIEW**  

## Part A - Pre-enable backup

- Backup manifest: `artifacts/ecse_x2_m7_backups/20260629T190946Z/manifest.json`
- Git commit: `d143e98f20960e75235a95491f450fb05f101b55`
- Before snapshot: `artifacts/ecse_x2_m7_before_enable_public_output_snapshot.json`

## Part B — Flag enablement

- `ECSE_X2_M6_SHADOW_LIVE_ENABLED`: **1**
- Flag active in settings: **True**
- Env snippet: `deployment/ecse_x2_m7_enablement_snippet.env`

## Part C — Service restart

- Attempted: **True**
- Success: **False**
- Note: Sudo ist auf diesem Computer deaktiviert. Um sie zu aktivieren, wechseln Sie zu ]8;;ms-settings:developers\Developer Settings page]8;;\ in der App "Einstellungen"

## Public output comparison

- Compared fixtures: **8**
- Unchanged: **8**
- Changed: **0**
- Public output unchanged: **True**

## Part D — Live collection

- total_rows: **108**
- applied: **24**
- excluded: **84**
- strong_home_prob_ge_60: **20**
- balanced_excluded: **3**
- missing_odds: **75**
- pending_evaluation: **108**
- duplicate_row_keys: **0**
- exclusion_reasons: `{"home_prob_below_55": 6, "missing_ft_home": 75, "balanced_match": 3}`

## Part E — Evaluation watch

- Evaluations: **21**
- top1: {'baseline_pct': 9.5238, 'enhanced_pct': 14.2857, 'delta_pp': 4.7619}
- top3: {'baseline_pct': 19.0476, 'enhanced_pct': 19.0476, 'delta_pp': 0.0}
- top5: {'baseline_pct': 33.3333, 'enhanced_pct': 28.5714, 'delta_pp': -4.7619}
- top10: {'baseline_pct': 57.1429, 'enhanced_pct': 57.1429, 'delta_pp': 0.0}

## Part F — Admin endpoints

- unauthenticated_401: PASS
- non_super_admin_403: PASS
- summary_200: PASS
- list_200: PASS
- detail_200: PASS
- no_public_shadow_route: PASS

## Part G — Validation

- Passed: **True**
- Details: `ECSE-X2-M7 validation

  [PASS] flag_active
  [PASS] enablement_proof_exists
  [PASS] proof_flag_value
  [PASS] before_snapshot_exists
  [PASS] after_snapshot_exists
  [PASS] public_output_unchanged — changed=0
  [PASS] membership_unchanged
  [PASS] public_output_false
  [PASS] no_nan
  [PASS] shadow_artifact_exists — rows check below
  [PASS] shadow_rows_present — n=108
  [PASS] public_output_changed_all_false
  [PASS] no_duplicate_keys — dup=0
  [PASS] eval_separate_artifact — n=21
  [PASS] baseline_unchanged — rows=10935145
  [PASS] predictions_no_m7_leak
  [PASS] admin_unauth_401
  [PASS] admin_non_super_403
  [PASS] admin_super_200
  [PASS] report_exists
  [PASS] watch_summary_exists
  [PASS] recommendation_enum — READY_FOR_ADMIN_UI_REVIEW

22/22 checks passed
`

## Rollback

```bash
# Set in production .env:
ECSE_X2_M6_SHADOW_LIVE_ENABLED=0
sudo systemctl restart worldcup-api
```

Restore artifacts from: `artifacts/ecse_x2_m7_backups/20260629T190946Z`
