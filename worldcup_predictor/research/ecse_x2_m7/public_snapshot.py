"""PHASE ECSE-X2-M7 — Public ECSE output snapshots (before/after enablement)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_match_display import build_ecse_fixture_display
from worldcup_predictor.research.ecse_x2_m2.prob_features import load_fixture_records
from worldcup_predictor.research.ecse_x2_m4.segment import classify_match_state


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def pick_sample_fixture_ids(conn: sqlite3.Connection, *, min_count: int = 5) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()

    snap_rows = conn.execute(
        """
        SELECT fixture_id FROM ecse_prediction_snapshots
        ORDER BY kickoff_utc DESC
        LIMIT 20
        """
    ).fetchall()
    for row in snap_rows:
        fid = int(row["fixture_id"])
        if fid not in seen:
            seen.add(fid)
            ids.append(fid)

    records = load_fixture_records(conn)
    home_fav_added = 0
    for rec in sorted(records, key=lambda r: r.get("kickoff_unix") or 0, reverse=True):
        if len(ids) >= min_count + 3:
            break
        fid = int(rec["registry_fixture_id"])
        if fid in seen:
            continue
        h = rec["probs"].get("ft_home")
        state = classify_match_state(rec["probs"])
        if state == "home_favorite" and h is not None and h >= 0.55:
            seen.add(fid)
            ids.append(fid)
            home_fav_added += 1

    for rec in records:
        if len(ids) >= min_count:
            break
        fid = int(rec["registry_fixture_id"])
        if fid not in seen:
            seen.add(fid)
            ids.append(fid)

    return ids[: max(min_count, len(ids))]


def capture_public_output_snapshot(
    conn: sqlite3.Connection,
    fixture_ids: list[int] | None = None,
) -> dict[str, Any]:
    fixture_ids = fixture_ids or pick_sample_fixture_ids(conn)
    fixtures: list[dict[str, Any]] = []
    for fid in fixture_ids:
        display = build_ecse_fixture_display(conn, fid)
        fixtures.append(
            {
                "fixture_id": fid,
                "available": display.get("available"),
                "top_scores": display.get("top_scores"),
                "top_1": (display.get("top_scores") or [{}])[0].get("scoreline")
                if display.get("top_scores")
                else None,
                "lambda": display.get("lambda"),
                "registry_fixture_id": display.get("registry_fixture_id"),
                "display_version": display.get("display_version"),
            }
        )
    return {
        "fixture_count": len(fixtures),
        "fixtures": fixtures,
    }


def save_snapshot(payload: dict[str, Any], path: str | Path) -> Path:
    out = _repo_root() / path
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return out


def compare_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_map = {int(f["fixture_id"]): f for f in before.get("fixtures") or []}
    after_map = {int(f["fixture_id"]): f for f in after.get("fixtures") or []}
    unchanged = 0
    changed = 0
    details: list[dict[str, Any]] = []
    for fid, b in before_map.items():
        a = after_map.get(fid)
        if not a:
            details.append({"fixture_id": fid, "status": "missing_after"})
            continue
        same = json.dumps(b.get("top_scores"), sort_keys=True) == json.dumps(
            a.get("top_scores"), sort_keys=True
        )
        if same:
            unchanged += 1
            details.append({"fixture_id": fid, "status": "unchanged", "top_1": b.get("top_1")})
        else:
            changed += 1
            details.append(
                {
                    "fixture_id": fid,
                    "status": "changed",
                    "before_top_1": b.get("top_1"),
                    "after_top_1": a.get("top_1"),
                }
            )
    return {
        "compared": len(before_map),
        "unchanged": unchanged,
        "changed": changed,
        "public_output_unchanged": changed == 0,
        "details": details,
    }
