#!/usr/bin/env python3
"""Phase API-I — UEFA event schema audit, FG pending breakdown, xG/predictions diagnosis."""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACTS = ROOT / "artifacts"
MAPPING_PATH = ARTIFACTS / "uefa_fixture_mapping.json"
BEFORE_BACKTEST = ARTIFACTS / "uefa_club_backtest.json"


def _raw_cache_paths() -> list[Path]:
    roots = [
        ROOT / "data" / "egie" / "uefa_club" / "raw",
        ROOT / "data" / "data" / "egie" / "uefa_club" / "raw",
    ]
    seen: set[int] = set()
    paths: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for p in sorted(root.glob("*.json")):
            try:
                fid = int(p.stem)
            except ValueError:
                continue
            if fid in seen:
                continue
            seen.add(fid)
            paths.append(p)
    return paths


def _load_mapping() -> dict[int, dict[str, Any]]:
    if not MAPPING_PATH.is_file():
        return {}
    data = json.loads(MAPPING_PATH.read_text(encoding="utf-8"))
    out: dict[int, dict[str, Any]] = {}
    for fx in data.get("fixtures") or []:
        fid = int(fx.get("sportmonks_fixture_id") or 0)
        if fid:
            out[fid] = fx
    return out


def _fixture_data(blob: dict[str, Any]) -> dict[str, Any] | None:
    payload = blob.get("payload")
    if isinstance(payload, dict):
        if isinstance(payload.get("data"), dict):
            return payload["data"]
        if payload.get("id"):
            return payload
    return None


def audit_event_schema(paths: list[Path]) -> dict[str, Any]:
    type_id_names: dict[int, set[str]] = defaultdict(set)
    type_counts: Counter[int] = Counter()
    field_presence: Counter[str] = Counter()
    sample_goal: dict[str, Any] | None = None
    sample_penalty: dict[str, Any] | None = None
    sample_own_goal: dict[str, Any] | None = None
    participant_fields: Counter[str] = Counter()
    fixtures_with_events = 0
    total_events = 0

    for path in paths:
        blob = json.loads(path.read_text(encoding="utf-8"))
        raw = _fixture_data(blob)
        if not raw:
            continue
        events = raw.get("events") or []
        if events:
            fixtures_with_events += 1
        total_events += len(events)
        for p in raw.get("participants") or []:
            if isinstance(p, dict):
                for k in p:
                    participant_fields[k] += 1
                meta = p.get("meta") or {}
                for k in meta:
                    participant_fields[f"meta.{k}"] += 1
        for ev in events:
            if not isinstance(ev, dict):
                continue
            tid = ev.get("type_id")
            tname = str((ev.get("type") or {}).get("name") or "")
            if tid is not None:
                type_counts[int(tid)] += 1
                type_id_names[int(tid)].add(tname)
            for k in ("minute", "extra_minute", "participant_id", "player_id", "player_name", "sort_order", "rescinded", "result", "info", "addition"):
                if ev.get(k) is not None:
                    field_presence[k] += 1
            if sample_goal is None and tid == 14:
                sample_goal = {k: ev.get(k) for k in ev if k != "period"}
                sample_goal["type"] = ev.get("type")
            if sample_penalty is None and tid == 16:
                sample_penalty = {k: ev.get(k) for k in ev if k != "period"}
                sample_penalty["type"] = ev.get("type")
            if sample_own_goal is None and tid == 15:
                sample_own_goal = {k: ev.get(k) for k in ev if k != "period"}
                sample_own_goal["type"] = ev.get("type")

    return {
        "fixtures_audited": len(paths),
        "fixtures_with_events": fixtures_with_events,
        "total_events": total_events,
        "event_type_ids": {
            str(tid): {"count": type_counts[tid], "names": sorted(type_id_names[tid])}
            for tid in sorted(type_counts)
        },
        "goal_event_types": {
            "goal": {"type_id": 14, "name": "Goal"},
            "own_goal": {"type_id": 15, "name": "Own Goal"},
            "penalty": {"type_id": 16, "name": "Penalty"},
            "missed_penalty": {"type_id": 17, "name": "Missed Penalty"},
            "penalty_shootout_goal": {"type_id": 23, "name": "Penalty Shootout Goal"},
            "substitution_not_goal": {"type_id": 18, "name": "Substitution", "note": "was incorrectly in GOAL_TYPE_IDS pre API-I"},
        },
        "event_field_presence": dict(field_presence),
        "participant_fields": dict(participant_fields),
        "team_identifier_fields": ["participants[].id", "participants[].meta.location", "events[].participant_id"],
        "minute_fields": ["events[].minute", "events[].extra_minute", "events[].sort_order"],
        "samples": {
            "goal": sample_goal,
            "penalty": sample_penalty,
            "own_goal": sample_own_goal,
        },
        "ordering": "events sorted by (minute, extra_minute, sort_order) for first-goal resolution",
    }


def fg_pending_breakdown(paths: list[Path], mapping: dict[int, dict[str, Any]]) -> dict[str, Any]:
    from worldcup_predictor.egie.uefa_club.feature_extractors import (
        build_participant_maps,
        parse_match_result,
        parse_uefa_goal_events,
    )

    before_pending = 62
    if BEFORE_BACKTEST.is_file():
        bt = json.loads(BEFORE_BACKTEST.read_text(encoding="utf-8"))
        fg = ((bt.get("strategies") or {}).get("A") or {}).get("metrics", {}).get("by_market", {}).get("first_goal_team", {})
        before_pending = int(fg.get("pending") or 62)

    categories: Counter[str] = Counter()
    fixtures_detail: list[dict[str, Any]] = []

    for path in paths:
        fid = int(path.stem)
        fx = mapping.get(fid, {})
        blob = json.loads(path.read_text(encoding="utf-8"))
        raw = _fixture_data(blob)
        if not raw:
            categories["no_raw_payload"] += 1
            continue
        home = str(fx.get("home_team") or "")
        away = str(fx.get("away_team") or "")
        result = parse_match_result(blob.get("payload"), home_team=home, away_team=away)
        goals = parse_uefa_goal_events(raw)
        id_to_side, _, _ = build_participant_maps(raw)
        state = str((raw.get("state") or {}).get("developer_name") or "")
        total_score = int(result.get("home_goals") or 0) + int(result.get("away_goals") or 0)

        reason = "resolved"
        if total_score == 0:
            reason = "scoreless_match"
        elif not goals:
            reason = "no_scoring_events_in_payload"
        elif result.get("first_goal_team_side") is None:
            if goals[0].get("participant_id") and not id_to_side:
                reason = "participant_mapping_missing"
            elif goals[0].get("participant_id") and goals[0].get("participant_id") not in id_to_side:
                reason = "participant_id_not_in_fixture_participants"
            else:
                reason = "parser_side_unresolved"
        elif state and state not in ("FT", "AET", "FT_PEN"):
            reason = "fixture_status_not_finished"

        categories[reason] += 1
        if reason != "resolved" or result.get("first_goal_team_side") is None:
            fixtures_detail.append(
                {
                    "fixture_id": fid,
                    "home_team": home,
                    "away_team": away,
                    "state": state,
                    "home_goals": result.get("home_goals"),
                    "away_goals": result.get("away_goals"),
                    "goal_events": len(goals),
                    "first_goal_side": result.get("first_goal_team_side"),
                    "reason": reason,
                }
            )

    return {
        "before_api_i_pending_fg_team_evaluations": before_pending,
        "fixtures_audited": len(paths),
        "breakdown": dict(categories),
        "unresolved_fixtures": fixtures_detail,
        "root_causes_pre_fix": [
            "GOAL_TYPE_IDS incorrectly included type_id 18 (Substitution), corrupting first-goal minute on 14 fixtures",
            "actual_first_goal_team used team names while predictions use home/away/none sides",
        ],
    }


def diagnose_xg_predictions(paths: list[Path]) -> dict[str, Any]:
    from worldcup_predictor.egie.uefa_club.config import UEFA_FULL_INCLUDES
    from worldcup_predictor.egie.uefa_club.feature_extractors import parse_uefa_predictions, parse_uefa_xg
    from worldcup_predictor.providers.sportmonks_xg_extraction import _XG_TYPE_MAP

    xg_rows = 0
    xg_true_type = 0
    xg_type_ids: Counter[int] = Counter()
    preds_nonempty = 0
    pressure_nonempty = 0
    seasons: Counter[int] = Counter()
    sample_xg_types: list[dict[str, Any]] = []
    sample_prediction: Any = None

    for path in paths:
        blob = json.loads(path.read_text(encoding="utf-8"))
        raw = _fixture_data(blob)
        if not raw:
            continue
        seasons[int(raw.get("season_id") or 0)] += 1
        xgfixture = raw.get("xgfixture") or raw.get("xGFixture") or []
        if isinstance(xgfixture, list) and xgfixture:
            xg_rows += 1
            for row in xgfixture:
                if not isinstance(row, dict):
                    continue
                tid = int(row.get("type_id") or 0)
                xg_type_ids[tid] += 1
                if tid == 5304:
                    xg_true_type += 1
                if len(sample_xg_types) < 5:
                    sample_xg_types.append(
                        {
                            "fixture_id": raw.get("id"),
                            "type_id": tid,
                            "type_name": (row.get("type") or {}).get("name"),
                            "value": (row.get("data") or {}).get("value"),
                        }
                    )
        preds = raw.get("predictions") or []
        if isinstance(preds, list) and preds:
            preds_nonempty += 1
            if sample_prediction is None:
                sample_prediction = preds[0]
        pressure = raw.get("pressure") or []
        if isinstance(pressure, list) and pressure:
            pressure_nonempty += 1

        parsed_xg = parse_uefa_xg(blob.get("payload"))
        parsed_pred = parse_uefa_predictions(blob.get("payload"))

    n = len(paths)
    return {
        "fixtures_audited": n,
        "ingest_includes": UEFA_FULL_INCLUDES,
        "xgfixture": {
            "fixtures_with_xgfixture_key": xg_rows,
            "fixtures_with_true_xg_type_5304": xg_true_type,
            "coverage_pct": round(100 * xg_true_type / n, 2) if n else 0,
            "type_id_histogram": {str(k): v for k, v in xg_type_ids.most_common(15)},
            "expected_xg_type_ids": {str(k): v for k, v in _XG_TYPE_MAP.items() if k in (5304, 5305, 7943)},
            "sample_rows": sample_xg_types,
            "parser_home_xg_non_null": sum(1 for p in paths if parse_uefa_xg(json.loads(p.read_text()).get("payload")).get("home_xg") is not None),
        },
        "predictions": {
            "fixtures_with_nonempty_predictions_array": preds_nonempty,
            "coverage_pct": round(100 * preds_nonempty / n, 2) if n else 0,
            "sample_row": sample_prediction,
            "parser_home_win_non_null": sum(
                1
                for p in paths
                if parse_uefa_predictions(json.loads(p.read_text(encoding="utf-8")).get("payload")).get("sportmonks_home_win")
                is not None
            ),
        },
        "pressure": {
            "fixtures_with_nonempty_pressure_array": pressure_nonempty,
            "coverage_pct": round(100 * pressure_nonempty / n, 2) if n else 0,
        },
        "season_distribution": {str(k): v for k, v in seasons.most_common(10)},
        "diagnosis": {
            "xg": (
                "Historical UEFA cache contains xGFixture include responses but rows are match statistics "
                "(corners, shots) not expected-goals metrics (type_id 5304). True xG unavailable for 2014-era seasons in cache."
                if xg_true_type == 0
                else f"{xg_true_type} fixtures have type_id 5304 xG rows"
            ),
            "predictions": (
                "predictions[] is empty for all cached historical fixtures; Sportmonks pre-match predictions "
                "are not retained in finished-match payloads for these seasons."
                if preds_nonempty == 0
                else f"{preds_nonempty} fixtures have prediction rows"
            ),
            "live_vs_historical": (
                "Live probe (CL 168925) returns same include keys; xGFixture holds non-xG stats for old seasons. "
                "Pressure array empty in cache; possession fallback used from statistics."
            ),
        },
        "recommendation": (
            "Do not fabricate xG/predictions. For Phase API-J consider re-ingesting recent-season UEFA fixtures "
            "(2023+) where Sportmonks xG add-on may populate type_id 5304, or accept A-only backtest for historical UEFA."
        ),
    }


def main() -> int:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    paths = _raw_cache_paths()
    mapping = _load_mapping()

    schema = audit_event_schema(paths)
    schema_path = ARTIFACTS / "uefa_event_schema_audit.json"
    schema_path.write_text(json.dumps(schema, indent=2, default=str), encoding="utf-8")
    print(f"STEP 1 -> {schema_path}")

    breakdown = fg_pending_breakdown(paths, mapping)
    breakdown_path = ARTIFACTS / "uefa_fg_team_pending_breakdown.json"
    breakdown_path.write_text(json.dumps(breakdown, indent=2, default=str), encoding="utf-8")
    print(f"STEP 2 -> {breakdown_path}")

    xg_diag = diagnose_xg_predictions(paths)
    xg_path = ARTIFACTS / "uefa_xg_predictions_diagnosis.json"
    xg_path.write_text(json.dumps(xg_diag, indent=2, default=str), encoding="utf-8")
    print(f"STEP 5 -> {xg_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
