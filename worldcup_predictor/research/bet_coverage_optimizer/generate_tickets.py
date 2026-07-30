"""64-ticket generator: deterministic 4×4×4 combinations."""

from __future__ import annotations

import csv
import itertools
import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation
from worldcup_predictor.research.multi_market_odds_loader import FRESH_OK


def _selection_legs(rec: CoverageRecommendation) -> list[dict[str, Any]]:
    legs: list[dict[str, Any]] = []
    for ex in rec.selected_exact_scores[:3]:
        legs.append(
            {
                "selection_id": ex.selection_id,
                "label": ex.label,
                "kind": "exact_score",
                "score": ex.score,
                "odds": ex.odds,
                "odds_freshness_status": ex.odds_freshness_status,
            }
        )
    while len(legs) < 3:
        legs.append(
            {
                "selection_id": f"exact:missing:{len(legs)+1}",
                "label": "MISSING_EXACT",
                "kind": "exact_score",
                "score": None,
                "odds": None,
                "odds_freshness_status": None,
            }
        )
    cov = rec.selected_coverage_market
    if cov is None:
        legs.append(
            {
                "selection_id": "coverage:unavailable",
                "label": "COVERAGE_MARKET_UNAVAILABLE",
                "kind": "coverage",
                "score": None,
                "odds": None,
                "odds_freshness_status": None,
                "market_key": None,
            }
        )
    else:
        legs.append(
            {
                "selection_id": f"coverage:{cov.market_key}",
                "label": cov.market_label,
                "kind": "coverage",
                "score": None,
                "odds": cov.odds,
                "odds_freshness_status": cov.odds_freshness_status,
                "market_key": cov.market_key,
            }
        )
    return legs[:4]


def generate_64_tickets(
    recommendations: list[CoverageRecommendation],
    *,
    stake_per_ticket: float = 1.0,
) -> dict[str, Any]:
    if len(recommendations) != 3:
        raise ValueError("exactly 3 fixture recommendations required for 64-ticket generation")

    per_fixture = []
    for rec in recommendations:
        legs = _selection_legs(rec)
        if len(legs) != 4:
            raise ValueError(f"fixture {rec.fixture_id} does not have 4 selections")
        per_fixture.append({"fixture_id": rec.fixture_id, "legs": legs})

    tickets: list[dict[str, Any]] = []
    seen: set[tuple] = set()
    ticket_no = 0
    for combo in itertools.product(*[pf["legs"] for pf in per_fixture]):
        key = tuple((per_fixture[i]["fixture_id"], combo[i]["selection_id"]) for i in range(3))
        if key in seen:
            continue
        seen.add(key)
        ticket_no += 1
        odds_vals = []
        fresh_ok = True
        for leg in combo:
            o = leg.get("odds")
            fr = str(leg.get("odds_freshness_status") or "")
            if o is None or float(o) <= 1.0:
                fresh_ok = False
                odds_vals = []
                break
            if fr and fr not in FRESH_OK:
                fresh_ok = False
                odds_vals = []
                break
            odds_vals.append(float(o))
        combined = None
        if fresh_ok and len(odds_vals) == 3:
            combined = round(odds_vals[0] * odds_vals[1] * odds_vals[2], 6)
        tickets.append(
            {
                "ticket_number": ticket_no,
                "selections": [
                    {
                        "fixture_id": per_fixture[i]["fixture_id"],
                        "selection_id": combo[i]["selection_id"],
                        "label": combo[i]["label"],
                        "kind": combo[i]["kind"],
                        "odds": combo[i].get("odds"),
                    }
                    for i in range(3)
                ],
                "combined_odds": combined,
                "stake": float(stake_per_ticket),
            }
        )

    assert ticket_no == 64, f"expected 64 unique tickets, got {ticket_no}"
    combined_available = [t["combined_odds"] for t in tickets if t["combined_odds"] is not None]
    summary = {
        "ticket_count": len(tickets),
        "matches": [r.fixture_id for r in recommendations],
        "stake_per_ticket": float(stake_per_ticket),
        "total_stake": round(len(tickets) * float(stake_per_ticket), 4),
        "min_combined_odds": min(combined_available) if combined_available else None,
        "max_combined_odds": max(combined_available) if combined_available else None,
        "tickets_with_combined_odds": len(combined_available),
    }
    return {"summary": summary, "tickets": tickets}


def write_tickets_artifacts(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "tickets_64.json"
    csv_path = output_dir / "tickets_64.csv"
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    with csv_path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(
            [
                "ticket_number",
                "fixture_1",
                "selection_1_id",
                "selection_1_label",
                "fixture_2",
                "selection_2_id",
                "selection_2_label",
                "fixture_3",
                "selection_3_id",
                "selection_3_label",
                "combined_odds",
                "stake",
            ]
        )
        for t in payload["tickets"]:
            s = t["selections"]
            writer.writerow(
                [
                    t["ticket_number"],
                    s[0]["fixture_id"],
                    s[0]["selection_id"],
                    s[0]["label"],
                    s[1]["fixture_id"],
                    s[1]["selection_id"],
                    s[1]["label"],
                    s[2]["fixture_id"],
                    s[2]["selection_id"],
                    s[2]["label"],
                    t["combined_odds"] if t["combined_odds"] is not None else "",
                    t["stake"],
                ]
            )
    return {"tickets_64.json": str(json_path), "tickets_64.csv": str(csv_path)}


def main(argv: list[str] | None = None) -> int:
    import argparse
    from datetime import datetime, timezone

    from worldcup_predictor.research.bet_coverage_optimizer.service import run_coverage_optimizer_job

    parser = argparse.ArgumentParser(description="Generate 64 coverage optimizer tickets")
    parser.add_argument("--fixture-ids", nargs=3, type=int, required=True)
    parser.add_argument("--stake-per-ticket", type=float, default=1.0)
    parser.add_argument("--output-dir", type=str, default="")
    parser.add_argument("--require-fresh", action="store_true", default=False)
    args = parser.parse_args(argv)

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = Path(args.output_dir) if args.output_dir else Path("artifacts/coverage_optimizer") / ts
    result = run_coverage_optimizer_job(
        list(args.fixture_ids),
        stake_per_ticket=float(args.stake_per_ticket),
        output_dir=out,
        require_fresh=bool(args.require_fresh),
    )
    print(json.dumps({"output_dir": str(out), "summary": result.get("summary"), "artifact_paths": result.get("artifact_paths")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
