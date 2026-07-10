# One-Week Forward Evidence Observation Plan

Date: 2026-07-10  
Period: 7 days from automation activation baseline  
Mode: **Observational only** — no model changes, no cadence changes, no auto-promotion

## Cadence (unchanged)

- Daily orchestrator: **07:00 and 17:00 Europe/Vienna**
- Weekly report: **Monday 08:00 Europe/Vienna**

## Daily counters to record

Use `scripts/forward_evaluation_automation_status.py` and `scripts/query_forward_evaluation_summary.py`.

| Metric | Source |
|--------|--------|
| discovered fixtures | automation cycle manifest / batch record |
| Tier A discovered | `tier_a_count` in discovery |
| Tier B discovered | `tier_b_count` in discovery |
| eligible fixtures | orchestrator `eligible_count` |
| frozen fixtures | `frozen_count` / eval DB delta |
| excluded fixtures | `excluded_count` |
| ODDS_MISSING | `excluded_candidates.exclusion_reason` |
| ODDS_STALE | excluded reason |
| DATA_QUALITY_BLOCKED | excluded reason |
| WDE_UNAVAILABLE | excluded reason |
| ECSE_UNAVAILABLE | excluded reason |
| MISSED_PREMATCH_FREEZE | post-kickoff without freeze |
| already frozen reuse | orchestrator `reused_frozen` |
| provider calls | owner odds budget / gate audit |
| cache hits | gate `allow_provider=False` path |
| new FT results | `actual_results` new rows |
| new evaluations | `evaluation_status=EVALUATED` delta |
| Top1/Top3/Top5 hits | `market_evaluations` |
| Rank 1–5 / OUTSIDE_TOP5 | `actual_score_rank` distribution |

## Weekly review (owner manual)

After 7 days, review:

- MISSED_PREMATCH_FREEZE rate vs cadence
- eligible-to-frozen conversion
- Tier A vs Tier B hit rates (`--compare-tiers`)
- Whether additional prematch windows are needed (**manual decision only**)

## Explicit exclusions

- No automatic cadence optimization
- No weight changes
- No Tier B promotion
- No retraining
