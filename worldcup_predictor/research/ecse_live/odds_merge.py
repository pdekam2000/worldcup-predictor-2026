"""PHASE ECSE-LIVE-1 — Merge provider odds into ECSE lambda feature row."""

from __future__ import annotations

import re
from typing import Any

from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    normalize_snapshot_odds_lines,
    parse_snapshot_payload,
)
from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row

PHASE = "ECSE-LIVE-1"


def _set_if_missing(row: dict[str, Any], key: str, value: float | None) -> None:
    if value is None or value < 1.0:
        return
    if row.get(key) is None:
        row[key] = float(value)


def _parse_decimal(value: Any) -> float | None:
    try:
        num = float(value)
        return num if num >= 1.0 else None
    except (TypeError, ValueError):
        return None


def oddalerts_history_to_ecse_row(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Map OddAlerts odds/history rows to ecse_training_dataset-style columns."""
    out: dict[str, Any] = {}
    correct_score: dict[str, float] = {}

    for row in rows:
        market = str(row.get("market_key") or row.get("market") or "").lower()
        selection = str(row.get("outcome") or row.get("selection") or "").lower().strip()
        closing = _parse_decimal(row.get("closing")) or _parse_decimal(row.get("opening")) or _parse_decimal(row.get("peak"))
        if closing is None:
            continue

        if market in {"ft_result", "match_odds", "1x2", "fulltime_result"}:
            if selection in {"home", "1"}:
                _set_if_missing(out, "ft_home_closing", closing)
            elif selection in {"draw", "x"}:
                _set_if_missing(out, "ft_draw_closing", closing)
            elif selection in {"away", "2"}:
                _set_if_missing(out, "ft_away_closing", closing)
        elif "over" in market and "2.5" in market:
            if "over" in selection:
                _set_if_missing(out, "ou_over_25_closing", closing)
            elif "under" in selection:
                _set_if_missing(out, "ou_under_25_closing", closing)
        elif "over" in market and "1.5" in market:
            if "over" in selection:
                _set_if_missing(out, "ou_over_15_closing", closing)
            elif "under" in selection:
                _set_if_missing(out, "ou_under_15_closing", closing)
        elif "over" in market and "3.5" in market:
            if "over" in selection:
                _set_if_missing(out, "ou_over_35_closing", closing)
            elif "under" in selection:
                _set_if_missing(out, "ou_under_35_closing", closing)
        elif market in {"btts", "both_teams_to_score"}:
            if selection in {"yes", "btts_yes"}:
                _set_if_missing(out, "btts_yes_closing", closing)
            elif selection in {"no", "btts_no"}:
                _set_if_missing(out, "btts_no_closing", closing)
        elif "correct" in market or "exact" in market:
            label = selection.replace(":", "-").strip()
            if re.match(r"^\d+-\d+$", label):
                correct_score[label] = closing

    if correct_score:
        out["correct_score_odds"] = correct_score
    return out


def api_football_odds_to_ecse_row(payload: Any, *, fixture_id: int | None = None) -> dict[str, Any]:
    """Parse API-Football odds response into ECSE row."""
    if isinstance(payload, list) and payload:
        payload = payload[0]
    bookmakers = []
    if isinstance(payload, dict):
        bookmakers = payload.get("bookmakers") or []
        if not bookmakers and payload.get("response"):
            resp = payload["response"]
            if isinstance(resp, list) and resp:
                bookmakers = resp[0].get("bookmakers") or []

    lines = normalize_snapshot_odds_lines({"bookmakers": bookmakers}, fixture_id=fixture_id)
    row: dict[str, Any] = {}
    if lines:
        from worldcup_predictor.research.ecse_live.prediction_builder import (  # noqa: PLC0415
            _is_ou_line,
            _pick_odd,
        )

        def mw(name: str, _sel: str) -> bool:
            n = name.lower()
            return n in {"match winner", "1x2", "match result", "home/draw/away"}

        def mw_sel(sel: str, key: str) -> bool:
            return sel.lower().strip() == key

        row = {
            "ft_home_closing": _pick_odd(lines, mw, lambda s: mw_sel(s, "home")),
            "ft_draw_closing": _pick_odd(lines, mw, lambda s: mw_sel(s, "draw")),
            "ft_away_closing": _pick_odd(lines, mw, lambda s: mw_sel(s, "away")),
            "ou_over_25_closing": _pick_odd(
                lines,
                lambda n, s: _is_ou_line(n, s, "2.5") and "over" in s.lower(),
                lambda _s: True,
            ),
            "ou_under_25_closing": _pick_odd(
                lines,
                lambda n, s: _is_ou_line(n, s, "2.5") and "under" in s.lower(),
                lambda _s: True,
            ),
            "ou_over_15_closing": _pick_odd(
                lines,
                lambda n, s: _is_ou_line(n, s, "1.5") and "over" in s.lower(),
                lambda _s: True,
            ),
            "ou_under_15_closing": _pick_odd(
                lines,
                lambda n, s: _is_ou_line(n, s, "1.5") and "under" in s.lower(),
                lambda _s: True,
            ),
            "ou_over_35_closing": _pick_odd(
                lines,
                lambda n, s: _is_ou_line(n, s, "3.5") and "over" in s.lower(),
                lambda _s: True,
            ),
            "ou_under_35_closing": _pick_odd(
                lines,
                lambda n, s: _is_ou_line(n, s, "3.5") and "under" in s.lower(),
                lambda _s: True,
            ),
            "btts_yes_closing": _pick_odd(
                lines,
                lambda n, _s: "both teams" in n.lower() or n.lower() == "btts",
                lambda s: s.lower().strip() in {"yes", "btts: yes"},
            ),
            "btts_no_closing": _pick_odd(
                lines,
                lambda n, _s: "both teams" in n.lower() or n.lower() == "btts",
                lambda s: s.lower().strip() in {"no", "btts: no"},
            ),
        }
        correct_score: dict[str, float] = {}
        for line in lines:
            n = line.market_name.lower()
            if "correct score" not in n and "exact score" not in n:
                continue
            label = line.selection.replace(":", "-").strip()
            if re.match(r"^\d+-\d+$", label):
                correct_score[label] = float(line.odd)
        if correct_score:
            row["correct_score_odds"] = correct_score

    implied = parse_snapshot_payload({"bookmakers": bookmakers}, fixture_id=fixture_id)
    row["_implied"] = implied
    return {k: v for k, v in row.items() if v is not None}


def merge_ecse_odds_rows(*rows: dict[str, Any]) -> dict[str, Any]:
    """Merge provider rows — first non-null wins per ECSE column."""
    merged: dict[str, Any] = {}
    correct_scores: dict[str, float] = {}
    providers_used: list[str] = []

    for row in rows:
        if not row:
            continue
        src = row.get("_provider")
        if src:
            providers_used.append(str(src))
        for key, value in row.items():
            if key.startswith("_"):
                continue
            if key == "correct_score_odds" and isinstance(value, dict):
                for sl, odd in value.items():
                    correct_scores.setdefault(sl, odd)
                continue
            if merged.get(key) is None and value is not None:
                merged[key] = value

    if correct_scores:
        merged["correct_score_odds"] = correct_scores
    merged["_providers_merged"] = providers_used
    return merged


def sqlite_odds_row(conn, fixture_id: int) -> dict[str, Any]:
    row = build_odds_feature_row(conn, fixture_id) or {}
    if row:
        row["_provider"] = "sqlite_odds_snapshots"
    return row
