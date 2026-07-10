# BIG5 Runtime Policy State Matrix

**Generated:** 2026-07-10  
**Anchor date:** 2026-07-10  
**Canonical commit:** `5999a65afe8175f322dd57f2077ece70d6735711`

| Competition | Provider ID | Tier | Display Status | Owner Visible | Production Visible | Shadow Visible | prediction_allowed | forward_evaluation_enabled | Automation Discovery | Result Sync |
|-------------|--------------:|------|----------------|---------------|--------------------|----------------|--------------------|-----------------------------|----------------------|-------------|
| Premier League (`premier_league`) | 39 | A | TRUSTED | yes | yes | no | yes (odds-gated) | yes | yes | yes |
| Bundesliga (`bundesliga`) | 78 | A | TRUSTED | yes | yes | no | yes (odds-gated) | yes | yes | yes |
| Serie A (`serie_a`) | 135 | B | TEST_PHASE | yes | no | yes | yes (odds-gated) | yes | yes | yes |
| La Liga (`la_liga`) | 140 | B | TEST_PHASE | yes | no | yes | yes (odds-gated) | yes | yes | yes |
| Ligue 1 (`ligue_1`) | 61 | B | TEST_PHASE | yes | no | yes | yes (odds-gated) | yes | yes | yes |

## Metadata per league

| Key | prediction_mode | validation_tier | public Trusted |
|-----|-----------------|-----------------|----------------|
| premier_league | TIER_A_PRODUCTION | A | true |
| bundesliga | TIER_A_PRODUCTION | A | true |
| serie_a | TIER_B_OWNER_SHADOW | B | false |
| la_liga | TIER_B_OWNER_SHADOW | B | false |
| ligue_1 | TIER_B_OWNER_SHADOW | B | false |

## Policy verdict

All five leagues match required expected state. Premier League and Bundesliga remain Tier A TRUSTED in production scope. Serie A, La Liga, and Ligue 1 remain Tier B TEST_PHASE in owner/shadow scope only.

**Status:** POLICY_MATRIX_PASS
