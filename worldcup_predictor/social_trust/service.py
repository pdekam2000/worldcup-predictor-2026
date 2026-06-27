"""Social sharing service — Phase A20."""

from __future__ import annotations

from typing import Any

from worldcup_predictor.social_trust.constants import DISCLAIMER, OG_IMAGE_DEFAULT
from worldcup_predictor.social_trust.sanitize import (
    sanitize_combo_payload,
    sanitize_paper_report_payload,
    sanitize_pick_payload,
    sanitize_plan_payload,
)
from worldcup_predictor.social_trust.store import SocialShareStore
from worldcup_predictor.social_trust.trust_stats import build_public_accuracy_trust


def _share_response(row: dict[str, Any], *, path_prefix: str) -> dict[str, Any]:
    sid = row.get("share_id")
    return {
        "status": "ok",
        "share_id": sid,
        "share_path": f"/share/{path_prefix}/{sid}",
        "og": {
            "title": row.get("og_title"),
            "description": row.get("og_description"),
            "image": OG_IMAGE_DEFAULT,
        },
    }


def _og_for_pick(payload: dict[str, Any]) -> tuple[str, str]:
    home = payload.get("home_team") or "Home"
    away = payload.get("away_team") or "Away"
    market = payload.get("market_label") or payload.get("market") or "Pick"
    pred = payload.get("prediction") or ""
    q = payload.get("bet_quality_score")
    qtxt = f" · Q{int(q)}" if q is not None else ""
    title = f"{home} vs {away} — {market}"
    desc = f"AI pick: {pred}{qtxt}. {DISCLAIMER}"
    return title, desc


def _og_for_combo(payload: dict[str, Any]) -> tuple[str, str]:
    label = payload.get("label") or payload.get("combo_type") or "Combo"
    legs = len(payload.get("legs") or [])
    title = f"AI Combo — {label}"
    desc = f"{legs}-leg combo tip. {DISCLAIMER}"
    return title, desc


def _og_for_paper(payload: dict[str, Any]) -> tuple[str, str]:
    month = payload.get("month") or "Monthly"
    roi = payload.get("roi_pct")
    pl = payload.get("net_profit_loss")
    title = f"Virtual betting report — {month}"
    desc = f"Anonymized paper portfolio"
    if roi is not None:
        desc += f" · ROI {roi}%"
    if pl is not None:
        desc += f" · P/L {pl:+.2f}"
    desc += f". {DISCLAIMER}"
    return title, desc


def create_pick_share(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    payload = sanitize_pick_payload({**data, "disclaimer": DISCLAIMER})
    title, desc = _og_for_pick(payload)
    store = SocialShareStore()
    row = store.create_share(
        share_type="pick",
        payload=payload,
        user_id=user_id,
        og_title=title,
        og_description=desc,
    )
    return _share_response(row, path_prefix="pick")


def create_combo_share(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    payload = sanitize_combo_payload({**data, "disclaimer": DISCLAIMER})
    title, desc = _og_for_combo(payload)
    store = SocialShareStore()
    row = store.create_share(
        share_type="combo",
        payload=payload,
        user_id=user_id,
        og_title=title,
        og_description=desc,
    )
    return _share_response(row, path_prefix="combo")


def create_plan_share(user_id: str, data: dict[str, Any]) -> dict[str, Any]:
    payload = sanitize_plan_payload({**data, "disclaimer": DISCLAIMER})
    date = payload.get("date") or "Today"
    title = f"AI Betting Plan — {date}"
    desc = f"Daily singles and combos. {DISCLAIMER}"
    store = SocialShareStore()
    row = store.create_share(
        share_type="betting_plan",
        payload=payload,
        user_id=user_id,
        og_title=title,
        og_description=desc,
    )
    return _share_response(row, path_prefix="plan")


def create_paper_report_share(user_id: str, data: dict[str, Any], *, opt_in: bool) -> dict[str, Any]:
    if not opt_in:
        return {"status": "error", "message": "Paper betting share requires explicit opt-in."}
    payload = sanitize_paper_report_payload({**data, "disclaimer": DISCLAIMER})
    title, desc = _og_for_paper(payload)
    store = SocialShareStore()
    row = store.create_share(
        share_type="paper_report",
        payload=payload,
        user_id=user_id,
        og_title=title,
        og_description=desc,
        opt_in=True,
    )
    return _share_response(row, path_prefix="paper-report")


def get_share(share_id: str, *, expected_type: str | None = None) -> dict[str, Any]:
    store = SocialShareStore()
    row = store.get_share(share_id)
    if not row:
        return {"status": "error", "message": "Share not found or expired"}
    if expected_type and row.get("share_type") != expected_type:
        return {"status": "error", "message": "Invalid share type"}
    trust = build_public_accuracy_trust()
    return {
        "status": "ok",
        "share": row,
        "og": {
            "title": row.get("og_title"),
            "description": row.get("og_description"),
            "image": OG_IMAGE_DEFAULT,
            "type": "article",
        },
        "trust": {
            "accuracy_30d_pct": trust.get("accuracy_30d_pct"),
            "evaluated_predictions": trust.get("evaluated_predictions"),
            "best_market": trust.get("best_market"),
            "data_available": trust.get("data_available"),
        },
    }


def get_public_accuracy() -> dict[str, Any]:
    trust = build_public_accuracy_trust()
    return {"status": "ok", "accuracy": trust}
