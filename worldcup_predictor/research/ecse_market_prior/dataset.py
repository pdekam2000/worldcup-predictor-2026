"""Canonical market-prior dataset from external_historical_csv_raw_rows."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_market_prior.probability_space import (
    favorite_frame_probs,
    favorite_result,
    margin_normalized_probs,
    normalize_favorite_score,
    winning_margin,
)
from worldcup_predictor.research.ecse_market_prior.segments import competition_segment
from worldcup_predictor.research.ecse_market_prior.types import FavResult, FavSide, MarketPriorRow

PHASE = "ECSE-MARKET-PRIOR-SHADOW-1"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        v = float(value)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _parse_goals(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        g = int(float(value))
        return g if g >= 0 else None
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip()
    return text[:10] if len(text) >= 10 else text or None


def row_from_raw_json(row_hash: str, source_file: str, raw: dict[str, Any]) -> MarketPriorRow | None:
    oh = _parse_float(raw.get("oddsFT_1"))
    od = _parse_float(raw.get("oddsFT_X"))
    oa = _parse_float(raw.get("oddsFT_2"))
    hg = _parse_goals(raw.get("goalsHomeFullTime"))
    ag = _parse_goals(raw.get("goalsAwayFullTime"))
    if oh is None or od is None or oa is None or hg is None or ag is None:
        return None

    fixture_date = _parse_date(raw.get("eventDate"))
    if not fixture_date:
        return None

    p_h, p_d, p_a = margin_normalized_probs(oh, od, oa)
    fav_side, p_fav, p_draw_fav, p_dog, (pf, pd, pu) = favorite_frame_probs(oh, od, oa)
    league = str(raw.get("league") or "")
    country = str(raw.get("countryName") or "")
    segment = competition_segment(league, source_file, country)
    event_hour = str(raw.get("eventHour") or "").strip()
    kickoff = f"{fixture_date}T{event_hour}" if event_hour else fixture_date
    total = hg + ag

    return MarketPriorRow(
        row_hash=row_hash,
        fixture_date=fixture_date,
        kickoff_utc=kickoff,
        league=league,
        country=country,
        source_file=source_file,
        home_team=str(raw.get("homeTeam") or ""),
        away_team=str(raw.get("awayTeam") or ""),
        odds_home=oh,
        odds_draw=od,
        odds_away=oa,
        p_home=p_h,
        p_draw=p_d,
        p_away=p_a,
        fav_side=fav_side,
        p_favorite=p_fav,
        p_draw_fav=p_draw_fav,
        p_underdog=p_dog,
        prob_fav=pf,
        prob_draw=pd,
        prob_dog=pu,
        home_goals=hg,
        away_goals=ag,
        raw_score=f"{hg}-{ag}",
        norm_score=normalize_favorite_score(hg, ag, fav_side),
        fav_result=favorite_result(hg, ag, fav_side),
        btts_actual=1 if hg > 0 and ag > 0 else 0,
        over_25_actual=1 if total > 2 else 0,
        total_goals=total,
        winning_margin=winning_margin(hg, ag, fav_side),
        segment=segment,
    )


def load_canonical_dataset_from_db(conn: sqlite3.Connection) -> list[MarketPriorRow]:
    conn.row_factory = sqlite3.Row
    rows: list[MarketPriorRow] = []
    seen: set[str] = set()
    for rec in conn.execute(
        "SELECT row_hash, source_file, raw_row_json FROM external_historical_csv_raw_rows"
    ):
        rh = str(rec["row_hash"])
        if rh in seen:
            continue
        seen.add(rh)
        try:
            raw = json.loads(rec["raw_row_json"])
        except json.JSONDecodeError:
            continue
        parsed = row_from_raw_json(rh, str(rec["source_file"]), raw)
        if parsed:
            rows.append(parsed)
    rows.sort(key=lambda r: (r.fixture_date, r.kickoff_utc, r.row_hash))
    return rows


def external_row_to_ecse_odds_features(raw: dict[str, Any]) -> dict[str, Any]:
    """Map external raw JSON fields into ECSE lambda extraction row shape."""
    def pick(key: str) -> float | None:
        return _parse_float(raw.get(key))

    return {
        "ft_home_closing": pick("oddsFT_1"),
        "ft_draw_closing": pick("oddsFT_X"),
        "ft_away_closing": pick("oddsFT_2"),
        "ou_over_25_closing": pick("oddsFT_Over_2_5"),
        "ou_under_25_closing": pick("oddsFT_Under_2_5"),
        "ou_over_15_closing": pick("oddsFT_Over_1_5"),
        "ou_under_15_closing": None,
        "ou_over_35_closing": None,
        "ou_under_35_closing": pick("oddsFT_Under_3_5"),
        "btts_yes_closing": pick("oddsFT_BTTS_Yes"),
        "btts_no_closing": pick("oddsFT_BTTS_No"),
        "dc_home_draw_closing": pick("oddsFT_1X"),
        "dc_home_away_closing": pick("oddsFT_12"),
        "dc_draw_away_closing": pick("oddsFT_X2"),
    }


def build_canonical_dataset(
    conn: sqlite3.Connection,
    *,
    summary_path: Path | None = None,
) -> tuple[list[MarketPriorRow], dict[str, Any]]:
    rows = load_canonical_dataset_from_db(conn)
    hash_counts = Counter(r.row_hash for r in rows)
    dupes = sum(1 for c in hash_counts.values() if c > 1)
    segments = Counter(r.segment for r in rows)
    years = Counter(r.fixture_date[:4] for r in rows if r.fixture_date)

    summary = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "source_table": "external_historical_csv_raw_rows",
        "row_count": len(rows),
        "duplicate_row_hash_count": dupes,
        "date_min": rows[0].fixture_date if rows else None,
        "date_max": rows[-1].fixture_date if rows else None,
        "segments": dict(segments.most_common()),
        "years": dict(sorted(years.items())),
        "fav_side_split": {
            "HOME": sum(1 for r in rows if r.fav_side == "HOME"),
            "AWAY": sum(1 for r in rows if r.fav_side == "AWAY"),
        },
        "avg_total_goals": round(sum(r.total_goals for r in rows) / max(len(rows), 1), 4),
        "fields": [
            "fixture_date",
            "odds_home/draw/away",
            "p_home/draw/away",
            "fav_side",
            "p_favorite/p_draw_fav/p_underdog",
            "norm_score",
            "fav_result",
            "btts_actual",
            "over_25_actual",
            "winning_margin",
            "segment",
        ],
    }

    if summary_path:
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    return rows, summary


def row_to_dict(row: MarketPriorRow) -> dict[str, Any]:
    return asdict(row)
