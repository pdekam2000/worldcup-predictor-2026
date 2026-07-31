# BETTING_DAY_SIMILARITY_ENGINE_REPORT

**Status:** `BETTING_DAY_SIMILARITY_ENGINE_HOLD`  
**Recommendation:** `SIMILARITY_OVERLAY_HOLD`  
**Baseline commit:** `aa2af6a`  
**Deployment:** NOT DEPLOYED

## Pipeline position

Coverage → Insurance → **Betting Day Similarity Engine** → Portfolio Manager → Tickets → Forward Shadow

## Holdout policy comparison

- Always Bet ROI: `0.38556604`
- Baseline Portfolio ROI: `0.29096154`
- Calibrated candidate ROI: `0.29096154`
- Similarity overlay ROI: `0.20094787`
- Always Bet max DD: `4.33`
- Baseline max DD: `4.0`
- Overlay max DD: `2.175`

## Similarity lock

- Method: `cosine`
- K: `10`
- Regimes: `3`
- OOD days: `75`
- Features: `72`
- Historical days: `488`

## Leakage validation

- Passed: `True`

## Regime profiles (training)

```json
[
  {
    "regime_id": 0,
    "size": 106,
    "top_drivers": [
      {
        "feature": "pct_tier_lower",
        "centroid": -1.039736,
        "delta_vs_mean": -1.039736
      },
      {
        "feature": "pct_tier_b",
        "centroid": 1.018123,
        "delta_vs_mean": 1.018123
      },
      {
        "feature": "pct_model_conflict",
        "centroid": -0.969171,
        "delta_vs_mean": -0.969171
      },
      {
        "feature": "avg_top5_mass",
        "centroid": 0.902246,
        "delta_vs_mean": 0.902246
      },
      {
        "feature": "avg_wde_confidence",
        "centroid": 0.902246,
        "delta_vs_mean": 0.902246
      },
      {
        "feature": "median_wde_confidence",
        "centroid": 0.902172,
        "delta_vs_mean": 0.902172
      }
    ],
    "descriptive_tags": [
      "elevated_confidence",
      "concentrated_leagues"
    ]
  },
  {
    "regime_id": 1,
    "size": 34,
    "top_drivers": [
      {
        "feature": "n_leagues",
        "centroid": 2.754675,
        "delta_vs_mean": 2.754675
      },
      {
        "feature": "n_countries",
        "centroid": 2.754675,
        "delta_vs_mean": 2.754675
      },
      {
        "feature": "coupon_diversification_score",
        "centroid": 2.743301,
        "delta_vs_mean": 2.743301
      },
      {
        "feature": "coupon_overlap_score",
        "centroid": -2.743301,
        "delta_vs_mean": -2.743301
      },
      {
        "feature": "league_concentration",
        "centroid": -2.743301,
        "delta_vs_mean": -2.743301
      },
      {
        "feature": "max_league_share",
        "centroid": -2.671019,
        "delta_vs_mean": -2.671019
      }
    ],
    "descriptive_tags": [
      "elevated_confidence",
      "dense_volume"
    ]
  },
  {
    "regime_id": 2,
    "size": 152,
    "top_drivers": [
      {
        "feature": "pct_tier_lower",
        "centroid": 0.781648,
        "delta_vs_mean": 0.781648
      },
      {
        "feature": "pct_tier_b",
        "centroid": -0.760911,
        "delta_vs_mean": -0.760911
      },
      {
        "feature": "pct_model_conflict",
        "centroid": 0.739816,
        "delta_vs_mean": 0.739816
      },
      {
        "feature": "max_wde_confidence",
        "centroid": -0.68989,
        "delta_vs_mean": -0.68989
      },
      {
        "feature": "avg_wde_confidence",
        "centroid": -0.678335,
        "delta_vs_mean": -0.678335
      },
      {
        "feature": "avg_top5_mass",
        "centroid": -0.678335,
        "delta_vs_mean": -0.678335
      }
    ],
    "descriptive_tags": [
      "elevated_entropy",
      "concentrated_leagues",
      "sparse_volume"
    ]
  }
]
```

## Guardrails

- Passed: `['overlay_dd_le_baseline', 'overlay_exposure_controlled', 'strong_dd_below_always', 'alt_meaningful_dd_reduction']`
- Failed: `['overlay_roi_ge_baseline', 'strong_roi_ge_always', 'alt_roi_approx_unchanged']`

## Limitations

- Day features use research proxies where country/draw-odds/freshness are incomplete.
- Similarity does not predict match results.
- Overlay cannot change football predictions, markets, or freezes.
- Baseline PM and calibrated candidate remain immutable.

**NOT DEPLOYED**
