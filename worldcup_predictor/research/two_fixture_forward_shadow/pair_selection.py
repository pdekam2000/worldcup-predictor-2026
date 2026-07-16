"""Train-locked pair selection for forward shadow (gate frozen)."""

from __future__ import annotations

import hashlib
import json
import random
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.two_fixture_forward_shadow.constants import (
    PAIR_SELECTION_STRATEGIES,
    PRIMARY_SELECTION_GATE,
    STRATEGY_VERSION,
)
from worldcup_predictor.research.two_fixture_forward_shadow.ddl import ensure_tfps_schema

ELIGIBLE_SET = {"PORTFOLIO_ELIGIBLE", "PORTFOLIO_PARTIAL_ODDS"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _pair_id(report_date: str, a: int, b: int, strategy: str) -> str:
    lo, hi = sorted([int(a), int(b)])
    raw = f"{report_date}|{lo}|{hi}|{strategy}|{STRATEGY_VERSION}"
    return "pair_" + hashlib.sha256(raw.encode()).hexdigest()[:16]


def _eligible(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        r
        for r in rows
        if r.get("eligibility") in ELIGIBLE_SET and int(r.get("top5_priced_n") or 0) >= 4
    ]


def select_pairs(
    fixtures: list[dict[str, Any]],
    *,
    report_date: str,
    rng: random.Random | None = None,
) -> list[dict[str, Any]]:
    """Return candidate pairs for all strategies; mark primary gate selected=1."""
    rng = rng or random.Random(int(report_date.replace("-", "") or 42))
    elig = _eligible(fixtures)
    out: list[dict[str, Any]] = []
    ts = _utc_now()

    def emit(strategy: str, a: dict, b: dict, rank: int, selected: bool, note: str = "") -> None:
        if int(a["fixture_id"]) == int(b["fixture_id"]):
            return
        joint = float(a["top5_mass"]) * float(b["top5_mass"])
        out.append(
            {
                "pair_id": _pair_id(report_date, a["fixture_id"], b["fixture_id"], strategy),
                "report_date": report_date,
                "fixture_a": int(a["fixture_id"]),
                "fixture_b": int(b["fixture_id"]),
                "selection_strategy": strategy,
                "strategy_version": STRATEGY_VERSION,
                "selection_timestamp_utc": ts,
                "pair_rank": rank,
                "top5_mass_a": a["top5_mass"],
                "top5_mass_b": b["top5_mass"],
                "joint_top5_est": joint,
                "entropy_a": a["entropy"],
                "entropy_b": b["entropy"],
                "league_a": a.get("league"),
                "league_b": b.get("league"),
                "odds_completeness": f"{a['top5_priced_n']}/5|{b['top5_priced_n']}/5",
                "selected": int(selected),
                "rejection_note": note,
                "fixture_a_obj": a,
                "fixture_b_obj": b,
            }
        )

    if len(elig) < 2:
        return out

    # 1 highest_expected_joint
    best = None
    best_j = -1.0
    for i in range(len(elig)):
        for j in range(i + 1, len(elig)):
            jv = float(elig[i]["top5_mass"]) * float(elig[j]["top5_mass"])
            if jv > best_j:
                best_j = jv
                best = (elig[i], elig[j])
    if best:
        emit(
            "highest_expected_joint",
            best[0],
            best[1],
            1,
            PRIMARY_SELECTION_GATE == "highest_expected_joint",
        )

    # 2 highest top5 mass
    ranked = sorted(elig, key=lambda r: -float(r["top5_mass"]))
    if len(ranked) >= 2:
        emit("highest_top5_mass", ranked[0], ranked[1], 1, False)

    # 3 lowest combined entropy
    ranked_e = sorted(elig, key=lambda r: float(r["entropy"]) + float(r.get("entropy") or 0))
    # actually sort by entropy then take top2 lowest
    ranked_e = sorted(elig, key=lambda r: float(r["entropy"]))
    if len(ranked_e) >= 2:
        emit("lowest_combined_entropy", ranked_e[0], ranked_e[1], 1, False)

    # 4 strongest suitability — prefer PORTFOLIO_ELIGIBLE
    order = {"PORTFOLIO_ELIGIBLE": 0, "PORTFOLIO_PARTIAL_ODDS": 1}
    ranked_s = sorted(
        elig,
        key=lambda r: (order.get(r["eligibility"], 9), -float(r["top5_mass"])),
    )
    if len(ranked_s) >= 2:
        emit("strongest_suitability", ranked_s[0], ranked_s[1], 1, False)

    # 5 model/market agreement proxy — prefer higher top5 mass + lower entropy
    ranked_a = sorted(
        elig,
        key=lambda r: (-float(r["top5_mass"]) / max(float(r["entropy"]), 0.1)),
    )
    if len(ranked_a) >= 2:
        emit("highest_model_market_agreement", ranked_a[0], ranked_a[1], 1, False)

    # 6 cross-league
    by_lg: dict[str, list] = {}
    for r in elig:
        by_lg.setdefault(str(r.get("league") or "UNK"), []).append(r)
    lgs = list(by_lg.keys())
    if len(lgs) >= 2:
        a = sorted(by_lg[lgs[0]], key=lambda r: -float(r["top5_mass"]))[0]
        b = sorted(by_lg[lgs[1]], key=lambda r: -float(r["top5_mass"]))[0]
        emit("cross_league_diversified", a, b, 1, False)

    # 7 same-league
    same = [v for v in by_lg.values() if len(v) >= 2]
    if same:
        group = max(same, key=len)
        g = sorted(group, key=lambda r: -float(r["top5_mass"]))
        emit("same_league", g[0], g[1], 1, False)

    # 8 random control
    if len(elig) >= 2:
        a, b = rng.sample(elig, 2)
        emit("random_eligible_control", a, b, 1, False)

    # ensure all strategy names represented in constants
    assert set(PAIR_SELECTION_STRATEGIES) >= {p["selection_strategy"] for p in out}
    return out


def persist_pairs(conn, pairs: list[dict[str, Any]]) -> None:
    ensure_tfps_schema(conn)
    for p in pairs:
        conn.execute(
            """
            INSERT OR IGNORE INTO tfps_pair_candidates (
                pair_id, report_date, fixture_a, fixture_b, selection_strategy,
                strategy_version, selection_timestamp_utc, pair_rank, top5_mass_a,
                top5_mass_b, joint_top5_est, entropy_a, entropy_b, league_a, league_b,
                odds_completeness, selected, rejection_note
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                p["pair_id"],
                p["report_date"],
                p["fixture_a"],
                p["fixture_b"],
                p["selection_strategy"],
                p["strategy_version"],
                p["selection_timestamp_utc"],
                p["pair_rank"],
                p["top5_mass_a"],
                p["top5_mass_b"],
                p["joint_top5_est"],
                p["entropy_a"],
                p["entropy_b"],
                p.get("league_a"),
                p.get("league_b"),
                p.get("odds_completeness"),
                p.get("selected", 0),
                p.get("rejection_note"),
            ),
        )
    conn.commit()


def primary_selected(pairs: list[dict[str, Any]]) -> dict[str, Any] | None:
    for p in pairs:
        if p.get("selected") and p["selection_strategy"] == PRIMARY_SELECTION_GATE:
            return p
    for p in pairs:
        if p["selection_strategy"] == PRIMARY_SELECTION_GATE:
            return p
    return None
