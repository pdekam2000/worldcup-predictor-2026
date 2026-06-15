"""Phase 55 — probe API-Football sidelined endpoint availability (no hacks if unavailable)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_PROBE_FILENAME = "sidelined_endpoint_probe.json"


def _probe_path(cache_dir: Path | str) -> Path:
    return Path(cache_dir) / _PROBE_FILENAME


def load_sidelined_probe(cache_dir: Path | str) -> dict[str, Any] | None:
    path = _probe_path(cache_dir)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_sidelined_probe(cache_dir: Path | str, result: dict[str, Any]) -> None:
    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _probe_path(cache_dir).write_text(json.dumps(result, indent=2), encoding="utf-8")


def probe_sidelined_endpoint(
    api: Any,
    *,
    cache_dir: Path | str,
    team_id: int | None = None,
) -> dict[str, Any]:
    """
    One-time probe — stores result in cache dir.
    Returns {available: bool, reason: str, plan_blocked: bool}.
    """
    cached = load_sidelined_probe(cache_dir)
    if cached is not None:
        return cached

    if not getattr(api, "is_configured", False):
        result = {"available": False, "reason": "API not configured", "plan_blocked": False}
        save_sidelined_probe(cache_dir, result)
        return result

    tid = team_id or 25  # Germany fallback for probe
    try:
        call = api.get_sidelined(team_id=tid, probe_only=True)
        err = (call.error or "").lower()
        if call.ok:
            result = {
                "available": True,
                "reason": "Endpoint reachable via team param",
                "plan_blocked": False,
                "sample_count": len(call.data) if isinstance(call.data, list) else 0,
            }
        elif "plan" in err or "subscription" in err or "access" in err or "not allowed" in err:
            result = {"available": False, "reason": call.error or "Plan does not include sidelined", "plan_blocked": True}
        elif call.error:
            result = {"available": False, "reason": call.error, "plan_blocked": False}
        else:
            result = {"available": True, "reason": "Endpoint reachable (empty response ok)", "plan_blocked": False, "sample_count": 0}
    except Exception as exc:
        logger.debug("Sidelined probe failed: %s", exc)
        result = {"available": False, "reason": str(exc), "plan_blocked": False}

    save_sidelined_probe(cache_dir, result)
    return result


def normalize_sidelined(raw: list[Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        player = item.get("player") or {}
        team = item.get("team") or {}
        name = str(player.get("name") or item.get("name") or "")
        if not name:
            continue
        reason = str(item.get("reason") or item.get("type") or "Sidelined")
        rows.append(
            {
                "team": {"id": team.get("id"), "name": team.get("name")},
                "player": {
                    "name": name,
                    "id": player.get("id"),
                    "type": "Suspended" if "suspend" in reason.lower() else "Missing Fixture",
                    "reason": reason,
                },
            }
        )
    return rows


def sidelined_enabled(cache_dir: Path | str) -> bool:
    probe = load_sidelined_probe(cache_dir)
    return bool(probe and probe.get("available"))
