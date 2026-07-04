# FIRST PRODUCTION END-RESULT EVIDENCE

**fixture_id:** 1567310  
**Match:** Colombia vs Ghana · Round of 32  
**Evaluation date:** 2026-07-04  
**Environment:** Hetzner production (`APP_ENV=production`)

---

## Fixture

**Colombia vs Ghana**

## Actual (90-minute)

**1-0** · FT · no AET · no penalties

Provider/production DB confirmed before evaluation write.

---

## Raw ECSE score candidates (frozen snapshot id=1)

| Rank | Score | vs actual 1-0 |
|------|-------|---------------|
| 1 | 2-0 | **MISS** |
| 2 | 1-0 | **HIT** |
| 3 | 3-0 | MISS |

## Tier outcomes

| Tier | Result |
|------|--------|
| Top3 | **HIT** (actual at rank 2) |
| Top5 | **HIT** (actual at rank 2) |

Full Top5 frozen list: 2-0, 1-0, 3-0, 4-0, 2-1

---

## WDE (90-minute)

| Market | Prediction | Result |
|--------|------------|--------|
| 1X2 | Colombia Home Win (57.3%) | **HIT** |
| BTTS | No | **HIT** |
| O/U 2.5 | Under | **HIT** |

---

## Prediction-time odds (frozen, not refreshed)

| Field | Value |
|-------|-------|
| Operational classification | STALE_ODDS |
| Documented age | 7.44h (knockout threshold 6h) |
| odds_snapshot_at | 2026-07-04 00:55:59 UTC |
| Payload at freeze | `ODDS_FRESHNESS_UNKNOWN` (unchanged — no historical rewrite) |

---

## Interpretation

This is the **first production ECSE evaluation**. Actual score **1-0** missed ECSE Top1 (2-0) but was captured at **rank 2** in frozen Top3 and Top5. All three WDE markets hit on the 90-minute result.

This single production fixture supports **continued evaluation** of Top3 score-candidate presentation. **One match is insufficient** for promotion, win-rate claims, or statistical proof. Do not infer that stale odds caused any hit or miss.

---

## ECSE evaluation record

- snapshot_id: 1
- top1_correct: 0
- top3_correct: 1
- top5_correct: 1
- rank_of_actual_score: 2
- evaluated_at: 2026-07-04 05:01:16 UTC
