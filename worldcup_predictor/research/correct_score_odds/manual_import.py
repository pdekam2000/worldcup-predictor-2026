"""Owner-assisted Correct Score odds import (never silent OCR acceptance)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.research.correct_score_odds.ddl import ensure_correct_score_odds_schema
from worldcup_predictor.research.correct_score_odds.mapping import parse_selection
from worldcup_predictor.research.correct_score_odds.store import insert_lines


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def preview_manual_rows(
    *,
    fixture_id: int,
    home_team: str,
    away_team: str,
    bookmaker_name: str,
    capture_timestamp_utc: str,
    settlement_scope: str,
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Build a confirmation preview. Nothing is persisted until confirm_manual_import.
    """
    parsed = []
    errors = []
    for r in rows:
        meta = parse_selection(str(r.get("selection") or ""))
        try:
            odd = float(r.get("decimal_odds"))
        except Exception:
            odd = None
        if meta is None or odd is None or odd <= 1:
            errors.append({"row": r, "reason": "invalid_selection_or_odds"})
            continue
        parsed.append(
            {
                "selection": meta["selection"],
                "home_goals": meta["home_goals"],
                "away_goals": meta["away_goals"],
                "decimal_odds": odd,
                "market": meta["market"],
            }
        )
    return {
        "odds_kind": "manual_owner_confirmed",
        "api_fetched": False,
        "requires_owner_confirmation": True,
        "fixture_id": fixture_id,
        "home_team": home_team,
        "away_team": away_team,
        "home_away_order_note": f"Scores are HOME-AWAY for {home_team} vs {away_team}",
        "bookmaker_name": bookmaker_name,
        "capture_timestamp_utc": capture_timestamp_utc,
        "settlement_scope": settlement_scope,
        "parsed_rows": parsed,
        "errors": errors,
        "ready_to_confirm": bool(parsed) and not errors and settlement_scope == "90_MINUTES",
    }


def confirm_manual_import(
    conn,
    preview: dict[str, Any],
    *,
    owner_confirmed: bool,
    raw_image_path: str | None = None,
) -> dict[str, Any]:
    """Persist only after explicit owner_confirmed=True."""
    ensure_correct_score_odds_schema(conn)
    if not owner_confirmed:
        return {"status": "rejected", "reason": "owner_confirmation_required"}
    if preview.get("settlement_scope") != "90_MINUTES":
        return {"status": "rejected", "reason": "settlement_scope_must_be_90_MINUTES"}
    if not preview.get("ready_to_confirm"):
        return {"status": "rejected", "reason": "preview_not_ready"}

    now = _utc_now()
    conn.execute(
        """
        INSERT INTO correct_score_odds_manual_imports (
            fixture_id, bookmaker_name, capture_timestamp_utc, settlement_scope,
            owner_confirmed, confirmed_at_utc, raw_image_path, rows_json, odds_kind, created_at_utc
        ) VALUES (?, ?, ?, ?, 1, ?, ?, ?, 'manual_owner_confirmed', ?)
        """,
        (
            int(preview["fixture_id"]),
            str(preview["bookmaker_name"]),
            str(preview["capture_timestamp_utc"]),
            "90_MINUTES",
            now,
            raw_image_path,
            json.dumps(preview["parsed_rows"]),
            now,
        ),
    )
    lines = []
    for r in preview["parsed_rows"]:
        lines.append(
            {
                "fixture_id": int(preview["fixture_id"]),
                "provider_fixture_id": str(preview["fixture_id"]),
                "bookmaker_id": None,
                "bookmaker_name": str(preview["bookmaker_name"]),
                "market": r["market"],
                "selection": r["selection"],
                "home_goals": r["home_goals"],
                "away_goals": r["away_goals"],
                "decimal_odds": float(r["decimal_odds"]),
                "raw_odds_format": "decimal",
                "fetched_at_utc": str(preview["capture_timestamp_utc"]),
                "valid_from_utc": None,
                "kickoff_utc": None,
                "prematch_status": "prematch",
                "settlement_scope": "90_MINUTES",
                "provider": "manual_owner_import",
                "source_hash": f"manual|{preview['fixture_id']}|{r['selection']}|{r['decimal_odds']}|{preview['capture_timestamp_utc']}",
                "payload_reference": raw_image_path or "manual_no_image",
                "snapshot_id": None,
                "is_complete_market": 0,
                "is_fresh": 1,
                "odds_age_seconds": None,
                "currency": None,
                "minimum_stake": None,
                "maximum_stake": None,
                "market_status": "open",
                "ingestion_run_id": f"manual_{now}",
                "odds_kind": "manual_owner_confirmed",
                "created_at_utc": now,
            }
        )
    # hash truncate
    import hashlib

    for ln in lines:
        ln["source_hash"] = hashlib.sha256(ln["source_hash"].encode()).hexdigest()[:40]
    ins, ded = insert_lines(conn, lines)
    conn.commit()
    return {
        "status": "ok",
        "odds_kind": "manual_owner_confirmed",
        "api_fetched": False,
        "lines_inserted": ins,
        "lines_deduped": ded,
    }
