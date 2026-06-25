"""Probe Sportmonks fixture payloads for pressure-related data."""

from __future__ import annotations

from typing import Any


def _pressure_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    pr = data.get("pressure")
    if isinstance(pr, list):
        return [r for r in pr if isinstance(r, dict)]
    return []


def probe_fixture_pressure(data: dict[str, Any]) -> dict[str, Any]:
    rows = _pressure_rows(data)
    minutes: set[int] = set()
    participants: set[int] = set()
    values: list[float] = []
    duplicate_keys: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()

    for row in rows:
        minute = row.get("minute")
        pid = row.get("participant_id")
        if minute is not None:
            try:
                minutes.add(int(minute))
            except (TypeError, ValueError):
                pass
        if pid is not None:
            try:
                participants.add(int(pid))
            except (TypeError, ValueError):
                pass
        pv = row.get("pressure")
        if pv is not None:
            try:
                values.append(float(pv))
            except (TypeError, ValueError):
                pass
        if minute is not None and pid is not None:
            try:
                key = (int(minute), int(pid))
                if key in seen:
                    duplicate_keys.append(key)
                seen.add(key)
            except (TypeError, ValueError):
                pass

    stats_types: set[str] = set()
    dangerous_attacks = 0
    for st in data.get("statistics") or []:
        if not isinstance(st, dict):
            continue
        tb = st.get("type") or {}
        if isinstance(tb, dict):
            name = str(tb.get("name") or tb.get("developer_name") or "")
            stats_types.add(name)
            if "dangerous" in name.lower() and "attack" in name.lower():
                dangerous_attacks += 1

    return {
        "has_pressure_block": bool(rows),
        "pressure_row_count": len(rows),
        "unique_minutes": len(minutes),
        "unique_participants": len(participants),
        "minute_min": min(minutes) if minutes else None,
        "minute_max": max(minutes) if minutes else None,
        "pressure_value_min": round(min(values), 4) if values else None,
        "pressure_value_max": round(max(values), 4) if values else None,
        "pressure_value_mean": round(sum(values) / len(values), 4) if values else None,
        "duplicate_minute_participant_pairs": len(duplicate_keys),
        "has_statistics": bool(data.get("statistics")),
        "has_dangerous_attacks_stat": dangerous_attacks > 0,
        "statistics_type_count": len(stats_types),
        "has_events": bool(data.get("events")),
        "state_id": data.get("state_id"),
        "league_id": data.get("league_id"),
        "season_id": data.get("season_id"),
        "fixture_id": data.get("id"),
    }
