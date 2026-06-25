"""Pressure data quality scoring (0–100 per league)."""

from __future__ import annotations

from typing import Any


def score_fixture_quality(probe: dict[str, Any]) -> dict[str, Any]:
    """Score a single fixture pressure probe 0–100."""
    if not probe.get("has_pressure_block"):
        return {"quality_score": 0, "issues": ["no_pressure_block"]}

    score = 100.0
    issues: list[str] = []

    rows = int(probe.get("pressure_row_count") or 0)
    minutes = int(probe.get("unique_minutes") or 0)
    if rows == 0:
        return {"quality_score": 0, "issues": ["empty_pressure"]}

    if minutes < 30:
        score -= 25
        issues.append("low_minute_coverage")
    elif minutes < 60:
        score -= 10
        issues.append("partial_minute_coverage")

    avg_rows_per_minute = rows / max(minutes, 1)
    if avg_rows_per_minute < 1.5:
        score -= 15
        issues.append("missing_participant_rows")

    dups = int(probe.get("duplicate_minute_participant_pairs") or 0)
    if dups > 0:
        score -= min(20, dups * 2)
        issues.append(f"duplicate_rows:{dups}")

    pmax = probe.get("pressure_value_max")
    if pmax is not None and float(pmax) > 100:
        score -= 10
        issues.append("outlier_pressure_max")

    if probe.get("minute_min") is None:
        score -= 5
        issues.append("missing_minute_field")

    return {"quality_score": max(0, round(score, 1)), "issues": issues}


def aggregate_league_quality(probes: list[dict[str, Any]]) -> dict[str, Any]:
    if not probes:
        return {"quality_score": 0, "fixture_count": 0, "with_pressure": 0}

    scores = []
    with_pressure = 0
    for p in probes:
        if p.get("has_pressure_block"):
            with_pressure += 1
        q = score_fixture_quality(p)
        scores.append(q["quality_score"])

    return {
        "quality_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "fixture_count": len(probes),
        "with_pressure": with_pressure,
        "avg_unique_minutes": round(
            sum(int(p.get("unique_minutes") or 0) for p in probes if p.get("has_pressure_block"))
            / max(with_pressure, 1),
            1,
        ),
        "avg_rows_per_fixture": round(
            sum(int(p.get("pressure_row_count") or 0) for p in probes if p.get("has_pressure_block"))
            / max(with_pressure, 1),
            1,
        ),
    }
