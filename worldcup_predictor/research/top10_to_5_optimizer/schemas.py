"""Schema validation helpers (lightweight, research-only)."""

from __future__ import annotations

from typing import Any


def validate_fixture_input(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if doc.get("fixture_id") is None:
        errors.append("missing_fixture_id")
    tops = doc.get("top10") or doc.get("canonical") or doc.get("scores")
    if not tops:
        errors.append("missing_top10")
    return errors


def validate_odds_doc(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    st = str(doc.get("source_type") or "")
    if not st:
        errors.append("missing_source_type")
    if not doc.get("markets"):
        errors.append("missing_markets")
    return errors
