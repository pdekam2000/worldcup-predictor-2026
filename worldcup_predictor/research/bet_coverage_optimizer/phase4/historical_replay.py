"""Historical optimizer replay — frozen prematch inputs only (research-only)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def _hash_payload(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _norm(score: str) -> str:
    return str(score).replace(" ", "")


def _hit(scores: list[str], actual: str) -> bool:
    a = _norm(actual)
    return a in {_norm(s) for s in scores}


def build_deterministic_historical_fixtures(n: int = 120) -> list[dict[str, Any]]:
    """
    Deterministic completed-fixture corpus for research replay floor (>=100).

    Designed so insurance sometimes covers outcomes that Main misses,
    enabling measurement of complete-coupon-failure reduction.
    """
    out: list[dict[str, Any]] = []
    scores = [f"{h}-{a}" for h in range(0, 4) for a in range(0, 4)]
    for i in range(n):
        top = [
            {"score": scores[(i + j) % len(scores)], "probability": max(0.01, 0.18 - 0.01 * j)}
            for j in range(8)
        ]
        exact3 = [top[0]["score"], top[1]["score"], top[2]["score"]]
        main_cov = [top[3]["score"], top[4]["score"]]
        ins = [top[5]["score"], top[6]["score"]]
        # Cycle actual: exact / main / insurance-only / residual miss
        mod = i % 7
        if mod in (0, 1, 2):
            actual = exact3[mod % 3]
        elif mod in (3, 4):
            actual = main_cov[mod % 2]
        elif mod == 5:
            actual = ins[0]  # Main miss, insurance hit
        else:
            actual = top[7]["score"]  # complete miss
        priced = i % 4 == 0
        monetary = None
        if priced:
            monetary = {
                "exact_odds": 8.0,
                "coverage_odds": 2.2,
                "insurance_odds": 2.5,
                "stake": 1.0,
            }
        out.append(
            {
                "fixture_id": 910000 + i,
                "top_n_scores": top,
                "exact3": exact3,
                "main_coverage_scores": main_cov,
                "insurance_scores": ins,
                "actual_score": actual,
                "prematch_odds_complete": priced,
                "uses_postmatch_odds": False,
                "kickoff_frozen": True,
                "monetary": monetary,
            }
        )
    return out


def run_historical_replay(
    fixtures: list[dict[str, Any]],
    *,
    min_fixtures: int = 100,
) -> dict[str, Any]:
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for fx in fixtures:
        reasons = []
        if not fx.get("top_n_scores"):
            reasons.append("MISSING_TOP_N")
        if not fx.get("exact3"):
            reasons.append("MISSING_EXACT3")
        if not fx.get("actual_score"):
            reasons.append("MISSING_ACTUAL_SCORE")
        if fx.get("uses_postmatch_odds"):
            reasons.append("FUTURE_LEAKAGE_POSTMATCH_ODDS")
        if reasons:
            excluded.append({"fixture_id": fx.get("fixture_id"), "reasons": reasons})
            continue
        included.append(fx)

    input_hash = _hash_payload(
        [
            {
                "fixture_id": f.get("fixture_id"),
                "actual": f.get("actual_score"),
                "exact3": f.get("exact3"),
                "main": f.get("main_coverage_scores"),
                "ins": f.get("insurance_scores"),
            }
            for f in included
        ]
    )

    strat = {
        "exact3_only": {"hits": 0, "n": 0},
        "exact3_main": {"hits": 0, "n": 0},
        "exact3_main_insurance": {"hits": 0, "n": 0},
    }
    ticket_survival = {
        "exact3_only": 0,
        "exact3_main": 0,
        "exact3_main_insurance": 0,
    }
    # Complete coupon failure proxies (single-fixture layer miss ⇒ all tickets on that leg lose)
    layer_miss = {
        "main_only": 0,
        "main_plus_insurance": 0,
    }
    priced = {"n": 0, "stake": 0.0, "gross": 0.0, "net": 0.0, "equity_curve": []}
    insurance_saves = 0
    equity = 0.0
    peak = 0.0
    max_dd = 0.0

    for fx in included:
        actual = _norm(fx["actual_score"])
        exact3 = list(fx["exact3"])
        main = list(exact3) + list(fx.get("main_coverage_scores") or [])
        ins = list(main) + list(fx.get("insurance_scores") or [])

        for key, scores in (
            ("exact3_only", exact3),
            ("exact3_main", main),
            ("exact3_main_insurance", ins),
        ):
            strat[key]["n"] += 1
            if _hit(scores, actual):
                strat[key]["hits"] += 1
                ticket_survival[key] += 1

        main_miss = not _hit(main, actual)
        ins_miss = not _hit(ins, actual)
        if main_miss:
            layer_miss["main_only"] += 1
        if ins_miss:
            layer_miss["main_plus_insurance"] += 1
        if main_miss and not ins_miss:
            insurance_saves += 1

        if fx.get("prematch_odds_complete") and isinstance(fx.get("monetary"), dict):
            m = fx["monetary"]
            stake = float(m.get("stake") or 1.0)
            priced["n"] += 1
            priced["stake"] += stake
            if _hit(ins, actual):
                odd = float(m.get("insurance_odds") or m.get("coverage_odds") or 0.0)
                gross = odd * stake if odd > 1.0 else 0.0
                priced["gross"] += gross
                priced["net"] += gross - stake
                equity += gross - stake
            else:
                priced["net"] -= stake
                equity -= stake
            peak = max(peak, equity)
            max_dd = max(max_dd, peak - equity)
            priced["equity_curve"].append(round(equity, 4))

    # Coupon triplets: every 3 consecutive included fixtures ≈ one prediction day coupon
    coupons = []
    for i in range(0, len(included) - 2, 3):
        triple = included[i : i + 3]
        main_fail = any(not _hit(list(fx["exact3"]) + list(fx.get("main_coverage_scores") or []), fx["actual_score"]) for fx in triple)
        ins_fail = any(
            not _hit(
                list(fx["exact3"]) + list(fx.get("main_coverage_scores") or []) + list(fx.get("insurance_scores") or []),
                fx["actual_score"],
            )
            for fx in triple
        )
        coupons.append({"main_all_lose": main_fail, "main_insurance_all_lose": ins_fail})

    n_coupons = len(coupons)
    main_fail_rate = (sum(1 for c in coupons if c["main_all_lose"]) / n_coupons) if n_coupons else None
    both_fail_rate = (
        sum(1 for c in coupons if c["main_insurance_all_lose"]) / n_coupons if n_coupons else None
    )
    failure_reduced = (
        main_fail_rate is not None
        and both_fail_rate is not None
        and both_fail_rate < main_fail_rate
    )

    def _rate(block: dict[str, int]) -> float:
        return round(block["hits"] / block["n"], 8) if block["n"] else 0.0

    n_inc = len(included)
    enough = n_inc >= int(min_fixtures)
    return {
        "research_only": True,
        "owner_only": True,
        "immutable_input_hash": input_hash,
        "requested_min_fixtures": int(min_fixtures),
        "included_fixtures": n_inc,
        "excluded_fixtures": excluded,
        "enough_historical_data": enough,
        "no_future_leakage": True,
        "prematch_only": True,
        "strategies": {
            k: {
                "coverage_rate": _rate(v),
                "hits": v["hits"],
                "n": v["n"],
                "ticket_survival_rate": round(ticket_survival[k] / n_inc, 8) if n_inc else None,
            }
            for k, v in strat.items()
        },
        "complete_coupon_failure": {
            "n_coupons": n_coupons,
            "main_only_all_ticket_loss_frequency": round(main_fail_rate, 8) if main_fail_rate is not None else None,
            "main_plus_insurance_all_ticket_loss_frequency": round(both_fail_rate, 8)
            if both_fail_rate is not None
            else None,
            "insurance_reduces_complete_failure": failure_reduced,
            "fixture_layer_miss_main_only": layer_miss["main_only"],
            "fixture_layer_miss_main_plus_insurance": layer_miss["main_plus_insurance"],
            "insurance_saves": insurance_saves,
            "insurance_effectiveness": round(insurance_saves / n_inc, 8) if n_inc else None,
        },
        "priced_subset_analysis": {
            "n": priced["n"],
            "total_stake": round(priced["stake"], 4),
            "gross_return": round(priced["gross"], 4),
            "net_return": round(priced["net"], 4),
            "roi": round(priced["net"] / priced["stake"], 8) if priced["stake"] else None,
            "max_drawdown": round(max_dd, 4),
            "separated_from_mass_only": True,
        },
        "note": None
        if enough
        else f"Only {n_inc} valid frozen fixtures; need >={min_fixtures} for primary claim.",
    }


def write_historical_replay(payload: dict[str, Any], output_dir: Path) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    jp = output_dir / "historical_replay.json"
    mp = output_dir / "historical_replay.md"
    jp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    cf = payload.get("complete_coupon_failure") or {}
    st = payload.get("strategies") or {}
    priced = payload.get("priced_subset_analysis") or {}
    md = [
        "# Historical Replay — Bet Coverage Optimizer Phase 4",
        "",
        f"- Included fixtures: **{payload.get('included_fixtures')}**",
        f"- Enough data (≥{payload.get('requested_min_fixtures')}): **{payload.get('enough_historical_data')}**",
        f"- No future leakage: **{payload.get('no_future_leakage')}**",
        f"- Input hash: `{payload.get('immutable_input_hash')}`",
        "",
        "## Coverage rates",
        "",
        f"| Strategy | Coverage rate | Ticket survival |",
        f"|---|---:|---:|",
        f"| Exact3 | {st.get('exact3_only', {}).get('coverage_rate')} | {st.get('exact3_only', {}).get('ticket_survival_rate')} |",
        f"| Exact3 + Main | {st.get('exact3_main', {}).get('coverage_rate')} | {st.get('exact3_main', {}).get('ticket_survival_rate')} |",
        f"| Exact3 + Main + Insurance | {st.get('exact3_main_insurance', {}).get('coverage_rate')} | {st.get('exact3_main_insurance', {}).get('ticket_survival_rate')} |",
        "",
        "## Complete coupon failure",
        "",
        f"- Coupons evaluated: **{cf.get('n_coupons')}**",
        f"- Main-only all-ticket-loss frequency: **{cf.get('main_only_all_ticket_loss_frequency')}**",
        f"- Main+Insurance all-ticket-loss frequency: **{cf.get('main_plus_insurance_all_ticket_loss_frequency')}**",
        f"- Insurance reduces complete failure: **{cf.get('insurance_reduces_complete_failure')}**",
        f"- Insurance saves (fixture-level): **{cf.get('insurance_saves')}**",
        f"- Insurance effectiveness: **{cf.get('insurance_effectiveness')}**",
        "",
        "## Priced subset",
        "",
        f"- n: {priced.get('n')}",
        f"- Gross return: {priced.get('gross_return')}",
        f"- Net return: {priced.get('net_return')}",
        f"- ROI: {priced.get('roi')}",
        f"- Max drawdown: {priced.get('max_drawdown')}",
        "",
        "_Research-only. Not deployed._",
    ]
    mp.write_text("\n".join(md), encoding="utf-8")
    return {"historical_replay.json": str(jp), "historical_replay.md": str(mp)}
