"""Goalscorer odds backfill plan (design only — no import)."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.egie.goalscorer_odds_acquisition.models import BackfillPlan

# Phase 54M observed yields
_SPORTMONKS_GS_HIT_RATE = 3 / 70  # UEFA odds-rich cache files with GS
_AVG_SELECTIONS_PER_SPORTMONKS_GS_FIXTURE = 703 / 3
_AVG_SELECTIONS_PER_API_GS_FIXTURE = 5247  # from inventory scan
_PLAYER_MARKET_SHARE = 417 / 703  # Sportmonks player vs team rows
_SPORTMONKS_DEEP_INCLUDE = "participants;league;season;state;lineups.player;lineups.details.type;odds.bookmaker;odds.market"


def build_backfill_plans(candidates: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    api_count = int((candidates.get("counts") or {}).get("api_football_with_gs") or 0)
    sm_gs = int((candidates.get("counts") or {}).get("sportmonks_with_gs") or 0)
    sm_candidates = int((candidates.get("counts") or {}).get("sportmonks_backfill_candidates") or 0)

    plans: list[BackfillPlan] = []

    # Plan A — zero-call import from existing API-Football snapshots
    plans.append(
        BackfillPlan(
            strategy="A_existing_api_football_snapshots",
            candidate_fixtures=api_count,
            expected_api_calls=0,
            expected_odds_fixtures=api_count,
            expected_player_selections=int(api_count * _AVG_SELECTIONS_PER_API_GS_FIXTURE * 0.35),
            quota_impact="None — data already in odds_snapshots + .cache/api_football",
            steps=[
                "Parse 72 WC 2026 fixtures from odds_snapshots (API-Football IDs)",
                "Split player vs team-scoped markets via market_classifier",
                "Bridge API-Football fixture_id → lineup source (API-Football lineups cache or Sportmonks ID lookup)",
                "Feed player selections into 54M mapper with lineup context",
            ],
            risks=[
                "API-Football fixture IDs differ from Sportmonks IDs used by ML shadow engine",
                "Lineup bridge not yet built — mapping may stall without lineups",
            ],
        )
    )

    # Plan B — Sportmonks UEFA deep re-fetch (capped)
    for target in (50, 100, 200):
        calls = min(sm_candidates, target)
        expected_gs = max(1, int(calls * _SPORTMONKS_GS_HIT_RATE))
        plans.append(
            BackfillPlan(
                strategy=f"B_sportmonks_uefa_deep_fetch_{target}",
                candidate_fixtures=calls,
                expected_api_calls=calls,
                expected_odds_fixtures=expected_gs,
                expected_player_selections=int(expected_gs * _AVG_SELECTIONS_PER_SPORTMONKS_GS_FIXTURE * _PLAYER_MARKET_SHARE),
                quota_impact=f"~{calls} Sportmonks API calls (1 fixture deep pull each); ~{expected_gs} expected GS fixtures at {_SPORTMONKS_GS_HIT_RATE:.1%} hit rate",
                steps=[
                    f"Select top-{calls} UEFA backfill candidates by priority_score",
                    f"GET /fixtures/{{id}}?include={_SPORTMONKS_DEEP_INCLUDE}",
                    "Cache raw JSON under data/egie/uefa_club/raw/",
                    "Re-run 54M strict audit on expanded cache",
                ],
                risks=[
                    "Low historical GS yield on UEFA (~4% of odds-rich fixtures in cache)",
                    "bet365 GS markets sparse outside specific match types",
                    "Local Sportmonks token may be invalid — use server token for live pull",
                ],
            )
        )

    # Plan C — API-Football odds endpoint for PL/UEFA (if quota available)
    plans.append(
        BackfillPlan(
            strategy="C_api_football_odds_endpoint",
            candidate_fixtures=200,
            expected_api_calls=200,
            expected_odds_fixtures=40,
            expected_player_selections=int(40 * 3500),
            quota_impact="~200 API-Football calls (odds endpoint); estimated 20% GS market availability on top leagues",
            steps=[
                "Target finished PL + UCL fixtures 2023-2025 from fixtures table",
                "GET /odds?fixture={id} per fixture (cache-first via ApiCache)",
                "Insert into odds_snapshots if GS markets present",
            ],
            risks=[
                "API-Football GS coverage varies by league/bookmaker",
                "Requires API-Football quota separate from Sportmonks",
                "Still needs lineup bridge for mapping",
            ],
        )
    )

    # Recommended combined path
    reach_50 = api_count >= 50
    reach_100 = api_count >= 100

    recommendation_notes = []
    if reach_50:
        recommendation_notes.append(
            f"Plan A alone satisfies 50+ fixture minimum ({api_count} API-Football fixtures on disk)"
        )
    else:
        recommendation_notes.append("Plan A insufficient alone; combine with Plan B or C")
    if not reach_100:
        recommendation_notes.append(
            f"100+ target requires Plan B (~{max(0, 100 - api_count)} additional Sportmonks GS fixtures) or Plan C"
        )

    return {
        "plans": [p.to_dict() for p in plans],
        "recommended_sequence": ["A_existing_api_football_snapshots", "B_sportmonks_uefa_deep_fetch_100", "C_api_football_odds_endpoint"],
        "reach_50_with_plan_a_only": reach_50,
        "reach_100_with_plan_a_only": reach_100,
        "notes": recommendation_notes,
        "assumptions": {
            "sportmonks_gs_hit_rate": round(_SPORTMONKS_GS_HIT_RATE, 4),
            "avg_selections_per_sportmonks_gs_fixture": round(_AVG_SELECTIONS_PER_SPORTMONKS_GS_FIXTURE, 1),
            "avg_selections_per_api_gs_fixture": round(_AVG_SELECTIONS_PER_API_GS_FIXTURE, 1),
            "player_market_share_sportmonks": round(_PLAYER_MARKET_SHARE, 4),
        },
    }
