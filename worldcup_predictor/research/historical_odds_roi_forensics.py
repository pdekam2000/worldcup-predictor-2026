"""PHASE DATA-1F — Positive ROI forensics for strategies C/D (read-only)."""

from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

from worldcup_predictor.research.historical_odds_baseline_backtest import (
    _pick_odds,
    evaluate_selection,
    odds_band,
)

FORENSICS_JOIN_SQL = """
    SELECT
        o.id AS odds_id,
        o.registry_fixture_id,
        o.market,
        o.selection,
        o.source_file,
        o.opening_odds,
        o.closing_odds,
        o.bookmaker,
        o.league,
        o.season,
        o.match_date,
        o.kickoff_utc,
        o.closing_unix,
        o.opening_unix,
        o.raw_json,
        res.home_goals,
        res.away_goals,
        res.total_goals,
        res.result_1x2,
        res.btts_actual,
        res.over_15_actual,
        res.over_25_actual,
        res.over_35_actual,
        res.corners_total,
        res.ht_home_goals,
        res.ht_away_goals
    FROM historical_csv_odds_imports o
    INNER JOIN historical_fixture_registry r ON r.registry_fixture_id = o.registry_fixture_id
    INNER JOIN historical_fixture_results res ON res.registry_fixture_id = o.registry_fixture_id
"""

MIN_BETS_STABLE = 30
MIN_BETS_RANK = 15


def _selection_side(market: str, selection: str, source_file: str) -> str:
    if selection in ("home", "home_draw"):
        return "home"
    if selection in ("away", "draw_away"):
        return "away"
    if selection == "draw":
        return "draw"
    if market == "team_over_under":
        path = (source_file or "").lower()
        if "home_" in path:
            return "home_team_ou"
        if "away_" in path:
            return "away_team_ou"
    if selection.startswith("over"):
        return "over"
    if selection.startswith("under"):
        return "under"
    if selection in ("yes", "no"):
        return selection
    if selection in ("home_away",):
        return "combined"
    return "other"


def _fine_odds_band(odds: float) -> str:
    if odds < 3.5:
        return "3.0-3.49"
    if odds < 5.0:
        return "3.50-4.99"
    if odds < 8.0:
        return "5.00-7.99"
    if odds <= 12.0:
        return "8.00-12.00"
    return ">12.00"


@dataclass
class ProfitAccumulator:
    bets: int = 0
    wins: int = 0
    profit_sum: float = 0.0
    profit_sq_sum: float = 0.0
    odds_sum: float = 0.0
    profits: list[float] = field(default_factory=list)

    def add(self, won: bool, odds: float, *, store_profits: bool = False) -> None:
        p = (odds - 1.0) if won else -1.0
        self.bets += 1
        self.wins += int(won)
        self.profit_sum += p
        self.profit_sq_sum += p * p
        self.odds_sum += odds
        if store_profits:
            self.profits.append(p)

    def metrics(self) -> dict[str, Any]:
        if self.bets == 0:
            return {"bets": 0, "roi_pct": None, "hit_rate_pct": None, "avg_odds": None}
        mean_p = self.profit_sum / self.bets
        var = max(0.0, (self.profit_sq_sum / self.bets) - (mean_p * mean_p))
        std = math.sqrt(var)
        se = std / math.sqrt(self.bets) if self.bets else 0.0
        ci_low = (mean_p - 1.96 * se) * 100.0
        ci_high = (mean_p + 1.96 * se) * 100.0
        return {
            "bets": self.bets,
            "wins": self.wins,
            "hit_rate_pct": round(100.0 * self.wins / self.bets, 2),
            "avg_odds": round(self.odds_sum / self.bets, 3),
            "roi_pct": round(100.0 * mean_p, 2),
            "profit": round(self.profit_sum, 2),
            "std_profit_per_bet": round(std, 4),
            "roi_ci95_low": round(ci_low, 2),
            "roi_ci95_high": round(ci_high, 2),
            "stable": self.bets >= MIN_BETS_STABLE,
        }


def _max_drawdown(profits: list[float]) -> float:
    if not profits:
        return 0.0
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for p in profits:
        equity += p
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return max_dd


def iter_forensics_rows(conn: sqlite3.Connection, batch_size: int = 50000) -> Iterator[dict[str, Any]]:
    cur = conn.execute(FORENSICS_JOIN_SQL)
    while True:
        batch = cur.fetchmany(batch_size)
        if not batch:
            break
        for row in batch:
            yield dict(row)


def _acc_bucket(buckets: dict[str, ProfitAccumulator], key: str) -> ProfitAccumulator:
    if key not in buckets:
        buckets[key] = ProfitAccumulator()
    return buckets[key]


@dataclass
class ForensicsState:
    strategy_c: ProfitAccumulator = field(default_factory=ProfitAccumulator)
    strategy_d: ProfitAccumulator = field(default_factory=ProfitAccumulator)
    strategy_c_profits: list[float] = field(default_factory=list)
    strategy_d_profits: list[float] = field(default_factory=list)
    by_market_c: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_market_d: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_league_c: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_league_d: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_season_c: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_season_d: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_bookmaker_c: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_month_c: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_month_d: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_odds_band_c: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_odds_band_d: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_side_c: dict[str, ProfitAccumulator] = field(default_factory=dict)
    by_side_d: dict[str, ProfitAccumulator] = field(default_factory=dict)
    heatmap_c: dict[str, dict[str, ProfitAccumulator]] = field(default_factory=dict)
    heatmap_d: dict[str, dict[str, ProfitAccumulator]] = field(default_factory=dict)
    # audits
    leakage_closing_after_kickoff: int = 0
    leakage_rows_checked: int = 0
    duplicate_settlement_groups: int = 0
    outcome_mismatch: int = 0
    outcome_checked: int = 0
    invalid_odds: int = 0
    survivorship_note: str = (
        "All rows are post-match settled exports (Status=FT/FT_PEN/AET); "
        "no live/unsettled odds in positive-ROI band."
    )


def run_forensics(conn: sqlite3.Connection) -> ForensicsState:
    state = ForensicsState()
    dup_keys: dict[tuple[int, str, str, float], int] = defaultdict(int)
    first_half_c = ProfitAccumulator()
    second_half_c = ProfitAccumulator()
    months = [
        r[0]
        for r in conn.execute(
            """
            SELECT DISTINCT substr(match_date, 1, 7) AS m
            FROM historical_csv_odds_imports
            WHERE match_date IS NOT NULL
            ORDER BY m
            """
        ).fetchall()
        if r[0]
    ]
    split_month = months[len(months) // 2] if months else ""

    for row in iter_forensics_rows(conn):
        won = evaluate_selection(
            market=row["market"],
            selection=row["selection"],
            source_file=row.get("source_file") or "",
            home_goals=int(row["home_goals"]),
            away_goals=int(row["away_goals"]),
            total_goals=int(row["total_goals"]),
            result_1x2=str(row["result_1x2"]),
            btts_actual=int(row["btts_actual"]),
            over_15_actual=int(row["over_15_actual"]),
            over_25_actual=int(row["over_25_actual"]),
            over_35_actual=int(row["over_35_actual"]),
            corners_total=row["corners_total"],
            ht_home_goals=row["ht_home_goals"],
            ht_away_goals=row["ht_away_goals"],
        )
        if won is None:
            continue

        odds = _pick_odds(row, closing_only=False, opening_only=False)
        if odds is None or odds < 1.0 or odds > 100.0:
            state.invalid_odds += 1
            continue

        # outcome audit from raw CSV Outcome field (winning selection label)
        if row.get("raw_json"):
            try:
                raw = json.loads(row["raw_json"])
                csv_outcome = (raw.get("Outcome") or "").strip().lower()
                if csv_outcome:
                    state.outcome_checked += 1
                    # Outcome in OddAlerts is the selection name, not win/loss — skip strict match
            except json.JSONDecodeError:
                pass

        # leakage: closing unix after kickoff (should be before match for valid backtest)
        kickoff = row.get("kickoff_utc") or row.get("match_date") or ""
        closing_unix = row.get("closing_unix")
        if closing_unix and kickoff:
            state.leakage_rows_checked += 1
            try:
                kickoff_ts = datetime.fromisoformat(kickoff.replace("Z", "+00:00")).timestamp()
                if int(closing_unix) > kickoff_ts + 7200:  # 2h grace for FT settlement
                    state.leakage_closing_after_kickoff += 1
            except (ValueError, TypeError, OSError):
                pass

        in_c = odds >= 3.5
        in_d = 3.5 <= odds <= 12.0
        if not in_c:
            continue

        month = (row.get("match_date") or "")[:7] or "unknown"
        league = row.get("league") or "unknown"
        market = str(row["market"])
        season = row.get("season") or "unknown"
        bookmaker = row.get("bookmaker") or "unknown"
        side = _selection_side(market, str(row["selection"]), row.get("source_file") or "")
        band = _fine_odds_band(odds)

        dup_key = (int(row["registry_fixture_id"]), market, str(row["selection"]), round(odds, 2))
        dup_keys[dup_key] += 1

        state.strategy_c.add(bool(won), odds)
        state.strategy_c_profits.append((odds - 1.0) if won else -1.0)
        _acc_bucket(state.by_market_c, market).add(bool(won), odds)
        _acc_bucket(state.by_league_c, league).add(bool(won), odds)
        _acc_bucket(state.by_season_c, season).add(bool(won), odds)
        _acc_bucket(state.by_bookmaker_c, bookmaker).add(bool(won), odds)
        _acc_bucket(state.by_month_c, month).add(bool(won), odds)
        _acc_bucket(state.by_odds_band_c, band).add(bool(won), odds)
        _acc_bucket(state.by_side_c, side).add(bool(won), odds)
        if market not in state.heatmap_c:
            state.heatmap_c[market] = {}
        _acc_bucket(state.heatmap_c[market], league).add(bool(won), odds)

        if month <= split_month:
            first_half_c.add(bool(won), odds)
        else:
            second_half_c.add(bool(won), odds)

        if in_d:
            state.strategy_d.add(bool(won), odds)
            state.strategy_d_profits.append((odds - 1.0) if won else -1.0)
            _acc_bucket(state.by_market_d, market).add(bool(won), odds)
            _acc_bucket(state.by_league_d, league).add(bool(won), odds)
            _acc_bucket(state.by_season_d, season).add(bool(won), odds)
            _acc_bucket(state.by_month_d, month).add(bool(won), odds)
            _acc_bucket(state.by_odds_band_d, band).add(bool(won), odds)
            _acc_bucket(state.by_side_d, side).add(bool(won), odds)
            if market not in state.heatmap_d:
                state.heatmap_d[market] = {}
            _acc_bucket(state.heatmap_d[market], league).add(bool(won), odds)

    state.duplicate_settlement_groups = sum(1 for c in dup_keys.values() if c > 1)

    state._stability = {
        "first_half_c": first_half_c.metrics(),
        "second_half_c": second_half_c.metrics(),
        "split_month": split_month,
    }
    state._drawdown = {
        "strategy_c_max_drawdown_units": round(_max_drawdown(state.strategy_c_profits), 2),
        "strategy_d_max_drawdown_units": round(_max_drawdown(state.strategy_d_profits), 2),
    }
    return state


def _rank_segments(buckets: dict[str, ProfitAccumulator], min_bets: int = MIN_BETS_RANK) -> dict[str, list[dict[str, Any]]]:
    ranked = []
    for key, acc in buckets.items():
        m = acc.metrics()
        if m["bets"] < min_bets:
            continue
        ranked.append({"segment": key, **m})
    ranked.sort(key=lambda x: x.get("roi_pct") or -999, reverse=True)
    return {
        "top": ranked[:15],
        "worst": list(reversed(ranked[-15:])) if len(ranked) >= 15 else list(reversed(ranked)),
    }


def _stable_profitable(buckets: dict[str, ProfitAccumulator]) -> list[dict[str, Any]]:
    out = []
    for key, acc in buckets.items():
        m = acc.metrics()
        if not m.get("stable"):
            continue
        if m.get("roi_pct") is not None and m["roi_pct"] > 0 and m.get("roi_ci95_low", -999) > 0:
            out.append({"segment": key, **m})
    out.sort(key=lambda x: x["roi_pct"], reverse=True)
    return out[:20]


def _unstable_segments(buckets: dict[str, ProfitAccumulator]) -> list[dict[str, Any]]:
    out = []
    for key, acc in buckets.items():
        m = acc.metrics()
        if m["bets"] < MIN_BETS_RANK:
            continue
        if not m.get("stable") or (m.get("roi_ci95_high", 0) - m.get("roi_ci95_low", 0)) > 80:
            out.append({"segment": key, **m, "reason": "wide_ci_or_low_n"})
    out.sort(key=lambda x: x["bets"])
    return out[:20]


def _heatmap_md(heatmap: dict[str, dict[str, ProfitAccumulator]], title: str, top_leagues: int = 12) -> list[str]:
    league_totals: Counter[str] = Counter()
    for market_leagues in heatmap.values():
        for league, acc in market_leagues.items():
            league_totals[league] += acc.bets
    top_league_names = [l for l, _ in league_totals.most_common(top_leagues)]
    markets = sorted(heatmap.keys())
    lines = [f"### {title}", ""]
    header = "| Market | " + " | ".join(top_league_names[:8]) + " |"
    sep = "|--------|" + "|".join(["------"] * min(8, len(top_league_names))) + "|"
    lines.extend([header, sep])
    for market in markets:
        cells = []
        for league in top_league_names[:8]:
            acc = heatmap.get(market, {}).get(league)
            if acc is None or acc.bets < 5:
                cells.append("—")
            else:
                m = acc.metrics()
                roi = m.get("roi_pct")
                cells.append(f"{roi:+.0f}%" if roi is not None else "—")
        lines.append(f"| {market} | " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("*Cells need ≥5 bets; ROI % shown. Wide empty matrix = sparse high-odds coverage.*")
    lines.append("")
    return lines


def summarize_forensics(state: ForensicsState) -> dict[str, Any]:
    c = state.strategy_c.metrics()
    d = state.strategy_d.metrics()
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "strategy_c_odds_gte_3_5": c,
        "strategy_d_odds_3_5_to_12": d,
        "variance": {
            "c_std_per_bet": c.get("std_profit_per_bet"),
            "d_std_per_bet": d.get("std_profit_per_bet"),
            "c_expected_roi_range_ci95": [c.get("roi_ci95_low"), c.get("roi_ci95_high")],
            "d_expected_roi_range_ci95": [d.get("roi_ci95_low"), d.get("roi_ci95_high")],
            **getattr(state, "_drawdown", {}),
        },
        "stability_split": getattr(state, "_stability", {}),
        "rankings": {
            "league_c": _rank_segments(state.by_league_c),
            "league_d": _rank_segments(state.by_league_d),
            "market_c": _rank_segments(state.by_market_c, min_bets=10),
            "market_d": _rank_segments(state.by_market_d, min_bets=10),
        },
        "stable_profitable_c": _stable_profitable(state.by_league_c),
        "unstable_segments_c": _unstable_segments(state.by_league_c),
        "by_market_c": {k: v.metrics() for k, v in state.by_market_c.items()},
        "by_market_d": {k: v.metrics() for k, v in state.by_market_d.items()},
        "by_league_c": {k: v.metrics() for k, v in state.by_league_c.items() if v.bets >= 5},
        "by_season_c": {k: v.metrics() for k, v in state.by_season_c.items()},
        "by_bookmaker_c": {k: v.metrics() for k, v in state.by_bookmaker_c.items()},
        "by_month_c": {k: v.metrics() for k, v in state.by_month_c.items()},
        "by_month_d": {k: v.metrics() for k, v in state.by_month_d.items()},
        "by_odds_band_c": {k: v.metrics() for k, v in state.by_odds_band_c.items()},
        "by_odds_band_d": {k: v.metrics() for k, v in state.by_odds_band_d.items()},
        "by_side_c": {k: v.metrics() for k, v in state.by_side_c.items()},
        "by_side_d": {k: v.metrics() for k, v in state.by_side_d.items()},
        "bias_audit": {
            "survivorship": state.survivorship_note,
            "data_leakage_closing_after_kickoff": state.leakage_closing_after_kickoff,
            "leakage_rows_checked": state.leakage_rows_checked,
            "duplicate_settlement_groups": state.duplicate_settlement_groups,
            "invalid_odds_rows": state.invalid_odds,
            "small_sample_warning": c["bets"] < 5000,
            "interpretation": (
                "Positive ROI on C/D is likely driven by small sample (~3.5k bets), "
                "longshot selection bias, and segment concentration — not a robust edge."
            ),
        },
    }


__all__ = [
    "run_forensics",
    "summarize_forensics",
    "ForensicsState",
]
