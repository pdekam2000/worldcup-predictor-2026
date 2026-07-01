"""PHASE WDE-SHADOW-3 — Shadow WDE market inference (O/U2.5 + BTTS only, no production writes)."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from joblib import load

from worldcup_predictor.config.competitions import normalize_competition_key
from worldcup_predictor.owner.euro_c_odds_import import normalize_uefa_odds_snapshot
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS, DEFAULT_TIMEZONE
from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date, vienna_day_utc_bounds
from worldcup_predictor.owner_predict_eval.db_helpers import latest_odds_snapshot
from worldcup_predictor.research.wde_shadow_historical.constants import TARGETS
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, implied_probs, parse_float
from worldcup_predictor.research.wde_shadow_historical.wde_shadow_baselines import (
    _parse_wde_payload,
    bookmaker_predictions,
)

PHASE = "WDE-SHADOW-3"
DEFAULT_MODEL_DIR = Path("models/shadow/wde_historical_csv_shadow_20260701")
SHADOW_ONLY_LABEL = "SHADOW_ONLY"
ONE_X_TWO_BLOCKED = "1X2_PROMOTION_BLOCKED"
PREDICTIONS_ARTIFACT_TEMPLATE = "artifacts/wde_shadow_market_predictions_{tag}.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _date_tag(d: date) -> str:
    return d.strftime("%Y%m%d")


def _window_bounds(
    anchor: date,
    window_days: int,
    tz_name: str = DEFAULT_TIMEZONE,
) -> tuple[str, str]:
    tz = ZoneInfo(tz_name)
    start_local = anchor - timedelta(days=1)
    end_local = anchor + timedelta(days=max(1, window_days))
    start = datetime.combine(start_local, time.min, tzinfo=tz).astimezone(timezone.utc)
    end = datetime.combine(end_local, time.max, tzinfo=tz).astimezone(timezone.utc)
    return start.isoformat(), end.isoformat()


def discover_fixtures_in_window(
    conn: sqlite3.Connection,
    *,
    anchor: date,
    window_days: int = 7,
    competition_keys: list[str] | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    keys = [normalize_competition_key(k) for k in (competition_keys or list(DAILY_SUPPORTED_COMPETITIONS))]
    keys = [k for k in keys if k in DAILY_SUPPORTED_COMPETITIONS]
    start_utc, end_utc = _window_bounds(anchor, window_days)
    placeholders = ",".join("?" for _ in keys)
    rows = conn.execute(
        f"""
        SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season
        FROM fixtures
        WHERE competition_key IN ({placeholders})
          AND is_placeholder = 0
          AND kickoff_utc IS NOT NULL
          AND kickoff_utc >= ?
          AND kickoff_utc <= ?
        ORDER BY kickoff_utc ASC
        LIMIT ?
        """,
        [*keys, start_utc, end_utc, int(limit)],
    ).fetchall()
    return [dict(r) for r in rows]


def _odds_to_implied(snap_payload: dict[str, Any], fixture_id: int) -> dict[str, float | None]:
    normalized = normalize_uefa_odds_snapshot(snap_payload, fixture_id=fixture_id)
    mw = normalized.match_winner or {}
    ou = normalized.over_under_2_5 or {}
    btts = normalized.btts or {}
    flat_odds = {
        "oddsFT_1": None,
        "oddsFT_X": None,
        "oddsFT_2": None,
        "oddsFT_Over_2_5": None,
        "oddsFT_Under_2_5": None,
        "oddsFT_BTTS_Yes": None,
        "oddsFT_BTTS_No": None,
    }
    for sel, key in (("home", "oddsFT_1"), ("draw", "oddsFT_X"), ("away", "oddsFT_2")):
        p = mw.get(sel)
        if p is not None and p > 0:
            flat_odds[key] = round(1.0 / p, 4)
    for sel, key in (("over_2_5", "oddsFT_Over_2_5"), ("under_2_5", "oddsFT_Under_2_5")):
        p = ou.get(sel)
        if p is not None and p > 0:
            flat_odds[key] = round(1.0 / p, 4)
    for sel, key in (("yes", "oddsFT_BTTS_Yes"), ("no", "oddsFT_BTTS_No")):
        p = btts.get(sel)
        if p is not None and p > 0:
            flat_odds[key] = round(1.0 / p, 4)
    implied = implied_probs(flat_odds)
    return {
        "implied_prob_home": implied.get("oddsFT_1"),
        "implied_prob_draw": implied.get("oddsFT_X"),
        "implied_prob_away": implied.get("oddsFT_2"),
        "implied_prob_over_2_5": implied.get("oddsFT_Over_2_5"),
        "implied_prob_under_2_5": implied.get("oddsFT_Under_2_5"),
        "implied_prob_btts_yes": implied.get("oddsFT_BTTS_Yes"),
        "implied_prob_btts_no": implied.get("oddsFT_BTTS_No"),
    }


def _load_production_wde(conn: sqlite3.Connection, fixture_id: int) -> dict[str, str | None]:
    row = conn.execute(
        "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id = ? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    if not row:
        return {"1x2": None, "ou25": None, "btts": None}
    try:
        return _parse_wde_payload(json.loads(row["payload_json"]))
    except (json.JSONDecodeError, TypeError):
        return {"1x2": None, "ou25": None, "btts": None}


def _fixture_feature_row(
    fx: dict[str, Any],
    conn: sqlite3.Connection,
) -> tuple[dict[str, Any] | None, list[str]]:
    missing: list[str] = []
    snap = latest_odds_snapshot(conn, int(fx["fixture_id"]))
    if not snap or not snap.get("payload"):
        return None, ["odds_snapshot_missing"]

    implied = _odds_to_implied(snap["payload"], int(fx["fixture_id"]))
    if not implied.get("implied_prob_home") or not implied.get("implied_prob_over_2_5"):
        missing.append("critical_odds_implied_probs")

    kickoff = str(fx.get("kickoff_utc") or "")[:10]
    season_year = None
    if kickoff and len(kickoff) >= 4:
        try:
            season_year = int(kickoff[:4])
        except ValueError:
            season_year = fx.get("season")

    comp = str(fx.get("competition_key") or "unknown")
    row = {
        "fixture_id": int(fx["fixture_id"]),
        "date": kickoff,
        "kickoff": fx.get("kickoff_utc"),
        "home_team": fx.get("home_team"),
        "away_team": fx.get("away_team"),
        "competition": comp,
        "league": comp,
        "country": comp.split("_")[0] if "_" in comp else comp,
        "season_year": season_year,
        "expectedGoalsHome": None,
        "expectedGoalsAway": None,
        "cornerKicksHome": None,
        "cornerKicksAway": None,
        "data_quality_flags": None,
        **implied,
    }
    if missing:
        return row, missing
    return row, []


def _shadow_predict(model_dir: Path, df: pd.DataFrame) -> tuple[dict[str, list], dict[str, np.ndarray | None], dict[str, list[str]]]:
    encoder = load(model_dir / "feature_encoder.joblib")
    x, _ = encoder.transform(df)
    preds: dict[str, list] = {}
    proba: dict[str, np.ndarray | None] = {}
    classes: dict[str, list[str]] = {}
    for market in TARGETS:
        clf = load(model_dir / f"shadow_{market}.joblib")
        preds[market] = clf.predict(x).tolist()
        classes[market] = list(clf.classes_)
        proba[market] = clf.predict_proba(x) if hasattr(clf, "predict_proba") else None
    return preds, proba, classes


def _pick_confidence(
    pick: str,
    proba_row: np.ndarray | None,
    classes: list[str],
) -> float | None:
    if proba_row is None or pick not in classes:
        return None
    idx = classes.index(pick)
    return round(float(proba_row[idx]), 4)


def run_shadow_market_predictions(
    conn: sqlite3.Connection,
    *,
    date_arg: str = "today",
    window_days: int = 7,
    model_dir: Path | None = None,
    timezone: str = DEFAULT_TIMEZONE,
) -> dict[str, Any]:
    model_dir = model_dir or DEFAULT_MODEL_DIR
    anchor = resolve_target_date(date_arg, timezone)
    fixtures = discover_fixtures_in_window(conn, anchor=anchor, window_days=window_days)
    feature_rows: list[dict[str, Any]] = []
    row_meta: list[dict[str, Any]] = []

    for fx in fixtures:
        row, missing = _fixture_feature_row(fx, conn)
        if row is None:
            row_meta.append({"fixture": fx, "row": None, "missing": missing})
            continue
        feature_rows.append(row)
        row_meta.append({"fixture": fx, "row": row, "missing": missing})

    if not feature_rows:
        return {
            "phase": PHASE,
            "generated_at_utc": _utc_now(),
            "label": SHADOW_ONLY_LABEL,
            "model_dir": str(model_dir),
            "anchor_date": anchor.isoformat(),
            "window_days": window_days,
            "fixture_count": len(fixtures),
            "scored_count": 0,
            "fixtures": [],
            "note": "No fixtures with sufficient odds/features in window",
        }

    df = pd.DataFrame(feature_rows)
    shadow_preds, shadow_proba, shadow_classes = _shadow_predict(model_dir, df)
    book = bookmaker_predictions(df)

    fixtures_out: list[dict[str, Any]] = []
    for i, meta in enumerate(row_meta):
        fx = meta["fixture"]
        if meta["row"] is None:
            fixtures_out.append(
                {
                    "fixture_id": int(fx["fixture_id"]),
                    "match": f"{fx.get('home_team')} vs {fx.get('away_team')}",
                    "competition": fx.get("competition_key"),
                    "kickoff": fx.get("kickoff_utc"),
                    "label": SHADOW_ONLY_LABEL,
                    "skipped": True,
                    "missing_features": meta["missing"],
                }
            )
            continue

        idx = feature_rows.index(meta["row"])
        wde = _load_production_wde(conn, int(fx["fixture_id"]))
        ou_pick = shadow_preds["ou25"][idx]
        btts_pick = shadow_preds["btts"][idx]
        ou_conf = _pick_confidence(ou_pick, shadow_proba.get("ou25")[idx] if shadow_proba.get("ou25") is not None else None, shadow_classes["ou25"])
        btts_conf = _pick_confidence(
            btts_pick,
            shadow_proba.get("btts")[idx] if shadow_proba.get("btts") is not None else None,
            shadow_classes["btts"],
        )
        x12_pick = shadow_preds["1x2"][idx]
        x12_conf = _pick_confidence(
            x12_pick,
            shadow_proba.get("1x2")[idx] if shadow_proba.get("1x2") is not None else None,
            shadow_classes["1x2"],
        )

        book_ou = book["ou25"][idx]
        book_btts = book["btts"][idx]
        book_1x2 = book["1x2"][idx]

        disagreements: list[str] = []
        if book_ou and ou_pick != book_ou:
            disagreements.append("ou25_vs_bookmaker")
        if book_btts and btts_pick != book_btts:
            disagreements.append("btts_vs_bookmaker")
        if wde.get("ou25") and ou_pick != wde["ou25"]:
            disagreements.append("ou25_vs_production_wde")
        if wde.get("btts") and btts_pick != wde["btts"]:
            disagreements.append("btts_vs_production_wde")

        fixtures_out.append(
            {
                "fixture_id": int(fx["fixture_id"]),
                "match": f"{fx.get('home_team')} vs {fx.get('away_team')}",
                "competition": fx.get("competition_key"),
                "kickoff": fx.get("kickoff_utc"),
                "label": SHADOW_ONLY_LABEL,
                "implied_prob_over_2_5": meta["row"].get("implied_prob_over_2_5"),
                "implied_prob_under_2_5": meta["row"].get("implied_prob_under_2_5"),
                "implied_prob_btts_yes": meta["row"].get("implied_prob_btts_yes"),
                "implied_prob_btts_no": meta["row"].get("implied_prob_btts_no"),
                "ou25": {
                    "shadow_pick": ou_pick,
                    "shadow_confidence": ou_conf,
                    "bookmaker_pick": book_ou,
                    "production_wde_pick": wde.get("ou25"),
                },
                "btts": {
                    "shadow_pick": btts_pick,
                    "shadow_confidence": btts_conf,
                    "bookmaker_pick": book_btts,
                    "production_wde_pick": wde.get("btts"),
                },
                "one_x_two_comparison": {
                    "status": ONE_X_TWO_BLOCKED,
                    "shadow_pick": x12_pick,
                    "shadow_confidence": x12_conf,
                    "bookmaker_pick": book_1x2,
                    "production_wde_pick": wde.get("1x2"),
                    "reason": "shadow underperformed bookmaker baseline on test split",
                },
                "disagreement_flags": disagreements,
                "missing_features": meta["missing"],
            }
        )

    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "label": SHADOW_ONLY_LABEL,
        "model_dir": str(model_dir),
        "anchor_date": anchor.isoformat(),
        "window_days": window_days,
        "fixture_count": len(fixtures),
        "scored_count": len(feature_rows),
        "fixtures": fixtures_out,
        "markets_enabled": ["ou25", "btts"],
        "markets_blocked": ["1x2"],
    }


def write_predictions_artifact(payload: dict[str, Any], *, anchor: date) -> Path:
    path = Path(PREDICTIONS_ARTIFACT_TEMPLATE.format(tag=_date_tag(anchor)))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
