# Halmstad vs Sirius — DNA direction case study

Fixture `1494232` · Vienna `2026-08-03 19:00 CEST`

## Mission directions

| Model | Direction |
|-------|-----------|
| WDE | away |
| ECSE | away |
| Exact V2 | away |
| Lambda V2 | away |
| DNA | draw |
| Twins | away |
| Market | away |

Agreement: **PARTIAL_AGREEMENT** · no_bet=False · quality=66.09 · research_class=WATCHLIST

## Why DNA blocked final 1X2

Production `classify_1x2_agreement` treats a single opposing extra model as `PARTIAL_AGREEMENT`.
Final 1X2 requires `UNANIMOUS_DIRECTION` or `STRONG_MULTI_MODEL_AGREEMENT`.
DNA=`draw` while all other models=`away` → excluded despite `no_bet=false` and strong confidence (71.5).

## DNA inference method

`dir_from_scores(top5)` with **equal weights** when probabilities are absent (typical for DNA Top5 labels).

## Readonly replay

```json
{
  "status": "OK",
  "fixture_id": 1494232,
  "top5": [
    "1-1",
    "0-1",
    "1-2",
    "0-0",
    "1-0"
  ],
  "unweighted_dir_from_scores": "draw",
  "unweighted_mass": {
    "home": 1.0,
    "draw": 2.0,
    "away": 2.0
  },
  "rank_weighted_dir": "draw",
  "rank_weighted_mass": {
    "home": 1.0,
    "draw": 7.0,
    "away": 7.0
  },
  "winner_distribution": null,
  "dir_from_winner_distribution": null,
  "engine_errors": [],
  "probabilities_in_top5": false,
  "tie_between_draw_and_away": true,
  "tie_break_behavior": "max(mass.items()) returns first key among ties in insertion order (home, draw, away) — so draw beats away on equal counts",
  "conclusion": "Mission used unweighted Top5 score-count inference. Halmstad Top5=['1-1','0-1','1-2','0-0','1-0'] → mass draw=2, away=2, home=1. Inferred DNA=draw is a TIE ARTIFACT (draw preferred over away on equal unweighted counts), not a robust full-distribution dissent. Winner_distribution was null in this replay."
}
```

## Robustness

- Unweighted Top5 for Halmstad: **draw=2, away=2, home=1** — inferred `draw` is a **tie artifact** (`max` prefers `draw` before `away` on equal mass).
- Rank-weighted Top5 also ties draw=away=7.
- `winner_distribution` was null in readonly replay — no full-distribution rescue available from DNA artifact.
- This is a **direction-inference defect**, not robust opposition to away.

## Audit classification

`DIRECTION_INFERENCE_DEFECT` / `POSSIBLE_FALSE_NEGATIVE` under Policy G (core+lambda+market align; one low-info model opposes via tie-break).
