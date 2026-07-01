"""
SMC Strategy — Signal Generator (v3)
======================================
Decoupled sweep registration from zone matching.

Entry Logic
-----------
Phase 1 — Sweep detected at bar i:
  - Record pending bull/bear setup with stop level
  - No zone pre-filtering at this point

Phase 2 — Forward retest (bars i+1 … i+confirmation_bars):
  - For each active pending setup, scan ALL active zones of matching
    direction that sit above the stop (bull) or below the stop (bear)
  - Enter when bar overlaps with the nearest zone

This gives many more entry opportunities than the previous strict zone
filtering at the sweep bar.

Filters
-------
- Minimum risk filter: skip trades where risk < min_risk_pct × entry
- Zone must not be mitigated (price already closed through it)
- Zone age capped at max_zone_age bars
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def generate_signals(
    df: pd.DataFrame,
    bull_obs: list[dict],
    bear_obs: list[dict],
    bull_fvgs: list[dict],
    bear_fvgs: list[dict],
    pair: str = "UNKNOWN",
    rr_ratio: float = 2.0,
    confirmation_bars: int = 10,
    stop_buffer_pct: float = 0.0002,
    min_risk_pct: float = 0.0003,   # 0.03% of entry price minimum risk
    max_zone_age: int = 120,
) -> list[dict[str, Any]]:
    """
    Generate SMC trade signals from annotated DataFrame + zone registries.
    """
    signals: list[dict[str, Any]] = []
    n = len(df)

    # Tag zones with type
    for z in bull_obs:  z.setdefault("type", "OB")
    for z in bear_obs:  z.setdefault("type", "OB")
    for z in bull_fvgs: z.setdefault("type", "FVG")
    for z in bear_fvgs: z.setdefault("type", "FVG")

    # All live zones
    all_bull_zones = bull_obs + bull_fvgs
    all_bear_zones = bear_obs + bear_fvgs

    # Pending setups after sweeps
    # { 'sweep_bar', 'stop', 'expires', 'triggered': bool }
    pending_bull: list[dict] = []
    pending_bear: list[dict] = []

    # Track which (setup, zone) combinations we've already fired to prevent duplicates
    fired_bull: set[tuple[int, int]] = set()  # (sweep_bar, zone id)
    fired_bear: set[tuple[int, int]] = set()

    for i in range(5, n):
        bar   = df.iloc[i]
        close = float(bar["close"])
        low_i = float(bar["low"])
        high_i = float(bar["high"])

        # ── Mitigate zones when price closes inside them ──────────────
        for z in all_bull_zones:
            if not z["mitigated"] and z["bot"] <= close <= z["top"]:
                z["mitigated"] = True
        for z in all_bear_zones:
            if not z["mitigated"] and z["bot"] <= close <= z["top"]:
                z["mitigated"] = True

        # ── Register new BULLISH sweep ────────────────────────────────
        if bar["liq_sweep_bull"] and not np.isnan(bar["swept_low"]):
            swept_low = float(bar["swept_low"])
            buf       = close * stop_buffer_pct
            stop      = swept_low - buf
            pending_bull.append({
                "sweep_bar": i,
                "swept_low": swept_low,
                "stop":      stop,
                "expires":   i + confirmation_bars,
            })

        # ── Register new BEARISH sweep ────────────────────────────────
        if bar["liq_sweep_bear"] and not np.isnan(bar["swept_high"]):
            swept_high = float(bar["swept_high"])
            buf        = close * stop_buffer_pct
            stop       = swept_high + buf
            pending_bear.append({
                "sweep_bar":  i,
                "swept_high": swept_high,
                "stop":       stop,
                "expires":    i + confirmation_bars,
            })

        # ── Check LONG entries from active bull setups ────────────────
        live_pb = []
        for setup in pending_bull:
            if i > setup["expires"]:
                continue
            stop = setup["stop"]

            # Find zones active at this bar: formed before sweep, not mitigated, above stop
            entry, zone = _find_entry_zone(
                all_bull_zones, setup["sweep_bar"], i,
                stop_level=stop,
                direction="bull",
                max_zone_age=max_zone_age,
                bar_low=low_i,
                bar_high=high_i,
            )
            key = (setup["sweep_bar"], id(zone) if zone else -1)

            if entry is not None and zone is not None and key not in fired_bull:
                risk = entry - stop
                min_r = entry * min_risk_pct
                if risk >= min_r:
                    target = entry + risk * rr_ratio
                    signals.append(_make_signal(
                        i, df, pair, "long", entry, stop, target, risk, zone["type"]
                    ))
                    fired_bull.add(key)
                    zone["mitigated"] = True
            else:
                live_pb.append(setup)
        pending_bull = live_pb

        # ── Check SHORT entries from active bear setups ───────────────
        live_pb = []
        for setup in pending_bear:
            if i > setup["expires"]:
                continue
            stop = setup["stop"]

            entry, zone = _find_entry_zone(
                all_bear_zones, setup["sweep_bar"], i,
                stop_level=stop,
                direction="bear",
                max_zone_age=max_zone_age,
                bar_low=low_i,
                bar_high=high_i,
            )
            key = (setup["sweep_bar"], id(zone) if zone else -1)

            if entry is not None and zone is not None and key not in fired_bear:
                risk = stop - entry
                min_r = entry * min_risk_pct
                if risk >= min_r:
                    target = entry - risk * rr_ratio
                    signals.append(_make_signal(
                        i, df, pair, "short", entry, stop, target, risk, zone["type"]
                    ))
                    fired_bear.add(key)
                    zone["mitigated"] = True
            else:
                live_pb.append(setup)
        pending_bear = live_pb

    return signals


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _find_entry_zone(
    zones: list[dict],
    sweep_bar: int,
    current_bar: int,
    stop_level: float,
    direction: str,
    max_zone_age: int,
    bar_low: float,
    bar_high: float,
) -> tuple[float | None, dict | None]:
    """
    Find the best active zone that the current bar is touching.

    Priority: OB zones preferred over FVG zones (higher quality in SMC).
    For 'bull': zone must be above stop_level, formed before sweep_bar.
    For 'bear': zone must be below stop_level, formed before sweep_bar.
    Returns (entry_price, zone) or (None, None).
    """
    ob_match  = (None, None, float("inf"))  # (entry, zone, dist)
    fvg_match = (None, None, float("inf"))

    for z in zones:
        if z["mitigated"]:
            continue
        age = current_bar - z["bar"]
        if age < 0 or age > max_zone_age:
            continue
        if z["bar"] > sweep_bar:
            continue

        z_top = z["top"]
        z_bot = z["bot"]
        z_mid = (z_top + z_bot) / 2

        if bar_low <= z_top and bar_high >= z_bot:
            entry = z_mid
            valid = (
                (direction == "bull" and entry > stop_level) or
                (direction == "bear" and entry < stop_level)
            )
            if not valid:
                continue

            dist = abs(entry - bar_low) if direction == "bull" else abs(bar_high - entry)
            z_type = z.get("type", "FVG")

            if z_type == "OB" and dist < ob_match[2]:
                ob_match = (entry, z, dist)
            elif z_type == "FVG" and dist < fvg_match[2]:
                fvg_match = (entry, z, dist)

    # Prefer OB over FVG
    if ob_match[0] is not None:
        return ob_match[0], ob_match[1]
    if fvg_match[0] is not None:
        return fvg_match[0], fvg_match[1]
    return None, None


def _make_signal(
    bar_idx: int,
    df: pd.DataFrame,
    pair: str,
    side: str,
    entry: float,
    stop: float,
    target: float,
    risk: float,
    source: str,
) -> dict[str, Any]:
    pip_factor = 10000 if entry < 10 else (100 if entry < 1000 else 1)
    return {
        "bar_idx":   bar_idx,
        "timestamp": df.index[bar_idx],
        "pair":      pair,
        "side":      side,
        "entry":     round(entry, 5),
        "stop":      round(stop, 5),
        "target":    round(target, 5),
        "risk_pips": round(risk * pip_factor, 1),
        "source":    source,
    }
