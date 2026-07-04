# ECSE-RERANK-1 — UI Recommendation (Advisory Only)

No UI implemented in this phase. Recommended display rules based on shadow evaluation.

## Public / Normal Display

1. Show **Top 3** as: **"Most likely score candidates"**
2. Do **not** label Top 1 as a guaranteed exact score
3. Add disclaimer: *"Exact score is high variance. Top candidates are ranked by model likelihood."*
4. Primary call-to-action remains **WDE 1X2** (strongest market in knockout sample)

## Owner / Pro Display

1. Show **Top 5** score candidates (expandable from Top 3)
2. Consistency notes per match:
   - BTTS aligned / misaligned with WDE
   - O/U 2.5 aligned / misaligned with WDE
   - Odds fresh / stale / unknown
   - AET/PEN risk flag when fixture is knockout and draw-prone
3. If `REQUIRES_FRESH_ODDS`: show advisory badge, do not treat re-rank as high confidence

## Suggested Card Layout

```
┌─────────────────────────────────────┐
│ Main Pick: WDE 1X2 (Home / Draw / Away) │
│ Confidence: [WDE score]                   │
├─────────────────────────────────────┤
│ Score Candidates (Top 3)                │
│  1. 2-1   2. 1-0   3. 2-0              │
│  "Most likely score candidates"         │
├─────────────────────────────────────┤
│ [Expand] Top 5 + consistency notes      │
└─────────────────────────────────────┘
```

## Promotion Path (not executed)

| Option | When |
|--------|------|
| KEEP_SHADOW_ONLY | Default until 30–50 finished matches |
| PROMOTE_UI_TOP3_ONLY | Low risk UX change — label + Top 3 framing |
| PROMOTE_RERANK_TO_OWNER_PREVIEW | After more data + fresh odds pipeline |
| DO_NOT_PROMOTE | If shadow adds no value on holdout |

Current recommendation: **PROMOTE_UI_TOP3_ONLY** for UX honesty; keep re-rank in shadow until more data.
