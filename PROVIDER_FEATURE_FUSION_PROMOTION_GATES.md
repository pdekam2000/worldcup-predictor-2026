# Provider Feature Fusion Promotion Gates

**No promotion in this phase.** Design-only criteria:

1. Chronological holdout improvement ≥ +0.5% accuracy on 1X2 with n ≥ 5,000
2. No material calibration regression (Δ calibration_error ≤ +0.01)
3. Improvement in ≥ 2 competition groups on holdout
4. Stable Tier A behavior (production scope fixtures)
5. Tier B remains owner_shadow / non-public
6. No unresolved leakage flags
7. Missing-data behavior stable (no provider/competition bias from imputation)
8. Shadow evaluation period ≥ 30 days live shadow
9. Rollback path documented and tested
10. API cost justified vs measured lift

**Current status:** Gates not met for xG/lineup/pressure families due to coverage gaps.
