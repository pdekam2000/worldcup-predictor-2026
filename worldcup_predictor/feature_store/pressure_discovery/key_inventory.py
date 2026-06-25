"""Recursive JSON key inventory for pressure payloads."""

from __future__ import annotations

from typing import Any


def recursive_keys(obj: Any, prefix: str = "", *, max_depth: int = 8) -> list[str]:
    if max_depth <= 0:
        return []
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            keys.append(path)
            keys.extend(recursive_keys(v, path, max_depth=max_depth - 1))
    elif isinstance(obj, list) and obj:
        keys.extend(recursive_keys(obj[0], f"{prefix}[]", max_depth=max_depth - 1))
    return keys


def build_pressure_key_inventory(samples: list[dict[str, Any]]) -> dict[str, Any]:
    """Merge key paths from multiple fixture pressure blocks."""
    all_keys: set[str] = set()
    pressure_row_keys: set[str] = set()
    for sample in samples:
        for path in recursive_keys(sample.get("fixture_data") or {}):
            all_keys.add(path)
        for row in sample.get("pressure_rows") or []:
            if isinstance(row, dict):
                for k in row.keys():
                    pressure_row_keys.add(k)
                    all_keys.add(f"pressure[].{k}")

    return {
        "fixture_top_level_keys": sorted(
            {k.split(".")[0] for k in all_keys if k and not k.startswith("pressure")}
        ),
        "pressure_row_field_keys": sorted(pressure_row_keys),
        "all_key_paths": sorted(all_keys),
        "sample_count": len(samples),
    }
