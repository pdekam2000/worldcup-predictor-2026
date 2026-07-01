"""PHASE DATA-1E — Historical odds baseline backtest (research only, no API)."""

from __future__ import annotations

import json
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

MARKETS = (
    "ft_result",
    "btts",
    "over_under",
    "corners_over_under",
    "double_chance",
    "team_over_under",
    "first_half_winner",
)

STRATEGIES = (
    "A_all_selections",
    "B_odds_gte_2",
    "C_odds_gte_3_5",
    "D_odds_3_5_to_12",
    "E_top_odds_per_fixture_market",
    "F_closing_only",
    "G_opening_odds",
    "G_closing_odds",
)

JOIN_SQL = """
    SELECT
        o.id AS odds_id,
        o.registry_fixture_id,
        o.market,
        o.selection,
        o.source_file,
        o.opening_odds,
        o.closing_odds,
        o.league,
        o.season,
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


def _parse_line_selection(selection: str) -> tuple[str, float] | None:
    m = re.match(r"^(over|under)_(\d+)$", selection)
    if not m:
        return None
    return m.group(1), int(m.group(2)) / 10.0


def _team_side_from_source(source_file: str) -> str:
    path = (source_file or "").lower()
    if "home_over_under" in path or "/home_ove" in path:
        return "home"
    if "away_over_under" in path or "/away_ove" in path:
        return "away"
    return "unknown"


def _ou_actual(total: float, side: str, line: float) -> bool:
    if side == "over":
        return total > line
    return total <= line


def evaluate_selection(
    *,
    market: str,
    selection: str,
    source_file: str,
    home_goals: int,
    away_goals: int,
    total_goals: int,
    result_1x2: str,
    btts_actual: int,
    over_15_actual: int,
    over_25_actual: int,
    over_35_actual: int,
    corners_total: int | None,
    ht_home_goals: int | None,
    ht_away_goals: int | None,
) -> bool | None:
    if market == "ft_result":
        if selection not in ("home", "draw", "away"):
            return None
        return selection == result_1x2

    if market == "btts":
        if selection == "yes":
            return bool(btts_actual)
        if selection == "no":
            return not bool(btts_actual)
        return None

    if market == "over_under":
        parsed = _parse_line_selection(selection)
        if not parsed:
            return None
        side, line = parsed
        if line == 1.5:
            actual_over = bool(over_15_actual)
        elif line == 2.5:
            actual_over = bool(over_25_actual)
        elif line == 3.5:
            actual_over = bool(over_35_actual)
        elif line == 4.5:
            actual_over = total_goals > 4.5
        else:
            actual_over = total_goals > line
        return actual_over if side == "over" else not actual_over

    if market == "corners_over_under":
        if corners_total is None:
            return None
        parsed = _parse_line_selection(selection)
        if not parsed:
            return None
        side, line = parsed
        return _ou_actual(float(corners_total), side, line)

    if market == "double_chance":
        if selection == "home_draw":
            return result_1x2 in ("home", "draw")
        if selection == "home_away":
            return result_1x2 in ("home", "away")
        if selection == "draw_away":
            return result_1x2 in ("draw", "away")
        return None

    if market == "team_over_under":
        team_side = _team_side_from_source(source_file)
        if team_side == "unknown":
            return None
        team_goals = home_goals if team_side == "home" else away_goals
        parsed = _parse_line_selection(selection)
        if not parsed:
            return None
        side, line = parsed
        return _ou_actual(float(team_goals), side, line)

    if market == "first_half_winner":
        if ht_home_goals is None or ht_away_goals is None:
            return None
        if ht_home_goals > ht_away_goals:
            actual = "home"
        elif ht_away_goals > ht_home_goals:
            actual = "away"
        else:
            actual = "draw"
        return selection == actual

    return None


def odds_band(odds: float) -> str:
    if odds < 2.0:
        return "lt_2_00"
    if odds < 3.5:
        return "2_00_to_3_49"
    if odds <= 12.0:
        return "3_50_to_12_00"
    return "gt_12_00"


@dataclass
class BetAccumulator:
    bets: int = 0
    wins: int = 0
    staked: float = 0.0
    returned: float = 0.0
    odds_sum: float = 0.0
    skipped: int = 0

    def add(self, won: bool, odds: float) -> None:
        self.bets += 1
        self.staked += 1.0
        self.odds_sum += odds
        if won:
            self.wins += 1
            self.returned += odds

    def skip(self) -> None:
        self.skipped += 1

    def to_metrics(self) -> dict[str, Any]:
        if self.bets == 0:
            return {
                "bets": 0,
                "wins": 0,
                "hit_rate_pct": None,
                "avg_odds": None,
                "roi_pct": None,
                "profit": 0.0,
                "skipped": self.skipped,
            }
        profit = self.returned - self.staked
        return {
            "bets": self.bets,
            "wins": self.wins,
            "hit_rate_pct": round(100.0 * self.wins / self.bets, 4),
            "avg_odds": round(self.odds_sum / self.bets, 4),
            "roi_pct": round(100.0 * profit / self.staked, 4),
            "profit": round(profit, 4),
            "skipped": self.skipped,
        }


@dataclass
class BacktestState:
    dataset_rows: int = 0
    evaluable_rows: int = 0
    unevaluable_rows: int = 0
    strategies: dict[str, BetAccumulator] = field(default_factory=dict)
    by_market: dict[str, dict[str, BetAccumulator]] = field(default_factory=dict)
    by_league: dict[str, dict[str, BetAccumulator]] = field(default_factory=dict)
    by_season: dict[str, dict[str, BetAccumulator]] = field(default_factory=dict)
    by_odds_band: dict[str, dict[str, BetAccumulator]] = field(default_factory=dict)
    by_selection: dict[str, dict[str, BetAccumulator]] = field(default_factory=dict)
    top_odds_candidates: dict[tuple[int, str], tuple[float, bool, str, str | None, str | None, str]] = field(
        default_factory=dict
    )

    def __post_init__(self) -> None:
        for s in STRATEGIES:
            self.strategies[s] = BetAccumulator()

    def _acc(self, bucket: dict[str, dict[str, BetAccumulator]], key: str, strategy: str) -> BetAccumulator:
        if key not in bucket:
            bucket[key] = {s: BetAccumulator() for s in STRATEGIES}
        return bucket[key][strategy]

    def record(
        self,
        *,
        strategy: str,
        won: bool,
        odds: float,
        market: str,
        league: str | None,
        season: str | None,
        selection: str,
    ) -> None:
        self.strategies[strategy].add(won, odds)
        self._acc(self.by_market, market, strategy).add(won, odds)
        self._acc(self.by_league, league or "unknown", strategy).add(won, odds)
        self._acc(self.by_season, season or "unknown", strategy).add(won, odds)
        self._acc(self.by_odds_band, odds_band(odds), strategy).add(won, odds)
        sel_key = f"{market}:{selection}"
        self._acc(self.by_selection, sel_key, strategy).add(won, odds)


def _pick_odds(row: dict[str, Any], *, closing_only: bool, opening_only: bool) -> float | None:
    closing = row.get("closing_odds")
    opening = row.get("opening_odds")
    if closing_only:
        return float(closing) if closing and float(closing) >= 1.0 else None
    if opening_only:
        return float(opening) if opening and float(opening) >= 1.0 else None
    if closing and float(closing) >= 1.0:
        return float(closing)
    if opening and float(opening) >= 1.0:
        return float(opening)
    return None


def _strategy_filters(strategy: str, odds: float) -> bool:
    if strategy == "A_all_selections":
        return True
    if strategy == "B_odds_gte_2":
        return odds >= 2.0
    if strategy == "C_odds_gte_3_5":
        return odds >= 3.5
    if strategy == "D_odds_3_5_to_12":
        return 3.5 <= odds <= 12.0
    if strategy == "F_closing_only":
        return True
    if strategy in ("G_opening_odds", "G_closing_odds"):
        return True
    return False


def iter_backtest_rows(conn: sqlite3.Connection, batch_size: int = 50000) -> Iterator[dict[str, Any]]:
    cur = conn.execute(JOIN_SQL)
    while True:
        batch = cur.fetchmany(batch_size)
        if not batch:
            break
        for row in batch:
            yield dict(row)


def run_baseline_backtest(conn: sqlite3.Connection) -> BacktestState:
    state = BacktestState()

    for row in iter_backtest_rows(conn):
        state.dataset_rows += 1
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
            state.unevaluable_rows += 1
            continue
        state.evaluable_rows += 1

        closing = _pick_odds(row, closing_only=False, opening_only=False)
        closing_only_odds = _pick_odds(row, closing_only=True, opening_only=False)
        opening_odds = _pick_odds(row, closing_only=False, opening_only=True)

        for strategy in STRATEGIES:
            if strategy == "E_top_odds_per_fixture_market":
                if closing is None:
                    state.strategies[strategy].skip()
                    continue
                key = (int(row["registry_fixture_id"]), str(row["market"]))
                prev = state.top_odds_candidates.get(key)
                if prev is None or closing > prev[0]:
                    state.top_odds_candidates[key] = (
                        closing,
                        bool(won),
                        str(row["market"]),
                        row.get("league"),
                        row.get("season"),
                        str(row["selection"]),
                    )
                continue

            if strategy == "F_closing_only":
                odds = closing_only_odds
            elif strategy == "G_opening_odds":
                odds = opening_odds
            elif strategy == "G_closing_odds":
                odds = closing_only_odds
            else:
                odds = closing

            if odds is None:
                state.strategies[strategy].skip()
                continue
            if not _strategy_filters(strategy, odds):
                continue

            state.record(
                strategy=strategy,
                won=bool(won),
                odds=odds,
                market=str(row["market"]),
                league=row.get("league"),
                season=row.get("season"),
                selection=str(row["selection"]),
            )

    # finalize strategy E
    for (_registry_id, _market), (odds, won, market, league, season, selection) in state.top_odds_candidates.items():
        state.record(
            strategy="E_top_odds_per_fixture_market",
            won=won,
            odds=odds,
            market=market,
            league=league,
            season=season,
            selection=selection,
        )

    return state


def summarize_state(state: BacktestState) -> dict[str, Any]:
    def acc_map(acc: dict[str, BetAccumulator]) -> dict[str, Any]:
        return {k: v.to_metrics() for k, v in acc.items()}

    def nested_map(nested: dict[str, dict[str, BetAccumulator]]) -> dict[str, Any]:
        return {k: acc_map(v) for k, v in nested.items()}

    primary = state.strategies["A_all_selections"].to_metrics()
    opening_vs_closing = {
        "opening": state.strategies["G_opening_odds"].to_metrics(),
        "closing": state.strategies["G_closing_odds"].to_metrics(),
        "delta_roi_pct": None,
    }
    o_roi = opening_vs_closing["opening"].get("roi_pct")
    c_roi = opening_vs_closing["closing"].get("roi_pct")
    if o_roi is not None and c_roi is not None:
        opening_vs_closing["delta_roi_pct"] = round(c_roi - o_roi, 4)

    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "dataset": {
            "join_rows": state.dataset_rows,
            "evaluable_rows": state.evaluable_rows,
            "unevaluable_rows": state.unevaluable_rows,
            "expected_join_rows": 2062130,
        },
        "strategies": {s: state.strategies[s].to_metrics() for s in STRATEGIES},
        "opening_vs_closing": opening_vs_closing,
        "primary_strategy_A": primary,
        "by_market": nested_map(state.by_market),
        "by_league_top20": dict(
            sorted(
                ((k, acc_map(v)) for k, v in state.by_league.items()),
                key=lambda x: x[1].get("A_all_selections", {}).get("bets", 0),
                reverse=True,
            )[:20]
        ),
        "by_season": nested_map(state.by_season),
        "by_odds_band": nested_map(state.by_odds_band),
        "by_selection_top30": dict(
            sorted(
                ((k, acc_map(v)) for k, v in state.by_selection.items()),
                key=lambda x: x[1].get("A_all_selections", {}).get("bets", 0),
                reverse=True,
            )[:30]
        ),
    }


def backup_artifact(path: Path, backup_dir: Path) -> Path | None:
    if not path.is_file():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    dest = backup_dir / f"{path.stem}_{stamp}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


def validate_roi_math(won: bool, odds: float) -> dict[str, float]:
    staked = 1.0
    returned = odds if won else 0.0
    profit = returned - staked
    roi_pct = 100.0 * profit / staked
    return {"staked": staked, "returned": returned, "profit": profit, "roi_pct": roi_pct}


__all__ = [
    "MARKETS",
    "STRATEGIES",
    "BetAccumulator",
    "evaluate_selection",
    "run_baseline_backtest",
    "summarize_state",
    "validate_roi_math",
    "backup_artifact",
]
