"""Mean-reversion strategy improvement research — Phase MR-1 (research only).

Three concrete techniques tested against the historical odds baseline:

  1. CLV filter (Closing Line Value)
     Beat the closing line → sharp money confirms your direction.
     Entry at opening odds > closing odds (CLV ≥ 0) indicates the market
     later moved your way, which is a quality signal even for mean-reversion
     bets that appear "counter-trend" on longer time-frames.

  2. Calibration-bucket filter
     Phase 56A identified specific market/odds-bucket combinations with
     persistent calibration gaps (real hit-rate >> or << implied probability).
     Filtering to these "known-edge" buckets improves entry quality without
     touching the trend axis at all.

  3. Dynamic Kelly stake scaling
     Replace binary bet/no-bet with a stake fraction proportional to the
     estimated bucket-level edge. Counter-trend but well-calibrated buckets
     get a partial stake rather than full exclusion.

All three can be stacked.  The combined strategy is labelled
``MR_COMBINED`` in the output.

Research only — no deployment, no API calls, no production writes.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from worldcup_predictor.research.historical_odds_baseline_backtest import (
    _pick_odds,
    evaluate_selection,
)
from worldcup_predictor.research.historical_odds_roi_forensics import (
    FORENSICS_JOIN_SQL,
    ProfitAccumulator,
    iter_forensics_rows,
    _max_drawdown,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "phase_mr1_mean_reversion_improvement"

# ---------------------------------------------------------------------------
# Phase 56A calibration-gap lookup
# Source: PHASE_56A_MARKET_BEHAVIOR_INTELLIGENCE_REPORT.md
# Format: (market, selection, odds_lo, odds_hi) → known_gap_pct
# Positive gap  → selection is underpriced by market (bet direction confirmed)
# Negative gap  → selection is overpriced (avoid)
# ---------------------------------------------------------------------------
CALIBRATION_BUCKETS: list[tuple[str, str, float, float, float]] = [
    # (market,         selection, odds_lo, odds_hi, gap_pct)
    ("match_winner",  "home",    2.40,    2.50,    43.80),   # home strongly underpriced
    ("over_under",    "over_2_5", 11.00,  999.0,   42.72),   # big long-shot under bias
    ("match_winner",  "home",    1.90,    2.00,    42.61),
    ("match_winner",  "home",    2.50,    2.60,    36.89),
    ("over_under",    "over_2_5", 7.00,   7.10,    34.10),
    ("match_winner",  "home",    3.80,    3.90,    32.15),
    ("match_winner",  "home",    2.30,    2.40,    30.32),
    # Overpriced selections to avoid (negative gap)
    ("over_under",    "under_2_5", 1.10,  1.20,   -39.25),
    ("over_under",    "under_2_5", 1.50,  1.60,   -33.69),
    ("over_under",    "over_2_5",  1.30,  1.40,   -31.89),
    ("match_winner",  "draw",    3.10,    3.20,   -29.39),
    ("match_winner",  "draw",    2.80,    2.90,   -25.66),
]

# Minimum bucket gap to treat as an "advantage bucket"
MIN_POSITIVE_GAP = 20.0   # %
MIN_STAKE_FRACTION = 0.25  # never go below 25 % of base stake


# Historical CSV data uses 'ft_result'; Phase 56A odds-snapshot data uses 'match_winner'.
# The calibration buckets are keyed on the odds-snapshot naming convention.
_MARKET_ALIAS: dict[str, str] = {
    "ft_result": "match_winner",
    "1x2": "match_winner",
}


def _normalise_market(market: str) -> str:
    return _MARKET_ALIAS.get(market.lower(), market.lower())


def _normalise_selection(market: str, selection: str) -> str:
    """Map raw selection strings to the Phase 56A naming convention.

    Historical CSV data encodes over/under selections as e.g. ``over_25``
    (line × 10, no decimal separator). Phase 56A uses ``over_2_5`` (with
    underscore as decimal point). This function converts between the two.

    Examples::

        over_25  → over_2_5
        under_15 → under_1_5
        under_35 → under_3_5
    """
    import re as _re

    sel = selection.lower()
    if market in ("over_under", "team_over_under"):
        # Match patterns like "over_25", "under_35", "over_45" etc.
        m = _re.match(r"^(over|under)_(\d)(\d)$", sel)
        if m:
            side, whole, frac = m.group(1), m.group(2), m.group(3)
            return f"{side}_{whole}_{frac}"
    return sel


def lookup_calibration(market: str, selection: str, odds: float) -> float | None:
    """Return the known calibration gap (%) for this market/selection/odds combo.

    Returns None when no bucket matches (unknown territory).
    Returns a negative value for overpriced selections.
    """
    mkt_norm = _normalise_market(market)
    sel_norm = _normalise_selection(market, selection)
    for mkt, sel, lo, hi, gap in CALIBRATION_BUCKETS:
        if mkt == mkt_norm and sel == sel_norm and lo <= odds <= hi:
            return gap
    return None


# ---------------------------------------------------------------------------
# CLV helpers
# ---------------------------------------------------------------------------

def clv(opening: float | None, closing: float | None) -> float | None:
    """Closing Line Value = (1/close) - (1/open).

    Convention: positive CLV means your entry odds were *higher* than the
    closing odds, i.e. you beat the closing line.

    - open_odds > close_odds  →  market shortened  →  CLV > 0  (sharp money
      confirmed the bet by pushing the line down; you had value).
    - open_odds < close_odds  →  market lengthened →  CLV < 0  (market moved
      against your direction; lower-quality entry).
    - None  →  either odds unavailable.
    """
    if opening is None or closing is None:
        return None
    if opening < 1.01 or closing < 1.01:
        return None
    return round(1.0 / closing - 1.0 / opening, 6)


# ---------------------------------------------------------------------------
# Stake scaling
# ---------------------------------------------------------------------------

def kelly_stake_fraction(
    gap_pct: float | None,
    *,
    clv_value: float | None,
    base_fraction: float = 1.0,
) -> float:
    """Return a stake multiplier in [0, 1.0].

    Rules (dynamic Kelly without hard exclusions):
    1. Known negative gap (overpriced bucket) → 0.0 stake (skip).
    2. Known positive gap → scale by magnitude.
    3. Unknown bucket → MIN_STAKE_FRACTION (cautious minimum).
    4. Positive CLV adds a confidence boost (+10 % fraction).
    """
    # Overpriced buckets: no stake even in dynamic mode
    if gap_pct is not None and gap_pct < 0:
        return 0.0

    fraction = MIN_STAKE_FRACTION  # default: unknown territory

    if gap_pct is not None:
        if gap_pct >= 35:
            fraction = 1.00
        elif gap_pct >= 25:
            fraction = 0.75
        elif gap_pct >= MIN_POSITIVE_GAP:
            fraction = 0.50
        else:
            fraction = MIN_STAKE_FRACTION

    # CLV positive → confidence boost (up to +10 % extra fraction)
    if clv_value is not None and clv_value > 0:
        fraction = min(1.0, fraction + 0.10)

    return round(fraction * base_fraction, 4)


# ---------------------------------------------------------------------------
# Weighted accumulator
# ---------------------------------------------------------------------------

@dataclass
class WeightedAccumulator:
    """Tracks weighted-stake bets."""
    bets: int = 0
    staked: float = 0.0
    returned: float = 0.0
    profits: list[float] = field(default_factory=list)
    skipped_clv: int = 0
    skipped_calib: int = 0

    def add(self, won: bool, odds: float, stake: float) -> None:
        self.bets += 1
        self.staked += stake
        p = stake * (odds - 1.0) if won else -stake
        self.returned += (stake * odds) if won else 0.0
        self.profits.append(p)

    def metrics(self) -> dict[str, Any]:
        if self.bets == 0:
            return {
                "bets": 0,
                "staked": 0.0,
                "roi_pct": None,
                "skipped_clv": self.skipped_clv,
                "skipped_calib": self.skipped_calib,
            }
        profit = self.returned - self.staked
        roi = 100.0 * profit / self.staked if self.staked else None

        wins = sum(1 for p in self.profits if p > 0)
        mean_p = profit / self.bets
        var = max(
            0.0,
            sum((p - mean_p) ** 2 for p in self.profits) / self.bets
        )
        std = math.sqrt(var)
        se = std / math.sqrt(self.bets)
        return {
            "bets": self.bets,
            "wins": wins,
            "staked": round(self.staked, 2),
            "profit": round(profit, 2),
            "roi_pct": round(roi, 2) if roi is not None else None,
            "hit_rate_pct": round(100.0 * wins / self.bets, 2),
            "roi_ci95_low": round((mean_p - 1.96 * se) * 100.0, 2),
            "roi_ci95_high": round((mean_p + 1.96 * se) * 100.0, 2),
            "max_drawdown_units": round(_max_drawdown(self.profits), 2),
            "skipped_clv": self.skipped_clv,
            "skipped_calib": self.skipped_calib,
        }


# ---------------------------------------------------------------------------
# Strategy definitions
# ---------------------------------------------------------------------------

STRATEGIES = (
    "baseline_D",           # same as historical strategy D: odds 3.5–12, flat stake
    "MR_CLV_filter",        # baseline_D + CLV ≥ 0 required
    "MR_calib_filter",      # baseline_D + calibration bucket must be positive
    "MR_dynamic_kelly",     # baseline_D + scaled stake by gap/CLV (no hard exclusions)
    "MR_combined",          # CLV ≥ 0 AND positive calib bucket AND dynamic stake
)


# ---------------------------------------------------------------------------
# Main backtest loop
# ---------------------------------------------------------------------------

@dataclass
class MRBacktestState:
    accs: dict[str, WeightedAccumulator] = field(default_factory=dict)
    rows_seen: int = 0
    rows_evaluated: int = 0

    def __post_init__(self) -> None:
        for s in STRATEGIES:
            self.accs[s] = WeightedAccumulator()


def run_mr_backtest(conn: sqlite3.Connection) -> MRBacktestState:
    state = MRBacktestState()

    for row in iter_forensics_rows(conn):
        state.rows_seen += 1

        won = evaluate_selection(
            market=str(row.get("market") or ""),
            selection=str(row.get("selection") or ""),
            source_file=str(row.get("source_file") or ""),
            home_goals=int(row.get("home_goals") or 0),
            away_goals=int(row.get("away_goals") or 0),
            total_goals=int(row.get("total_goals") or 0),
            result_1x2=str(row.get("result_1x2") or ""),
            btts_actual=int(row.get("btts_actual") or 0),
            over_15_actual=int(row.get("over_15_actual") or 0),
            over_25_actual=int(row.get("over_25_actual") or 0),
            over_35_actual=int(row.get("over_35_actual") or 0),
            corners_total=row.get("corners_total"),
            ht_home_goals=row.get("ht_home_goals"),
            ht_away_goals=row.get("ht_away_goals"),
        )
        if won is None:
            continue

        state.rows_evaluated += 1

        odds = _pick_odds(row, closing_only=False, opening_only=False)
        if odds is None or not (3.5 <= odds <= 12.0):
            continue  # all strategies share this baseline gate

        opening = row.get("opening_odds")
        closing_raw = row.get("closing_odds")
        open_f = float(opening) if opening and float(opening) >= 1.01 else None
        close_f = float(closing_raw) if closing_raw and float(closing_raw) >= 1.01 else None

        market = str(row.get("market") or "")
        selection = str(row.get("selection") or "")
        clv_val = clv(open_f, close_f)
        gap = lookup_calibration(market, selection, odds)

        # ---- Strategy: baseline_D (flat stake 1.0) ----
        state.accs["baseline_D"].add(bool(won), odds, 1.0)

        # ---- Strategy: MR_CLV_filter ----
        # Require CLV ≥ 0; skip when CLV unavailable or negative
        if clv_val is None or clv_val < 0:
            state.accs["MR_CLV_filter"].skipped_clv += 1
        else:
            state.accs["MR_CLV_filter"].add(bool(won), odds, 1.0)

        # ---- Strategy: MR_calib_filter ----
        # Require known positive gap bucket; skip overpriced or unknown
        if gap is None or gap < MIN_POSITIVE_GAP:
            state.accs["MR_calib_filter"].skipped_calib += 1
        else:
            state.accs["MR_calib_filter"].add(bool(won), odds, 1.0)

        # ---- Strategy: MR_dynamic_kelly ----
        # No hard exclusions; stake = f(gap, CLV)
        frac = kelly_stake_fraction(gap, clv_value=clv_val)
        state.accs["MR_dynamic_kelly"].add(bool(won), odds, frac)

        # ---- Strategy: MR_combined ----
        # CLV ≥ 0 AND positive gap bucket, with dynamic stake
        if clv_val is None or clv_val < 0:
            state.accs["MR_combined"].skipped_clv += 1
        elif gap is None or gap < MIN_POSITIVE_GAP:
            state.accs["MR_combined"].skipped_calib += 1
        else:
            frac_comb = kelly_stake_fraction(gap, clv_value=clv_val)
            state.accs["MR_combined"].add(bool(won), odds, frac_comb)

    return state


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def build_report(state: MRBacktestState) -> dict[str, Any]:
    strategies_out: dict[str, Any] = {}
    for s in STRATEGIES:
        strategies_out[s] = state.accs[s].metrics()

    baseline = strategies_out["baseline_D"]
    improvements: dict[str, Any] = {}
    for s in STRATEGIES:
        if s == "baseline_D":
            continue
        m = strategies_out[s]
        delta = None
        if m.get("roi_pct") is not None and baseline.get("roi_pct") is not None:
            delta = round(m["roi_pct"] - baseline["roi_pct"], 2)
        improvements[s] = {
            "delta_roi_vs_baseline_pct": delta,
            "trade_count": m.get("bets"),
            "roi_pct": m.get("roi_pct"),
        }

    # Calibration bucket catalogue (for reference)
    bucket_catalogue = [
        {
            "market": mkt,
            "selection": sel,
            "odds_range": f"{lo}–{hi}",
            "calibration_gap_pct": gap,
            "direction": "underpriced" if gap > 0 else "overpriced",
        }
        for mkt, sel, lo, hi, gap in CALIBRATION_BUCKETS
    ]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "disclaimer": "Research only — not betting advice.",
        "description": (
            "Mean-reversion strategy improvement: three complementary techniques "
            "tested against Strategy-D baseline (odds 3.5–12). "
            "See PHASE_56A for calibration source data."
        ),
        "rows_seen": state.rows_seen,
        "rows_evaluated": state.rows_evaluated,
        "strategies": strategies_out,
        "improvement_vs_baseline": improvements,
        "calibration_bucket_catalogue": bucket_catalogue,
        "technique_summary": {
            "CLV_filter": (
                "Only enter when closing odds ≤ opening odds (CLV ≥ 0). "
                "Positive CLV signals sharp-money confirmation of your entry price."
            ),
            "calibration_bucket_filter": (
                "Only enter in known-advantage odds buckets (Phase 56A gap ≥ 20 pp). "
                "Avoids systematically overpriced selections without blocking all counter-trend bets."
            ),
            "dynamic_kelly_scaling": (
                "Replace flat 1-unit bet with a stake proportional to the bucket edge magnitude "
                f"(range {int(MIN_STAKE_FRACTION*100)}%–100%). No positions fully blocked; "
                "low-confidence segments get small stake rather than exclusion."
            ),
            "combined": (
                "CLV ≥ 0 AND positive calibration bucket, with full Kelly-scaled stake. "
                "Tightest filter; expected to raise ROI at the cost of trade count."
            ),
        },
    }


def write_report(report: dict[str, Any]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / "mr1_improvement_report.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    return out


def run(db_path: str | Path) -> dict[str, Any]:
    """Entry point: runs the full backtest and returns the report dict."""
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        state = run_mr_backtest(conn)
    finally:
        conn.close()
    return build_report(state)


__all__ = [
    "run",
    "run_mr_backtest",
    "build_report",
    "write_report",
    "lookup_calibration",
    "clv",
    "kelly_stake_fraction",
    "CALIBRATION_BUCKETS",
    "STRATEGIES",
]
