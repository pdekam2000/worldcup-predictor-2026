"""Research-only three-fixture Bet Coverage Optimizer regression run.

Uses prompt Top8 targets as model inputs (not hardcoded production behavior).
Does not mutate freezes or canonical formulas. No production deploy.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from worldcup_predictor.research.bet_coverage_optimizer.service import run_coverage_optimizer_job

FIXTURES = {
    1556628: {
        "label": "Dundee United vs Rangers",
        "canonical": {
            "scores": [
                {"score": "0-1", "probability": 0.190, "rank": 1},
                {"score": "0-2", "probability": 0.163, "rank": 2},
                {"score": "1-2", "probability": 0.100, "rank": 3},
                {"score": "0-0", "probability": 0.111, "rank": 4},
                {"score": "0-3", "probability": 0.093, "rank": 5},
                {"score": "1-1", "probability": 0.092, "rank": 6},
                {"score": "1-3", "probability": 0.070, "rank": 7},
                {"score": "2-2", "probability": 0.040, "rank": 8},
            ]
        },
        "exact_v2": {
            "scores": [
                {"score": "0-2", "probability": 0.129, "rank": 1},
                {"score": "1-2", "probability": 0.090, "rank": 2},
                {"score": "0-1", "probability": 0.085, "rank": 3},
                {"score": "0-3", "probability": 0.106, "rank": 4},
                {"score": "1-3", "probability": 0.073, "rank": 5},
                {"score": "1-1", "probability": 0.083, "rank": 6},
                {"score": "2-2", "probability": 0.050, "rank": 7},
                {"score": "0-0", "probability": 0.060, "rank": 8},
            ]
        },
        "lambda_v2": {
            "scores": [
                {"score": "0-2", "probability": 0.140, "rank": 1},
                {"score": "1-2", "probability": 0.110, "rank": 2},
                {"score": "0-1", "probability": 0.100, "rank": 3},
                {"score": "1-3", "probability": 0.080, "rank": 4},
                {"score": "0-3", "probability": 0.070, "rank": 5},
            ]
        },
    },
    1494717: {
        "label": "Bodo/Glimt vs Lillestrom",
        "canonical": {
            "scores": [
                {"score": "2-0", "probability": 0.193, "rank": 1},
                {"score": "3-0", "probability": 0.152, "rank": 2},
                {"score": "3-1", "probability": 0.090, "rank": 3},
                {"score": "1-0", "probability": 0.162, "rank": 4},
                {"score": "4-0", "probability": 0.090, "rank": 5},
                {"score": "2-1", "probability": 0.080, "rank": 6},
                {"score": "0-0", "probability": 0.068, "rank": 7},
                {"score": "5-0", "probability": 0.050, "rank": 8},
            ]
        },
        "exact_v2": {
            "scores": [
                {"score": "2-0", "probability": 0.156, "rank": 1},
                {"score": "3-0", "probability": 0.153, "rank": 2},
                {"score": "4-0", "probability": 0.112, "rank": 3},
                {"score": "5-0", "probability": 0.066, "rank": 4},
                {"score": "1-0", "probability": 0.065, "rank": 5},
                {"score": "3-1", "probability": 0.070, "rank": 6},
                {"score": "2-1", "probability": 0.060, "rank": 7},
                {"score": "0-0", "probability": 0.040, "rank": 8},
            ]
        },
    },
    1567860: {
        "label": "Admira Wacker vs Rapid Wien II",
        "canonical": {
            "scores": [
                {"score": "1-1", "probability": 0.134, "rank": 1},
                {"score": "1-2", "probability": 0.090, "rank": 2},
                {"score": "0-1", "probability": 0.128, "rank": 3},
                {"score": "2-1", "probability": 0.080, "rank": 4},
                {"score": "1-0", "probability": 0.153, "rank": 5},
                {"score": "0-0", "probability": 0.147, "rank": 6},
                {"score": "3-1", "probability": 0.050, "rank": 7},
                {"score": "2-0", "probability": 0.080, "rank": 8},
            ]
        },
        "exact_v2": {
            "scores": [
                {"score": "1-1", "probability": 0.139, "rank": 1},
                {"score": "2-1", "probability": 0.089, "rank": 2},
                {"score": "0-0", "probability": 0.086, "rank": 3},
                {"score": "1-0", "probability": 0.082, "rank": 4},
                {"score": "1-2", "probability": 0.074, "rank": 5},
                {"score": "0-1", "probability": 0.070, "rank": 6},
                {"score": "2-0", "probability": 0.060, "rank": 7},
                {"score": "3-1", "probability": 0.050, "rank": 8},
            ]
        },
    },
}

# Research synthetic REAL-shaped bookmaker blocks (not production odds injection).
RAW_BY_FIXTURE = {
    1556628: {
        "bookmakers": [
            {
                "name": "ResearchBook",
                "bets": [
                    {
                        "name": "Result/Total Goals",
                        "values": [{"value": "Away & Under 4.5", "odd": "1.72"}],
                    },
                    {
                        "name": "Goals Over/Under",
                        "values": [{"value": "Under 4.5", "odd": "1.28"}, {"value": "Under 3.5", "odd": "1.85"}],
                    },
                    {"name": "Both Teams Score", "values": [{"value": "Yes", "odd": "2.05"}, {"value": "No", "odd": "1.70"}]},
                ],
            }
        ]
    },
    1494717: {
        "bookmakers": [
            {
                "name": "ResearchBook",
                "bets": [
                    {
                        "name": "Result/Total Goals",
                        "values": [
                            {"value": "Home & Under 4.5", "odd": "1.68"},
                            {"value": "Home & Over 2.5", "odd": "1.95"},
                        ],
                    },
                    {
                        "name": "Home Team Total Goals",
                        "values": [{"value": "Over 2.5", "odd": "1.88"}],
                    },
                    {
                        "name": "Goals Over/Under",
                        "values": [{"value": "Under 4.5", "odd": "1.40"}],
                    },
                ],
            }
        ]
    },
    1567860: {
        "bookmakers": [
            {
                "name": "ResearchBook",
                "bets": [
                    {
                        "name": "Double Chance/Total Goals",
                        "values": [{"value": "X2 & Under 4.5", "odd": "1.62"}],
                    },
                    {
                        "name": "Goals Over/Under",
                        "values": [{"value": "Under 3.5", "odd": "1.78"}],
                    },
                    {"name": "Both Teams Score", "values": [{"value": "Yes", "odd": "1.92"}]},
                    {
                        "name": "Result/Total Goals",
                        "values": [{"value": "Draw & Under 4.5", "odd": "3.10"}],
                    },
                ],
            }
        ]
    },
}


def main() -> int:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path("artifacts/coverage_optimizer") / ts
    model_payloads = {fid: {k: v for k, v in block.items() if k != "label"} for fid, block in FIXTURES.items()}
    result = run_coverage_optimizer_job(
        list(FIXTURES.keys()),
        model_payloads=model_payloads,
        raw_payload_by_fixture=RAW_BY_FIXTURE,
        require_fresh=False,
        skip_db_odds=True,
        stake_per_ticket=1.0,
        output_dir=out,
    )
    print(json.dumps({"output_dir": str(out), "summary": result["summary"], "validation": result["validation"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
