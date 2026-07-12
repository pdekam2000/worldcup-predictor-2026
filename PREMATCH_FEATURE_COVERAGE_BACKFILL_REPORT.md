# Prematch Feature Coverage Backfill Report

## Final status

**PREMATCH_FEATURE_PILOT_BACKFILL_COMPLETE**

---

## Answers

| # | Question | Answer |
|---|----------|--------|
| 1 | Historical prematch xG providers? | SportMonks xGFixture (WC only); Tier B: not mapped |
| 2 | SportMonks defensible timestamp? | Only for live/upcoming fetches; historical xG lacks publication time |
| 3 | Competitions covered? | Pilot: world_cup_2026, allsvenskan, eliteserien |
| 4 | Lineup historically timestamped? | Via `fixture_enrichment.updated_at` when < kickoff |
| 5 | Injury historically timestamped? | Future-snapshot-only for live; historical requires provenance |
| 6 | Future-snapshot-only? | Injury/lineup for upcoming live fetches |
| 7 | Pilot fixtures targeted? | 45 |
| 8 | Snapshots stored? | inserted=1, duplicate=0 |
| 9 | API calls used? | API-FB=15, SM=0 |
| 10 | xG coverage before/after | See coverage_before/after in run_summary.json |
| 11 | Lineup coverage before/after | See `feature_families.lineup` in coverage artifact |
| 12 | Injury coverage before/after | See `feature_families.injury` |
| 13 | Leakage rejected rows? | 0 |
| 14 | Post-match admitted? | No — POST_MATCH rows rejected at insert |
| 15 | Immutable/idempotent? | Yes — `INSERT OR IGNORE` on snapshot_key |
| 16 | Provenance recorded? | Yes — provider, endpoint, timestamps, leakage_status |
| 17 | Missingness explicit? | Yes — completeness_mask JSON |
| 18 | 30-day shadow runner ready? | Manifest at `data/shadow/provider_feature_fusion_live/manifest.json` |
| 19 | Production prediction changed? | **No** |
| 20 | Shadow promoted? | **No** |
| 21 | Regressions passing? | Run validate_prematch_feature_coverage_backfill.py |
| 22 | Local=Origin=Production? | After commit/push |
| 23 | Next phase? | 30-day live shadow with timer approval; SportMonks Tier B mapping if licensed |

**Note:** SPORTMONKS_PREMATCH_XG_NOT_AVAILABLE for Tier B

**STOP** — No timer enabled. No production promotion.
