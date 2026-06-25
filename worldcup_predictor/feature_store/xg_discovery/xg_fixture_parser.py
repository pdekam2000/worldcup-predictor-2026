"""
Shared Sportmonks xG fixture parser (Phase 54F-4).

Handles all known xGFixture response shapes. Type-id-first classification:
  5304 -> xg, 5305 -> xgot. Never maps Shots On Target (86) to xgot.
"""

from __future__ import annotations

from typing import Any

# Licensed expected-goals family type IDs (Sportmonks v3)
_XG_TYPE_MAP: dict[int, str] = {
    5304: "xg",
    5305: "xgot",
    7939: "xpts",
    7940: "xg_penalties",
    7941: "xg_free_kicks",
    7942: "xg_corners",
    7943: "npxg",
    7944: "xg_set_play",
    7945: "xg_open_play",
    9684: "xgd",
    9685: "shooting_performance",
    9686: "xg_prevented",
    9687: "xga",
}

_KNOWN_XG_TYPE_IDS = frozenset(_XG_TYPE_MAP.keys())

_XG_BLOCK_KEYS: tuple[str, ...] = (
    "xGFixture",
    "xgFixture",
    "xgfixture",
    "XGFixture",
)


def type_id_from_row(row: dict[str, Any]) -> int | None:
    type_id = row.get("type_id")
    if type_id is not None:
        try:
            return int(type_id)
        except (TypeError, ValueError):
            pass
    type_block = row.get("type")
    if isinstance(type_block, dict) and type_block.get("id") is not None:
        try:
            return int(type_block["id"])
        except (TypeError, ValueError):
            return None
    return None


def _type_label_from_row(row: dict[str, Any]) -> str:
    type_block = row.get("type")
    if isinstance(type_block, dict):
        for key in ("developer_name", "code", "name"):
            text = type_block.get(key)
            if text:
                return str(text).lower()
    tid = type_id_from_row(row)
    if tid is not None:
        return _XG_TYPE_MAP.get(tid, f"type_{tid}")
    return ""


def value_from_row(row: dict[str, Any]) -> float | None:
    data = row.get("data")
    if isinstance(data, dict):
        val = data.get("value")
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
    try:
        return float(row.get("value")) if row.get("value") is not None else None
    except (TypeError, ValueError):
        return None


def _rows_from_xg_block(block: Any) -> list[dict[str, Any]]:
    if isinstance(block, dict):
        nested = block.get("expected") or block.get("data")
        if isinstance(nested, list):
            return [r for r in nested if isinstance(r, dict)]
    elif isinstance(block, list):
        return [r for r in block if isinstance(r, dict)]
    return []


def block_has_expected_goals_semantics(block: Any) -> bool:
    for row in _rows_from_xg_block(block):
        tid = type_id_from_row(row)
        if tid in (5304, 5305) or tid in _KNOWN_XG_TYPE_IDS:
            return True
        label = _type_label_from_row(row)
        if "expected goal" in label:
            return True
    return False


def collect_xg_rows_from_object(obj: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    # Prefer canonical xGFixture so coerced lowercase aliases are not double-counted.
    canonical = obj.get("xGFixture")
    if canonical is not None:
        rows.extend(_rows_from_xg_block(canonical))
    else:
        for key in _XG_BLOCK_KEYS[1:]:
            block = obj.get(key)
            if block is not None:
                rows.extend(_rows_from_xg_block(block))
    top = obj.get("expected")
    if isinstance(top, list):
        rows.extend(r for r in top if isinstance(r, dict))
    return rows


def expected_rows_from_fixture(raw: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extract expected-goals rows from any supported fixture payload shape."""
    if not raw or not isinstance(raw, dict):
        return []
    coerced = coerce_fixture_xg_keys(raw)
    return collect_xg_rows_from_object(coerced)


def coerce_fixture_xg_keys(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize lowercase/mixed-case xGFixture keys onto xGFixture when semantic."""
    if any(raw.get(k) is not None for k in _XG_BLOCK_KEYS[:1]):
        return raw
    for key in _XG_BLOCK_KEYS[1:]:
        block = raw.get(key)
        if block is None:
            continue
        if block_has_expected_goals_semantics(block):
            out = dict(raw)
            out["xGFixture"] = block
            for alias in _XG_BLOCK_KEYS[1:]:
                if alias != key:
                    out.pop(alias, None)
            return out
    return raw


def classify_metric_key(row: dict[str, Any]) -> str | None:
    """
    Type-id-first metric classification.

    5304 -> xg, 5305 -> xgot. Unknown type IDs are skipped (not xGoT from Shots On Target).
    """
    tid = type_id_from_row(row)
    if tid is not None:
        if tid in _XG_TYPE_MAP:
            return _XG_TYPE_MAP[tid]
        return None

    label = _type_label_from_row(row)
    if not label:
        return None
    norm = label.replace("_", " ").replace("-", " ").lower()

    if "expected goals on target" in norm or ("expected" in norm and "on target" in norm):
        return "xgot"
    if "expected" in norm and "against" in norm:
        return "xga"
    if norm in {"xg", "xgoals", "expected goals", "expected goals xg"}:
        return "xg"
    if "expected goals" in norm and "on target" not in norm and "against" not in norm:
        return "xg"

    return None


def parse_proof_fixture(raw: dict[str, Any]) -> dict[str, Any]:
    """Audit helper — counts rows by type_id and metric_key."""
    rows = expected_rows_from_fixture(raw)
    by_tid: dict[str, int] = {}
    by_metric: dict[str, int] = {}
    for row in rows:
        tid = type_id_from_row(row)
        if tid is not None:
            by_tid[str(tid)] = by_tid.get(str(tid), 0) + 1
        mk = classify_metric_key(row)
        if mk:
            by_metric[mk] = by_metric.get(mk, 0) + 1
    return {
        "expected_row_count": len(rows),
        "by_type_id": by_tid,
        "by_metric_key": by_metric,
        "has_team_xg": by_metric.get("xg", 0) > 0,
    }
