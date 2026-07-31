"""Forensic audit of main + insurance tickets (research-only)."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from worldcup_predictor.research.bet_coverage_optimizer.insurance.schemas import InsuranceTicket
from worldcup_predictor.research.bet_coverage_optimizer.models import CoverageRecommendation


def _fixture_name(fid: int, names: dict[int, str] | None) -> str:
    if names and fid in names:
        return names[fid]
    return str(fid)


def _leg_model_prob(rec: CoverageRecommendation, leg: dict[str, Any]) -> float | None:
    kind = leg.get("kind")
    if kind == "exact_score":
        score = leg.get("score")
        for ex in rec.selected_exact_scores:
            if ex.score == score:
                return float(ex.weighted_probability or 0.0)
        return None
    if kind == "coverage" and rec.selected_coverage_market:
        return float(rec.selected_coverage_market.estimated_model_probability or 0.0)
    return None


def audit_main_tickets(
    main_payload: dict[str, Any],
    recommendations: list[CoverageRecommendation],
    *,
    fixture_names: dict[int, str] | None = None,
    budget: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    by_fid = {int(r.fixture_id): r for r in recommendations}
    stake = float(
        (budget or {}).get("stake_per_main_ticket_eur")
        or (budget or {}).get("equal_main_stake_eur")
        or main_payload.get("summary", {}).get("stake_per_ticket")
        or 1.0
    )
    rows: list[dict[str, Any]] = []
    tickets = list(main_payload.get("tickets") or [])
    # Rank by combined odds desc when available, else ticket number
    ranked = sorted(
        tickets,
        key=lambda t: (
            0 if t.get("combined_odds") is not None else 1,
            -(float(t["combined_odds"]) if t.get("combined_odds") is not None else 0.0),
            int(t.get("ticket_number") or 0),
        ),
    )
    rank_map = {int(t["ticket_number"]): i + 1 for i, t in enumerate(ranked)}

    for t in tickets:
        tid = f"MAIN-{int(t['ticket_number']):03d}"
        sels = []
        model_probs = []
        bookmakers = []
        market_names = []
        odds_list = []
        fixture_ids = []
        fixture_names_out = []
        for leg in t.get("selections") or []:
            fid = int(leg["fixture_id"])
            rec = by_fid[fid]
            fixture_ids.append(fid)
            fixture_names_out.append(_fixture_name(fid, fixture_names))
            mp = _leg_model_prob(rec, leg)
            if mp is not None:
                model_probs.append(mp)
            bookmaker = None
            market_name = str(leg.get("label") or "")
            if leg.get("kind") == "coverage" and rec.selected_coverage_market:
                bookmaker = rec.selected_coverage_market.bookmaker
                market_name = rec.selected_coverage_market.market_label
            elif leg.get("kind") == "exact_score":
                bookmaker = None
                market_name = f"Exact {leg.get('score')}"
            bookmakers.append(bookmaker)
            market_names.append(market_name)
            odds_list.append(leg.get("odds"))
            sels.append(
                {
                    "fixture_id": fid,
                    "fixture_name": _fixture_name(fid, fixture_names),
                    "selection_id": leg.get("selection_id"),
                    "label": leg.get("label"),
                    "kind": leg.get("kind"),
                    "score": leg.get("score"),
                    "bookmaker": bookmaker,
                    "market_name": market_name,
                    "bookmaker_odds": leg.get("odds"),
                    "model_probability": mp,
                }
            )
        joint = 1.0
        for p in model_probs:
            joint *= max(0.0, min(1.0, p))
        combined = t.get("combined_odds")
        monetary_ev = None
        if combined is not None and all(o is not None for o in odds_list):
            monetary_ev = round(float(combined) * joint * stake - stake, 6)
        rows.append(
            {
                "ticket_id": tid,
                "ticket_layer": "main",
                "selections": sels,
                "fixture_ids": fixture_ids,
                "fixture_names": fixture_names_out,
                "bookmaker": next((b for b in bookmakers if b), None),
                "market_names": market_names,
                "bookmaker_odds": odds_list,
                "combined_odds": combined,
                "model_probability": round(joint, 8),
                "monetary_ev": monetary_ev,
                "probability_mass_utility": round(joint, 8),
                "reason_for_inclusion": "MAIN_64_CARTESIAN_PRODUCT",
                "coupon_score": round(joint * (float(combined) if combined else 1.0), 8),
                "diversification_score": None,
                "overlap_score": None,
                "insurance_usage": False,
                "ranking": rank_map.get(int(t["ticket_number"]), int(t["ticket_number"])),
                "stake_eur": stake,
            }
        )
    rows.sort(key=lambda r: int(r["ranking"]))
    return rows


def audit_insurance_tickets(
    insurance_tickets: list[InsuranceTicket],
    *,
    fixture_names: dict[int, str] | None = None,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for t in insurance_tickets:
        fixture_ids = [int(s.get("fixture_id")) for s in t.selections]
        names = [_fixture_name(fid, fixture_names) for fid in fixture_ids]
        market_names = [str(s.get("label") or s.get("market_label") or "") for s in t.selections]
        odds_list = [s.get("odds") for s in t.selections]
        bookmakers = [s.get("bookmaker") for s in t.selections]
        rows.append(
            {
                "ticket_id": t.ticket_id,
                "ticket_layer": "insurance",
                "selections": [
                    {
                        **s,
                        "fixture_name": _fixture_name(int(s.get("fixture_id")), fixture_names),
                        "market_name": s.get("label") or s.get("market_label"),
                        "bookmaker_odds": s.get("odds"),
                    }
                    for s in t.selections
                ],
                "fixture_ids": fixture_ids,
                "fixture_names": names,
                "bookmaker": next((b for b in bookmakers if b), None),
                "market_names": market_names,
                "bookmaker_odds": odds_list,
                "combined_odds": t.combined_odds,
                "model_probability": t.modeled_joint_hit_probability,
                "monetary_ev": t.monetary_ev,
                "probability_mass_utility": t.probability_mass_utility,
                "reason_for_inclusion": t.inclusion_reason,
                "coupon_score": t.insurance_coupon_score,
                "diversification_score": t.diversification_score,
                "overlap_score": t.overlap_penalty,
                "insurance_usage": True,
                "insurance_fixture_ids": list(t.insurance_fixture_ids),
                "n_insurance_legs": t.n_insurance_legs,
                "ranking": t.rank,
                "stake_eur": t.stake_eur,
            }
        )
    return rows


def build_ticket_audit(
    *,
    main_payload: dict[str, Any],
    insurance_tickets: list[InsuranceTicket],
    recommendations: list[CoverageRecommendation],
    fixture_names: dict[int, str] | None = None,
    budget: dict[str, Any] | None = None,
) -> dict[str, Any]:
    main_rows = audit_main_tickets(
        main_payload, recommendations, fixture_names=fixture_names, budget=budget
    )
    ins_rows = audit_insurance_tickets(insurance_tickets, fixture_names=fixture_names)
    return {
        "research_only": True,
        "owner_only": True,
        "n_main_tickets": len(main_rows),
        "n_insurance_tickets": len(ins_rows),
        "tickets": main_rows + ins_rows,
    }


def write_ticket_audit(audit: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jp = output_dir / "ticket_audit.json"
    cp = output_dir / "ticket_audit.csv"
    jp.write_text(json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8")
    with cp.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(
            [
                "ticket_id",
                "ticket_layer",
                "ranking",
                "fixture_ids",
                "fixture_names",
                "market_names",
                "bookmaker",
                "bookmaker_odds",
                "combined_odds",
                "model_probability",
                "monetary_ev",
                "probability_mass_utility",
                "reason_for_inclusion",
                "coupon_score",
                "diversification_score",
                "overlap_score",
                "insurance_usage",
                "stake_eur",
            ]
        )
        for t in audit.get("tickets") or []:
            w.writerow(
                [
                    t.get("ticket_id"),
                    t.get("ticket_layer"),
                    t.get("ranking"),
                    "|".join(str(x) for x in (t.get("fixture_ids") or [])),
                    "|".join(str(x) for x in (t.get("fixture_names") or [])),
                    " || ".join(str(x) for x in (t.get("market_names") or [])),
                    t.get("bookmaker") or "",
                    "|".join("" if o is None else str(o) for o in (t.get("bookmaker_odds") or [])),
                    "" if t.get("combined_odds") is None else t.get("combined_odds"),
                    t.get("model_probability"),
                    "" if t.get("monetary_ev") is None else t.get("monetary_ev"),
                    t.get("probability_mass_utility"),
                    t.get("reason_for_inclusion"),
                    t.get("coupon_score"),
                    "" if t.get("diversification_score") is None else t.get("diversification_score"),
                    "" if t.get("overlap_score") is None else t.get("overlap_score"),
                    t.get("insurance_usage"),
                    "" if t.get("stake_eur") is None else t.get("stake_eur"),
                ]
            )
    return {"ticket_audit.json": str(jp), "ticket_audit.csv": str(cp)}
