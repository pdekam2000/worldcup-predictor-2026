"""Static provenance inventories for Phase 1."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_lambda_extraction import (
    LAMBDA_CEIL,
    LAMBDA_FLOOR,
    METHOD_VERSION,
    MIN_DATA_QUALITY,
    WEIGHT_OU_15,
    WEIGHT_OU_25,
    WEIGHT_OU_35,
    WEIGHT_TEAM_SUM,
)


def write_phase1_docs(out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)

    (out / "lambda_dependency_graph.md").write_text(
        f"""# Lambda dependency graph

## Canonical production path (ECSE)

```
prematch odds lines
  -> build_odds_feature_row / ecse_training_dataset closing odds
  -> extract_lambdas()  [{METHOD_VERSION}]
       O/U 1.5 / 2.5 / 3.5  -> solve_lambda_total_from_over (Poisson invert)
       team O/U 0.5 / 1.5   -> team lambdas
       1X2 (+ DC draw proxy) -> share_home split
       BTTS gentle rescale   -> scale in [0.85, 1.15]
       clip each lambda      -> [{LAMBDA_FLOOR}, {LAMBDA_CEIL}]
  -> generate_score_distribution()  [ECSE-1D-B, MAX_GOALS=7 + OTHER]
  -> freeze (lambda_home/away columns)
```

## Alternate runtime paths

| Path | Entry | Lambda source |
|------|-------|---------------|
| Live odds | `build_ecse_live_prediction` | `extract_lambdas(odds_row)` |
| Registry precomputed | same | `ecse_lambda_features` table |
| Prematch bundle | `build_ecse_live_prediction_from_prematch` | `extract_lambdas` |
| Historical replay | eligibility + extract_lambdas | same extractor |

## What does NOT enter canonical lambda

- Team attack/defense Elo or ratings
- Recent form / goals scored-conceded windows
- Volatility / high-total frequency
- League goal-environment priors (except default draw 0.26)
- Promoted / reserve / youth flags
- Lineup / injury
- WDE probabilities (WDE runs separately)
- Training-time football features

**Confirmed:** canonical λ is odds-market inversion + blending, not a football team-strength model.
""",
        encoding="utf-8",
    )

    (out / "lambda_clipping_and_bounds_audit.md").write_text(
        f"""# Lambda clipping and bounds audit

| Control | Value | Location |
|---------|-------|----------|
| LAMBDA_FLOOR | {LAMBDA_FLOOR} | ecse_lambda_extraction.py |
| LAMBDA_CEIL | {LAMBDA_CEIL} | ecse_lambda_extraction.py |
| O/U solve search | [0.2, 7.0] | solve_lambda_total_from_over |
| Team O/U 1.5 solve | [0.2, 5.0] | solve_lambda_team_from_over15 |
| BTTS scale clamp | [0.85, 1.15] | extract_lambdas |
| Draw proxy default | 0.26 | outcome_probs / extract_lambdas |
| Draw proxy clamp | [0.02, 0.50] / [0.05, 0.45] | helpers |
| MIN_DATA_QUALITY | {MIN_DATA_QUALITY} | reject extraction |
| O/U 2.5 weight | {WEIGHT_OU_25} | blend |
| O/U 1.5 weight | {WEIGHT_OU_15} | blend |
| O/U 3.5 weight | {WEIGHT_OU_35} | blend |
| Team-sum weight (declared) | {WEIGHT_TEAM_SUM} | declared; final blend uses 0.65 OU / 0.35 team |
| Total blend OU vs team | 0.65 / 0.35 | extract_lambdas |
| Share vs team refine | 0.55 / 0.45 | after split |
| Score grid max | 7 | ecse_score_distribution.MAX_GOALS |
| Residual | OTHER bucket | not redistributed to named high scores |

## Risk notes

1. Ceiling 6.0 per side rarely binds; underestimation is usually mean-level, not hard cap.
2. Missing O/U 3.5 / 4.5 reduces high-total signal (4.5 not used at all).
3. Default draw 0.26 when DC/1X2 incomplete is a low-scoring-leaning prior for share only.
4. No football shrinkage toward low-scoring means in extractor — but **missing markets** force weaker OU blends.
5. BTTS rescale can shrink both lambdas when model BTTS > market BTTS.
""",
        encoding="utf-8",
    )


def feature_source_inventory_rows() -> list[dict[str, Any]]:
    rows = []
    odds_features = [
        ("ft_home_closing", "1X2", "share_home", True),
        ("ft_draw_closing", "1X2", "outcome probs / draw", True),
        ("ft_away_closing", "1X2", "share_home", True),
        ("ou_over_25_closing", "O/U", "lambda_total_ou", True),
        ("ou_under_25_closing", "O/U", "lambda_total_ou", True),
        ("ou_over_15_closing", "O/U", "lambda_total_ou", True),
        ("ou_under_15_closing", "O/U", "lambda_total_ou", True),
        ("ou_over_35_closing", "O/U", "lambda_total_ou", True),
        ("ou_under_35_closing", "O/U", "lambda_total_ou", True),
        ("ou_over_45_closing", "O/U", "loaded in SQL but UNUSED in extract_lambdas", False),
        ("team_home_over_05_closing", "team O/U", "lambda_home_team", True),
        ("team_away_over_05_closing", "team O/U", "lambda_away_team", True),
        ("team_home_over_15_closing", "team O/U", "lambda_home_team blend", True),
        ("team_away_over_15_closing", "team O/U", "lambda_away_team blend", True),
        ("btts_yes_closing", "BTTS", "gentle rescale", True),
        ("btts_no_closing", "BTTS", "gentle rescale", True),
        ("dc_*", "double chance", "draw_proxy", True),
        ("fh_*", "1H 1X2", "quality score only", False),
    ]
    for name, grp, role, used in odds_features:
        rows.append(
            {
                "feature": name,
                "group": grp,
                "role_in_lambda": role,
                "enters_canonical_lambda": used,
                "source_model": METHOD_VERSION,
                "football_strength": False,
            }
        )
    football = [
        "recent_goals_scored",
        "recent_goals_conceded",
        "home_attack_form",
        "away_attack_form",
        "elo_rating",
        "league_scoring_average",
        "scoring_variance",
        "promoted_team_flag",
        "reserve_youth_flag",
        "lineup_injury",
        "odds_movement",
        "wde_hda_probs",
    ]
    for name in football:
        rows.append(
            {
                "feature": name,
                "group": "football/meta",
                "role_in_lambda": "NOT WIRED to extract_lambdas",
                "enters_canonical_lambda": False,
                "source_model": "none_canonical",
                "football_strength": True,
            }
        )
    return rows


def fallback_inventory_rows() -> list[dict[str, Any]]:
    return [
        {
            "fallback": "return None if no lambda_total",
            "trigger": "missing all O/U and team totals",
            "effect": "no ECSE prediction / skip",
            "severity": "silent miss or registry precomputed path",
        },
        {
            "fallback": "draw_proxy = 0.26",
            "trigger": "no DC and no p_draw",
            "effect": "1X2 share uses fixed draw prior",
            "severity": "share_home distortion",
        },
        {
            "fallback": "OU-only or team-only total",
            "trigger": "one family missing",
            "effect": "no 0.65/0.35 blend",
            "severity": "under/over estimate vs full market",
        },
        {
            "fallback": "registry_precomputed lambdas",
            "trigger": "registry_fixture_id mapped",
            "effect": "reuse training-time extract_lambdas",
            "severity": "stale vs live odds if mapping wrong",
        },
        {
            "fallback": "league/global priors in research challengers",
            "trigger": "low-data team in LTS store",
            "effect": "shrink toward league averages",
            "severity": "shadow-only; not production",
        },
        {
            "fallback": "LAMBDA_FLOOR / LAMBDA_CEIL clip",
            "trigger": "extreme solve",
            "effect": "hard bound",
            "severity": "rare for ceil; floor can inflate tiny team totals",
        },
    ]


def runtime_trace_rows() -> list[dict[str, Any]]:
    return [
        {
            "runtime_path": "live_odds",
            "source_model": "ECSE-LIVE-1 + ECSE-1C-v1",
            "entry": "prediction_builder.build_ecse_live_prediction",
            "lambda_fn": "extract_lambdas",
            "score_fn": "generate_score_distribution",
            "preprocessing": "median odds across bookmakers in build_odds_feature_row",
            "scaling": "BTTS scale 0.85-1.15; then floor/ceil",
            "defaults": "draw 0.26; share_home 0.5",
            "missing_value_handling": "skip market; may return None",
            "league_priors": "none in extractor",
            "team_priors": "none in extractor",
            "home_advantage": "implicit via 1X2 share + team O/U",
            "attack_strength": "NOT USED",
            "defense_strength": "NOT USED",
            "recent_form": "NOT USED",
            "opponent_strength": "NOT USED",
            "odds_influence": "PRIMARY",
            "ou_influence": "PRIMARY (weights 0.40/0.20/0.15)",
            "btts_influence": "secondary rescale",
            "wde_influence": "NONE on lambda",
            "calibration_layer": "BTTS gentle only",
            "clipping": f"[{LAMBDA_FLOOR},{LAMBDA_CEIL}]",
            "shrinkage": "blend OU↔team and share↔team; no Bayesian football shrink",
            "feature_timestamps": "odds snapshot at freeze",
            "model_artifact_version": "ECSE-1C-v1 / ECSE-1D-B-v1",
        },
        {
            "runtime_path": "registry_precomputed",
            "source_model": "ecse_lambda_features + ecse_top_scores",
            "entry": "prediction_builder (registry hit)",
            "lambda_fn": "table lookup (built by extract_lambdas offline)",
            "score_fn": "precomputed top scores",
            "preprocessing": "training dataset closing odds",
            "scaling": "same as extract_lambdas",
            "defaults": "same",
            "missing_value_handling": "row absent -> fall through to live odds",
            "league_priors": "none",
            "team_priors": "none",
            "home_advantage": "implicit",
            "attack_strength": "NOT USED",
            "defense_strength": "NOT USED",
            "recent_form": "NOT USED",
            "opponent_strength": "NOT USED",
            "odds_influence": "PRIMARY (historical closing)",
            "ou_influence": "PRIMARY",
            "btts_influence": "secondary",
            "wde_influence": "NONE",
            "calibration_layer": "BTTS gentle",
            "clipping": f"[{LAMBDA_FLOOR},{LAMBDA_CEIL}]",
            "shrinkage": "same blends",
            "feature_timestamps": "training closing time",
            "model_artifact_version": METHOD_VERSION,
        },
    ]
