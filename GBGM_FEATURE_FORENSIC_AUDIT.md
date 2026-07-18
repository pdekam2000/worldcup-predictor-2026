# GBGM FEATURE FORENSIC AUDIT

## Target audit summary
```json
{
  "n_rows": 1491,
  "global": {
    "n": 1491,
    "mean_home": 1.7907444668008048,
    "mean_away": 1.404426559356137,
    "var_home": 2.0299881110944678,
    "var_away": 1.5688335242845401,
    "zero_goal_share": 0.046948356807511735,
    "one_goal_share": 0.10663983903420524,
    "high_score_tail_ge5": 0.2199865861837693,
    "draw_share": 0.23742454728370221
  },
  "by_competition": {
    "bundesliga": {
      "n": 1111,
      "mean_home": 1.7785778577857785,
      "mean_away": 1.3807380738073807,
      "var_home": 2.0913862763414053,
      "var_away": 1.5499080061021402,
      "zero_goal_share": 0.05310531053105311,
      "one_goal_share": 0.10891089108910891,
      "high_score_tail_ge5": 0.21602160216021601,
      "draw_share": 0.24572457245724572
    },
    "premier_league": {
      "n": 358,
      "mean_home": 1.8072625698324023,
      "mean_away": 1.4972067039106145,
      "var_home": 1.8483271433475859,
      "var_away": 1.6578134265472364,
      "zero_goal_share": 0.030726256983240222,
      "one_goal_share": 0.10335195530726257,
      "high_score_tail_ge5": 0.23184357541899442,
      "draw_share": 0.21787709497206703
    },
    "champions_league": {
      "n": 5,
      "mean_home": 3.2,
      "mean_away": 1.8,
      "var_home": 3.7600000000000002,
      "var_away": 0.16,
      "zero_goal_share": 0.0,
      "one_goal_share": 0.0,
      "high_score_tail_ge5": 0.6,
      "draw_share": 0.0
    },
    "world_cup_2026": {
      "n": 17,
      "mean_home": 1.8235294117647058,
      "mean_away": 0.8823529411764706,
      "var_home": 0.7335640138408305,
      "var_away": 0.809688581314879,
      "zero_goal_share": 0.0,
      "one_goal_share": 0.058823529411764705,
      "high_score_tail_ge5": 0.11764705882352941,
      "draw_share": 0.17647058823529413
    }
  },
  "raw_status_filter_note": "Phase3 build used FT+AET+PEN; Phase3B recommends FT-only for regulation targets",
  "raw_status_counts": {
    "AET": 9,
    "FT": 2057,
    "PEN": 12
  },
  "checks": {
    "duplicate_fixture_ids": 0,
    "home_away_inversion_heuristic": "features encode home_/away_ separately; is_home was constant=1 in v1 (bug, non-informative)",
    "target_feature_alignment": true
  }
}
```

## Constant / nearly-constant features
- Constant: `['competition_key', 'is_home']`
- Nearly constant: `[]`

## Key findings
- is_home is constant=1.0 in GBGM-1 snapshots (non-informative)
- No xG/shots/lineup/injury features present in local Challenger snapshot
- Market features only when include_market=True and odds timestamp <= prediction time
- L5 form missing when team has <1 prior home/away match in competition

## Feature table (excerpt)
```json
[
  {
    "name": "away_goals_against_avg_l5",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 0.5475452846247567,
    "cardinality": 40,
    "mean": 1.7734630002235634,
    "leakage_risk": "low",
    "corr_home_goals": 0.06134933113485384,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "away_goals_for_avg_l5",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 0.505538210508549,
    "cardinality": 39,
    "mean": 1.3960652805723228,
    "leakage_risk": "low",
    "corr_home_goals": -0.11949840409398833,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "away_l5_sample",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 0.8754102976904575,
    "cardinality": 5,
    "mean": 4.674714956405097,
    "leakage_risk": "low",
    "corr_home_goals": 0.0017664804134486117,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "away_team_id",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 11821005.159428736,
    "cardinality": 65,
    "mean": 257.5734406438632,
    "leakage_risk": "low",
    "corr_home_goals": 0.044187805099407534,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "competition_key",
    "type": "non_numeric_or_all_missing",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": null,
    "cardinality": 0,
    "mean": null,
    "leakage_risk": "low",
    "corr_home_goals": null,
    "constant": true,
    "nearly_constant": true
  },
  {
    "name": "fixture_id",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 471598732214.9403,
    "cardinality": 1491,
    "mean": 1004293.8866532529,
    "leakage_risk": "low",
    "corr_home_goals": 0.017361969922526165,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "home_goals_against_avg_l5",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 0.4499386317157735,
    "cardinality": 37,
    "mean": 1.3842387659289068,
    "leakage_risk": "low",
    "corr_home_goals": -0.0978399617358172,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "home_goals_for_avg_l5",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 0.6795421716777551,
    "cardinality": 46,
    "mean": 1.8047171920411358,
    "leakage_risk": "low",
    "corr_home_goals": 0.21294415421781293,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "home_l5_sample",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 0.8713861528212422,
    "cardinality": 5,
    "mean": 4.674714956405097,
    "leakage_risk": "low",
    "corr_home_goals": 0.011856120652002531,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "home_team_id",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 11837368.122036941,
    "cardinality": 66,
    "mean": 256.9101274312542,
    "leakage_risk": "low",
    "corr_home_goals": -0.015176162437146302,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "is_home",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 0.0,
    "cardinality": 1,
    "mean": 1.0,
    "leakage_risk": "low",
    "corr_home_goals": null,
    "constant": true,
    "nearly_constant": true
  },
  {
    "name": "league_avg_away_goals",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 0.004346948546607315,
    "cardinality": 826,
    "mean": 1.3612374642914422,
    "leakage_risk": "low",
    "corr_home_goals": 0.015850008554051116,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "league_avg_home_goals",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 0.005318685502288555,
    "cardinality": 834,
    "mean": 1.77227795576559,
    "leakage_risk": "low",
    "corr_home_goals": -0.052583855692318375,
    "constant": false,
    "nearly_constant": false
  },
  {
    "name": "league_sample_before_cutoff",
    "type": "numeric",
    "source": "prematch_snapshot_or_enrichment",
    "availability_timestamp": "kickoff_cutoff_strict_less_than",
    "missing_rate": 0.0,
    "variance": 109657.9178716385,
    "cardinality": 745,
    "mean": 488.2079141515761,
    "leakage_risk": "low",
    "corr_home_goals": -0.01662638479654533,
    "constant": false,
    "nearly_constant": false
  }
]
```

Full JSON: `artifacts/challenger_program/phase3b/feature_audit.json`