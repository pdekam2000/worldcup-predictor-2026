"""Part B — Build canonical WDE shadow training dataset from historical CSV staging."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from worldcup_predictor.research.wde_shadow_historical.constants import (
    CHUNK_SIZE,
    DATASET_PATH,
    DATASET_SUMMARY,
    FT_ODDS_COLUMNS,
    MIN_SHADOW_TRAINING_ROWS,
    PHASE,
    READINESS_ARTIFACT,
)
from worldcup_predictor.research.wde_shadow_historical.helpers import (
    implied_probs,
    is_future_event,
    label_1x2,
    label_btts,
    label_over_25,
    load_raw_row,
    parse_float,
    parse_int,
    table_exists,
)
from worldcup_predictor.research.wde_shadow_historical.readiness_audit import _iter_match_chunks, _odds_complete


@dataclass
class DatasetBuildResult:
    phase: str = PHASE
    built_at_utc: str = ""
    skipped_reason: str | None = None
    row_count: int = 0
    deduplicated_from: int = 0
    dataset_path: str = ""
    summary_path: str = ""
    readiness_at_build: str = ""
    usable_counts: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "phase": self.phase,
            "built_at_utc": self.built_at_utc,
            "skipped_reason": self.skipped_reason,
            "row_count": self.row_count,
            "deduplicated_from": self.deduplicated_from,
            "dataset_path": self.dataset_path,
            "summary_path": self.summary_path,
            "readiness_at_build": self.readiness_at_build,
            "usable_counts": self.usable_counts,
        }


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _load_readiness() -> dict[str, Any]:
    if not READINESS_ARTIFACT.exists():
        return {}
    return json.loads(READINESS_ARTIFACT.read_text(encoding="utf-8"))


def _safe_to_build(readiness: dict[str, Any]) -> tuple[bool, str]:
    status = str(readiness.get("readiness") or "DO_NOT_TRAIN_YET")
    usable = int((readiness.get("usable_rows") or {}).get("wde_1x2") or 0)
    if status == "DO_NOT_TRAIN_YET":
        return False, "readiness_DO_NOT_TRAIN_YET"
    if usable < MIN_SHADOW_TRAINING_ROWS:
        return False, f"insufficient_usable_rows:{usable}"
    if status in ("READY_FOR_SHADOW_TRAINING", "NEED_TEAM_ALIAS_MAPPING", "NEED_LEAGUE_MAPPING"):
        # Shadow dataset uses staging-native team names; local crosswalk alias gaps are non-blocking
        return True, status
    if status == "NEED_DATA_CLEANING" and usable >= MIN_SHADOW_TRAINING_ROWS * 2:
        return True, "NEED_DATA_CLEANING_but_usable_rows_high"
    return False, status


def _row_to_record(row: sqlite3.Row, raw: dict[str, Any]) -> dict[str, Any] | None:
    home = str(row["home_team"] or "").strip()
    away = str(row["away_team"] or "").strip()
    if not home or not away:
        return None
    if is_future_event(row["event_date"]):
        return None

    hg = parse_int(row["home_ft_goals"])
    ag = parse_int(row["away_ft_goals"])
    if hg is None or ag is None:
        return None

    odds = {col: parse_float(raw.get(col)) for col in FT_ODDS_COLUMNS}
    if not _odds_complete(raw, ("oddsFT_1", "oddsFT_X", "oddsFT_2")):
        return None
    for col, val in odds.items():
        if val is not None and val <= 1.0:
            return None

    implied = implied_probs(odds)
    flags: list[str] = []
    dq = raw.get("_data_quality_flags") or {}
    if isinstance(dq, dict):
        flags.extend(sorted(dq.keys()))

    season_year = None
    event_date = str(row["event_date"] or "")[:10]
    if len(event_date) >= 4:
        try:
            season_year = int(event_date[:4])
        except ValueError:
            season_year = None

    return {
        "source_match_id": row["row_hash"],
        "row_hash": row["row_hash"],
        "date": event_date,
        "kickoff": row["kickoff_utc"] or event_date,
        "country": row["country_name"],
        "league": row["league"],
        "competition": row["league"],
        "season_year": season_year,
        "home_team": home,
        "away_team": away,
        "final_home_goals": hg,
        "final_away_goals": ag,
        "label_1x2": label_1x2(hg, ag),
        "label_over_2_5": label_over_25(hg, ag),
        "label_btts": label_btts(hg, ag),
        "expectedGoalsHome": parse_float(row["home_xg"] if row["home_xg"] is not None else raw.get("expectedGoalsHome")),
        "expectedGoalsAway": parse_float(row["away_xg"] if row["away_xg"] is not None else raw.get("expectedGoalsAway")),
        "cornerKicksHome": parse_int(row["home_corners"] if row["home_corners"] is not None else raw.get("cornerKicksHome")),
        "cornerKicksAway": parse_int(row["away_corners"] if row["away_corners"] is not None else raw.get("cornerKicksAway")),
        "penaltiesHome": parse_int(row["home_penalties"] if row["home_penalties"] is not None else raw.get("penaltiesHome")),
        "penaltiesAway": parse_int(row["away_penalties"] if row["away_penalties"] is not None else raw.get("penaltiesAway")),
        "oddsFT_1": odds["oddsFT_1"],
        "oddsFT_X": odds["oddsFT_X"],
        "oddsFT_2": odds["oddsFT_2"],
        "oddsFT_Over_2_5": odds["oddsFT_Over_2_5"],
        "oddsFT_Under_2_5": odds["oddsFT_Under_2_5"],
        "oddsFT_BTTS_Yes": odds["oddsFT_BTTS_Yes"],
        "oddsFT_BTTS_No": odds["oddsFT_BTTS_No"],
        "implied_prob_home": implied.get("oddsFT_1"),
        "implied_prob_draw": implied.get("oddsFT_X"),
        "implied_prob_away": implied.get("oddsFT_2"),
        "implied_prob_over_2_5": implied.get("oddsFT_Over_2_5"),
        "implied_prob_under_2_5": implied.get("oddsFT_Under_2_5"),
        "implied_prob_btts_yes": implied.get("oddsFT_BTTS_Yes"),
        "implied_prob_btts_no": implied.get("oddsFT_BTTS_No"),
        "data_quality_flags": ",".join(flags) if flags else None,
        "source_file": row["source_file"],
        "source_status": str(row["status"] or ""),
        "source_phase": PHASE,
    }


def build_shadow_dataset(conn: sqlite3.Connection, *, force: bool = False) -> DatasetBuildResult:
    result = DatasetBuildResult(built_at_utc=_utc_now())
    readiness = _load_readiness()
    result.readiness_at_build = str(readiness.get("readiness") or "unknown")
    result.usable_counts = dict(readiness.get("usable_rows") or {})

    if not table_exists(conn, "external_match_history_staging"):
        result.skipped_reason = "staging_table_missing"
        return result

    if not force:
        ok, reason = _safe_to_build(readiness)
        if not ok:
            result.skipped_reason = reason
            return result

    records: list[dict[str, Any]] = []
    seen_hashes: set[str] = set()
    raw_total = 0

    for chunk in _iter_match_chunks(conn):
        for row in chunk:
            raw_total += 1
            rhash = str(row["row_hash"])
            if rhash in seen_hashes:
                continue
            raw = load_raw_row(row["raw_row_json"])
            rec = _row_to_record(row, raw)
            if rec is None:
                continue
            seen_hashes.add(rhash)
            records.append(rec)

    result.deduplicated_from = raw_total
    result.row_count = len(records)

    if result.row_count < MIN_SHADOW_TRAINING_ROWS:
        result.skipped_reason = f"built_rows_below_minimum:{result.row_count}"
        return result

    DATASET_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    df.to_parquet(DATASET_PATH, index=False)
    result.dataset_path = str(DATASET_PATH)

    summary = {
        **result.to_dict(),
        "columns": list(df.columns),
        "label_1x2_distribution": df["label_1x2"].value_counts().to_dict() if "label_1x2" in df else {},
        "date_min": df["date"].min() if len(df) else None,
        "date_max": df["date"].max() if len(df) else None,
        "leagues_top10": df["league"].value_counts().head(10).to_dict() if "league" in df else {},
    }
    DATASET_SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    DATASET_SUMMARY.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    result.summary_path = str(DATASET_SUMMARY)
    return result
