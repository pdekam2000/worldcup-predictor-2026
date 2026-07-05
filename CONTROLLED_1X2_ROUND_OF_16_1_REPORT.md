# CONTROLLED-1X2-ROUND-OF-16-1 — Report

**Started:** 2026-07-04 11:14:47 UTC
**Finished:** 2026-07-04 11:15:19 UTC
**Recommendation:** `ODDS_CONTEXT_INSUFFICIENT`

## Production commit

- HEAD: `282ef700f7bc31090f775f752f168d30e701ba24`
- Expected baseline: `b512e0bd600de12849dfaa0104ae643dff54afe0`

## Fixture discovery

{
  "entries": [
    {
      "key": "mexico_england",
      "home": "Mexico",
      "away": "England",
      "existing": true,
      "fixture_id": 1570714,
      "status": "already_in_db"
    },
    {
      "key": "portugal_spain",
      "home": "Portugal",
      "away": "Spain",
      "existing": true,
      "fixture_id": 1576756,
      "status": "already_in_db"
    },
    {
      "key": "argentina_egypt",
      "home": "Argentina",
      "away": "Egypt",
      "existing": false,
      "provider_fixture_id": 1576804,
      "home_team": "Argentina",
      "away_team": "Egypt",
      "kickoff_utc": "2026-07-07T16:00:00+00:00",
      "kickoff_vienna": "2026-07-07 18:00 CEST",
      "stage": "World Cup",
      "round": "Round of 16",
      "status": "found_in_provider",
      "provider_source": "api-football",
      "fixture_id": 1576804
    },
    {
      "key": "switzerland_colombia",
      "home": "Switzerland",
      "away": "Colombia",
      "existing": false,
      "provider_fixture_id": 1576805,
      "home_team": "Switzerland",
      "away_team": "Colombia",
      "kickoff_utc": "2026-07-07T20:00:00+00:00",
      "kickoff_vienna": "2026-07-07 22:00 CEST",
      "stage": "World Cup",
      "round": "Round of 16",
      "status": "found_in_provider",
      "provider_source": "api-football",
      "fixture_id": 1576805
    }
  ],
  "provider_calls_discovery": 1
}

## Missing fixture import

{
  "imports": [
    {
      "fixture_id": 1576804,
      "duplicate_check": {
        "by_provider_id_exists": false,
        "by_provider_id_row": null,
        "by_teams_kickoff_count": 0,
        "duplicate_risk": false
      },
      "outcome": "imported",
      "local_row": {
        "fixture_id": 1576804,
        "home_team": "Argentina",
        "away_team": "Egypt",
        "kickoff_utc": "2026-07-07T16:00:00",
        "status": "NS",
        "round_name": "Round of 16"
      }
    },
    {
      "fixture_id": 1576805,
      "duplicate_check": {
        "by_provider_id_exists": false,
        "by_provider_id_row": null,
        "by_teams_kickoff_count": 0,
        "duplicate_risk": false
      },
      "outcome": "imported",
      "local_row": {
        "fixture_id": 1576805,
        "home_team": "Switzerland",
        "away_team": "Colombia",
        "kickoff_utc": "2026-07-07T20:00:00",
        "status": "NS",
        "round_name": "Round of 16"
      }
    }
  ],
  "provider_calls_import": 3
}

## Odds audit (before / after)

### Before

[
  {
    "fixture_id": 1570714,
    "match": "Mexico vs England",
    "kickoff_vienna": "2026-07-06 02:00 CEST",
    "snapshot_at": "2026-07-04T11:08:34.166035",
    "age_hours": 0.1,
    "source": "live",
    "freshness_status": "UNKNOWN_ODDS",
    "policy_status": "FRESH_ODDS",
    "has_1x2_market": true
  },
  {
    "fixture_id": 1576756,
    "match": "Portugal vs Spain",
    "kickoff_vienna": "2026-07-06 21:00 CEST",
    "snapshot_at": "2026-07-04T11:08:55.951206",
    "age_hours": 0.1,
    "source": "live",
    "freshness_status": "UNKNOWN_ODDS",
    "policy_status": "FRESH_ODDS",
    "has_1x2_market": true
  },
  {
    "fixture_id": 1576804,
    "match": "Argentina vs Egypt",
    "kickoff_vienna": "2026-07-07 18:00 CEST",
    "snapshot_at": null,
    "age_hours": null,
    "source": null,
    "freshness_status": "UNKNOWN_ODDS",
    "policy_status": "ODDS_MISSING",
    "has_1x2_market": false
  },
  {
    "fixture_id": 1576805,
    "match": "Switzerland vs Colombia",
    "kickoff_vienna": "2026-07-07 22:00 CEST",
    "snapshot_at": null,
    "age_hours": null,
    "source": null,
    "freshness_status": "UNKNOWN_ODDS",
    "policy_status": "ODDS_MISSING",
    "has_1x2_market": false
  }
]

### Refresh

{
  "max_total_calls": 40,
  "calls_used": 0,
  "runs": [
    {
      "fixture_id": 1570714,
      "before": "UNKNOWN_ODDS",
      "dry_run_would_refresh": 0,
      "refreshed": 0,
      "provider_calls": {}
    },
    {
      "fixture_id": 1576756,
      "before": "UNKNOWN_ODDS",
      "dry_run_would_refresh": 0,
      "refreshed": 0,
      "provider_calls": {}
    },
    {
      "fixture_id": 1576804,
      "before": "UNKNOWN_ODDS",
      "dry_run_would_refresh": 1,
      "refreshed": 3,
      "provider_calls": {}
    },
    {
      "fixture_id": 1576805,
      "before": "UNKNOWN_ODDS",
      "dry_run_would_refresh": 1,
      "refreshed": 3,
      "provider_calls": {}
    }
  ]
}

### After

[
  {
    "fixture_id": 1570714,
    "match": "Mexico vs England",
    "kickoff_vienna": "2026-07-06 02:00 CEST",
    "snapshot_at": "2026-07-04T11:08:34.166035",
    "age_hours": 0.11,
    "source": "live",
    "freshness_status": "UNKNOWN_ODDS",
    "policy_status": "FRESH_ODDS",
    "has_1x2_market": true
  },
  {
    "fixture_id": 1576756,
    "match": "Portugal vs Spain",
    "kickoff_vienna": "2026-07-06 21:00 CEST",
    "snapshot_at": "2026-07-04T11:08:55.951206",
    "age_hours": 0.1,
    "source": "live",
    "freshness_status": "UNKNOWN_ODDS",
    "policy_status": "FRESH_ODDS",
    "has_1x2_market": true
  },
  {
    "fixture_id": 1576804,
    "match": "Argentina vs Egypt",
    "kickoff_vienna": "2026-07-07 18:00 CEST",
    "snapshot_at": null,
    "age_hours": null,
    "source": null,
    "freshness_status": "UNKNOWN_ODDS",
    "policy_status": "ODDS_MISSING",
    "has_1x2_market": false
  },
  {
    "fixture_id": 1576805,
    "match": "Switzerland vs Colombia",
    "kickoff_vienna": "2026-07-07 22:00 CEST",
    "snapshot_at": null,
    "age_hours": null,
    "source": null,
    "freshness_status": "UNKNOWN_ODDS",
    "policy_status": "ODDS_MISSING",
    "has_1x2_market": false
  }
]

## Forensic — Mexico & Portugal

{
  "mexico_england": {
    "fixture_id": 1570714,
    "payload_hash": "50501ff18ebd708a",
    "predicted_at": "2026-07-04T11:08:34.847154",
    "odds_snapshots_in_db": 2,
    "latest_odds_snapshot_at": "2026-07-04T11:08:34.166035",
    "payload_odds_status": "ODDS_MISSING",
    "payload_odds_metadata": {
      "freshness_flag": "ODDS_MISSING",
      "odds_freshness_status": "ODDS_MISSING",
      "odds_age_hours": null,
      "stale_threshold_hours": 6.0,
      "requires_fresh_odds": true,
      "stale_odds": true,
      "odds_snapshot_at": null,
      "reference_at": "2026-07-04 11:08:21 UTC",
      "odds_source": null,
      "priority_tier": "knockout",
      "odds_refresh_attempted": false,
      "odds_refresh_success": null,
      "odds_refresh_reason": null,
      "explanation": "No odds snapshot stored for this fixture. Refresh required before high-confidence use."
    },
    "wde_ran_without_bookmaker_odds": false,
    "odds_in_db_but_metadata_missing": true,
    "provider_probabilities_consumed": false,
    "odds_missing_classification": "metadata_only_gap",
    "pick_1x2": "home",
    "confidence": 27.6,
    "probabilities_1x2": {
      "home": 50.5,
      "draw": 26.4,
      "away": 23.1
    },
    "engine_version": "34b-v1",
    "trace": {
      "phase": "DAILY-OWNER-1",
      "provider_fixture_id": 1570714,
      "provider_source": "api-football",
      "crosswalk_status": "canonical_api"
    },
    "has_specialist_report": false,
    "has_intelligence_report": false
  },
  "portugal_spain": {
    "fixture_id": 1576756,
    "payload_hash": "31b06f9d02eb486e",
    "predicted_at": "2026-07-04T11:08:56.491215",
    "odds_snapshots_in_db": 2,
    "latest_odds_snapshot_at": "2026-07-04T11:08:55.951206",
    "payload_odds_status": "ODDS_MISSING",
    "payload_odds_metadata": {
      "freshness_flag": "ODDS_MISSING",
      "odds_freshness_status": "ODDS_MISSING",
      "odds_age_hours": null,
      "stale_threshold_hours": 6.0,
      "requires_fresh_odds": true,
      "stale_odds": true,
      "odds_snapshot_at": null,
      "reference_at": "2026-07-04 11:08:45 UTC",
      "odds_source": null,
      "priority_tier": "knockout",
      "odds_refresh_attempted": false,
      "odds_refresh_success": null,
      "odds_refresh_reason": null,
      "explanation": "No odds snapshot stored for this fixture. Refresh required before high-confidence use."
    },
    "wde_ran_without_bookmaker_odds": false,
    "odds_in_db_but_metadata_missing": true,
    "provider_probabilities_consumed": false,
    "odds_missing_classification": "metadata_only_gap",
    "pick_1x2": "away",
    "confidence": 49.1,
    "probabilities_1x2": {
      "home": 16.0,
      "draw": 24.7,
      "away": 59.3
    },
    "engine_version": "34b-v1",
    "trace": {
      "phase": "DAILY-OWNER-1",
      "provider_fixture_id": 1576756,
      "provider_source": "api-football",
      "crosswalk_status": "canonical_api"
    },
    "has_specialist_report": false,
    "has_intelligence_report": false
  },
  "existing_payload_preserved": {
    "1570714": true,
    "1576756": true
  }
}

## Recompute decisions (Mexico & Portugal)

{
  "1570714": "ODDS_METADATA_ONLY_PATCH",
  "1576756": "ODDS_METADATA_ONLY_PATCH"
}

## 1X2 predictions

[
  {
    "fixture_id": 1570714,
    "stored": true,
    "match": "Mexico vs England",
    "kickoff_utc": "2026-07-06T00:00:00",
    "round": "Round of 16",
    "pick_1x2": "home",
    "confidence": 27.6,
    "H": 50.5,
    "X": 26.4,
    "A": 23.1,
    "prob_sum": 100.0,
    "odds_status": "ODDS_MISSING",
    "odds_snapshot_at": null,
    "odds_source": null,
    "predicted_at": "2026-07-04T11:08:34.847154",
    "engine_version": "34b-v1",
    "payload_hash": "50501ff18ebd708a"
  },
  {
    "fixture_id": 1576756,
    "stored": true,
    "match": "Portugal vs Spain",
    "kickoff_utc": "2026-07-06T19:00:00",
    "round": "Round of 16",
    "pick_1x2": "away",
    "confidence": 49.1,
    "H": 16.0,
    "X": 24.7,
    "A": 59.3,
    "prob_sum": 100.0,
    "odds_status": "ODDS_MISSING",
    "odds_snapshot_at": null,
    "odds_source": null,
    "predicted_at": "2026-07-04T11:08:56.491215",
    "engine_version": "34b-v1",
    "payload_hash": "31b06f9d02eb486e"
  },
  {
    "fixture_id": 1576804,
    "stored": true,
    "match": "Argentina vs Egypt",
    "kickoff_utc": "2026-07-07T16:00:00",
    "round": "Round of 16",
    "pick_1x2": "home",
    "confidence": 50.9,
    "H": 79.0,
    "X": 14.0,
    "A": 7.1,
    "prob_sum": 100.1,
    "odds_status": "ODDS_MISSING",
    "odds_snapshot_at": null,
    "odds_source": null,
    "predicted_at": "2026-07-04T11:15:07.962480",
    "engine_version": "34b-v1",
    "payload_hash": "0216ffad4e832f05"
  },
  {
    "fixture_id": 1576805,
    "stored": true,
    "match": "Switzerland vs Colombia",
    "kickoff_utc": "2026-07-07T20:00:00",
    "round": "Round of 16",
    "pick_1x2": "home",
    "confidence": 43.9,
    "H": 49.3,
    "X": 26.8,
    "A": 24.0,
    "prob_sum": 100.1,
    "odds_status": "ODDS_MISSING",
    "odds_snapshot_at": null,
    "odds_source": null,
    "predicted_at": "2026-07-04T11:15:19.107050",
    "engine_version": "34b-v1",
    "payload_hash": "303e9f1fa514478a"
  }
]

## Rankings

{
  "by_selected_outcome_probability": [
    "Argentina vs Egypt",
    "Portugal vs Spain",
    "Mexico vs England",
    "Switzerland vs Colombia"
  ],
  "by_model_confidence": [
    "Argentina vs Egypt",
    "Portugal vs Spain",
    "Switzerland vs Colombia",
    "Mexico vs England"
  ],
  "by_odds_freshness_quality": [
    "Mexico vs England",
    "Portugal vs Spain",
    "Argentina vs Egypt",
    "Switzerland vs Colombia"
  ]
}

## Risk classification

{
  "1570714": "LOW_CONVICTION + INSUFFICIENT_ODDS_CONTEXT",
  "1576756": "INSUFFICIENT_ODDS_CONTEXT",
  "1576804": "INSUFFICIENT_ODDS_CONTEXT",
  "1576805": "INSUFFICIENT_ODDS_CONTEXT"
}

## ECSE guard

{
  "before": {
    "1570714": 1,
    "1576756": 1
  },
  "after": {
    "1570714": 1,
    "1576756": 1,
    "1576804": 0,
    "1576805": 0
  },
  "new_ecse_created": {
    "1570714": 0,
    "1576756": 0,
    "1576804": 0,
    "1576805": 0
  }
}
