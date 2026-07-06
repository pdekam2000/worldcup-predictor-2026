"""Tomorrow 4-league production prediction batch — discovery, freeze, evaluation."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.accuracy.evaluator import actual_1x2, actual_over_under
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import COMPETITION_REGISTRY, CompetitionConfig, get_competition
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.odds.freshness_refresh import run_odds_freshness_refresh
from worldcup_predictor.owner.euro_c_odds_import import (
    _latest_odds_snapshot,
    assess_ecse_readiness,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)
from worldcup_predictor.owner_daily.fixture_discovery import (
    DailyFixture,
    discover_fixtures_from_db,
    resolve_target_date,
    vienna_day_utc_bounds,
)
from worldcup_predictor.owner_daily.odds_import import scan_fixture_odds_readiness
from worldcup_predictor.owner_daily.predictions import run_daily_predictions
from worldcup_predictor.owner_daily.report import (
    _load_ecse,
    _load_wde,
    _normalize_1x2,
    _owner_label,
    _scoreline_to_1x2,
)
from worldcup_predictor.owner_predict_eval.constants import ARTIFACTS_DIR, REPORTS_DIR
from worldcup_predictor.owner_predict_eval.dates import date_tag
from worldcup_predictor.owner_predict_eval.db_helpers import load_fixture_result, table_exists
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables, get_snapshot, has_snapshot
from worldcup_predictor.schedule.match_center import FINISHED_STATUSES

PHASE = "TOMORROW-4-LEAGUE-BATCH"
BATCH_PREFIX = "tomorrow_4_league"
TZ = "Europe/Vienna"
SELECT_COUNT = 4
NOT_STARTED = {"NS", "TBD", "SCHEDULED", "TIMED", "NOT_STARTED", "NOT STARTED"}

DDL = (
    """
    CREATE TABLE IF NOT EXISTS owner_league_batch_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        target_date TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        competition_key TEXT,
        competition_type TEXT,
        kickoff_utc TEXT,
        snapshot_json TEXT NOT NULL,
        prediction_timestamp TEXT NOT NULL,
        is_frozen INTEGER NOT NULL DEFAULT 1,
        UNIQUE(batch_id, fixture_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS owner_league_batch_evaluations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        batch_id TEXT NOT NULL,
        fixture_id INTEGER NOT NULL,
        competition_type TEXT,
        evaluation_json TEXT NOT NULL,
        evaluated_at TEXT NOT NULL,
        UNIQUE(batch_id, fixture_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_owner_league_batch_snapshots_batch
    ON owner_league_batch_snapshots(batch_id, target_date)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_owner_league_batch_evaluations_batch
    ON owner_league_batch_evaluations(batch_id)
    """,
)

DOMESTIC_LEAGUE_KEYS: tuple[str, ...] = tuple(
    k for k, c in COMPETITION_REGISTRY.items() if c.enabled and c.compensation_type == "league"
)
CLUB_COMPETITION_KEYS: tuple[str, ...] = (
    "champions_league",
    "europa_league",
    "conference_league",
)
SUPPORTED_BATCH_KEYS: tuple[str, ...] = DOMESTIC_LEAGUE_KEYS + CLUB_COMPETITION_KEYS


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _kickoff_vienna(kickoff_utc: str) -> str:
    try:
        dt = datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo(TZ)).strftime("%Y-%m-%d %H:%M %Z")
    except ValueError:
        return kickoff_utc


def ensure_batch_tables(conn: sqlite3.Connection) -> None:
    for stmt in DDL:
        conn.execute(stmt)
    conn.commit()


def batch_id_for(target: date) -> str:
    return f"{BATCH_PREFIX}_{date_tag(target)}"


def artifact_dir_for(target: date) -> Path:
    return ARTIFACTS_DIR / f"tomorrow_4_league_predictions_{date_tag(target)}"


def prediction_report_path(target: date) -> Path:
    return REPORTS_DIR / f"TOMORROW_4_LEAGUE_MATCH_PREDICTIONS_{target.isoformat()}.md"


def evaluation_report_path(target: date) -> Path:
    return REPORTS_DIR / f"TOMORROW_4_LEAGUE_MATCH_EVALUATION_{target.isoformat()}.md"


def classify_competition_type(
    comp_key: str,
    *,
    comp: CompetitionConfig | None = None,
    round_name: str | None = None,
) -> str:
    comp = comp or get_competition(comp_key) if comp_key in COMPETITION_REGISTRY else None
    rnd = str(round_name or "").lower()
    if comp and comp.compensation_type == "league":
        return "domestic_league"
    if comp and comp.compensation_type == "friendly":
        return "national_team_group"
    if comp and comp.key == "world_cup_2026":
        if any(x in rnd for x in ("final", "semi", "quarter", "round of", "last 16", "last 32")):
            return "national_team_knockout"
        if "group" in rnd:
            return "national_team_group"
        return "national_team_knockout"
    if comp and comp.compensation_type == "cup":
        if any(x in rnd for x in ("group", "league phase", "phase")):
            return "international_club_group"
        return "international_club_knockout"
    if comp and comp.compensation_type == "tournament":
        return "national_team_knockout"
    return "other/unknown"


def _league_id_to_comp_key(league_id: int) -> str | None:
    for key, comp in COMPETITION_REGISTRY.items():
        if comp.league_id == league_id and comp.enabled:
            return key
    return None


def _fetch_api_fixtures_for_date(client: ApiFootballClient, target: date) -> list[dict[str, Any]]:
    result = client._safe_get(
        "fixtures",
        {"date": target.isoformat()},
        placeholder_factory=lambda: None,
        ttl_seconds=120,
    )
    if not result or not result.data:
        return []
    return [item for item in result.data if isinstance(item, dict)]


def _candidate_from_api_item(item: dict[str, Any], *, allow_club_fallback: bool = True) -> dict[str, Any] | None:
    league = item.get("league") or {}
    league_id = int(league.get("id") or 0)
    comp_key = _league_id_to_comp_key(league_id)
    if not comp_key:
        return None
    comp = get_competition(comp_key)
    if comp.compensation_type == "league":
        pass
    elif allow_club_fallback and comp_key in CLUB_COMPETITION_KEYS:
        pass
    else:
        return None
    fx = item.get("fixture") or {}
    teams = item.get("teams") or {}
    status = str((fx.get("status") or {}).get("short") or "NS").upper()
    if status not in NOT_STARTED:
        return None
    fid = int(fx.get("id") or 0)
    if not fid:
        return None
    return {
        "fixture_id": fid,
        "provider_fixture_id": fid,
        "api_item": item,
        "competition_key": comp_key,
        "competition_name": comp.name,
        "competition_type": classify_competition_type(comp_key, comp=comp),
        "country": str(league.get("country") or comp.country),
        "home_team": str((teams.get("home") or {}).get("name") or ""),
        "away_team": str((teams.get("away") or {}).get("name") or ""),
        "kickoff_utc": str(fx.get("date") or ""),
        "status": status,
        "league_id": league_id,
        "season": int(league.get("season") or comp.season),
    }


def _score_candidate(conn: sqlite3.Connection, cand: dict[str, Any], settings: Settings) -> dict[str, Any]:
    fid = int(cand["fixture_id"])
    fx = DailyFixture(
        fixture_id=fid,
        provider_fixture_id=fid,
        competition_key=cand["competition_key"],
        home_team=cand["home_team"],
        away_team=cand["away_team"],
        kickoff_utc=cand["kickoff_utc"],
        status=cand["status"],
        season=cand.get("season"),
        coverage_sources=["api_football"],
        provider_ids={"api_football": fid},
    )
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()
    readiness = scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)
    snap = _latest_odds_snapshot(conn, fid)
    payload = None
    if snap and snap.get("payload_json"):
        try:
            payload = json.loads(snap["payload_json"])
        except json.JSONDecodeError:
            payload = snap.get("payload")
    norm = (
        normalize_uefa_odds_snapshot(payload, fixture_id=fid)
        if payload and not is_fake_odds_payload(payload)
        else None
    )
    ecse_ready = assess_ecse_readiness(conn, fid, normalized=norm)
    score = 0
    reasons: list[str] = []
    reject: str | None = None

    if not readiness.get("has_1x2"):
        score -= 20
        reasons.append("odds_missing_prematch")
    elif int(readiness.get("bookmaker_count") or norm.bookmaker_count if norm else 0) < 2:
        score -= 10
        reasons.append("thin_bookmaker_coverage")
    else:
        score += 30
        reasons.append("usable_odds")

    if readiness.get("odds_freshness") == "stale" and readiness.get("has_1x2"):
        score -= 15
        reasons.append("stale_odds_penalty")
    elif readiness.get("odds_freshness") == "fresh":
        score += 10
        reasons.append("fresh_odds")

    if ecse_ready.get("ecse_ready"):
        score += 25
        reasons.append("ecse_ready")
    elif not ecse_ready.get("lambda_inputs_available"):
        score -= 5
        reasons.append("ecse_inputs_uncertain_prematch")

    if readiness.get("has_btts"):
        score += 10
    if readiness.get("has_ou25"):
        score += 10
    if cand["competition_type"] == "domestic_league":
        score += 15
        reasons.append("domestic_league")
    elif cand["competition_key"] in CLUB_COMPETITION_KEYS:
        score += 8
        reasons.append("supported_club_competition")

    # historical coverage proxy: fixture already in DB
    row = conn.execute("SELECT 1 FROM fixtures WHERE fixture_id=? LIMIT 1", (fid,)).fetchone()
    if row:
        score += 10
        reasons.append("db_coverage")

    return {
        **cand,
        "selection_score": score,
        "selection_reasons": reasons,
        "rejection_reason": reject,
        "odds_readiness": readiness,
        "ecse_readiness": ecse_ready,
        "bookmaker_count": int(norm.bookmaker_count if norm else readiness.get("bookmaker_count") or 0),
        "odds_freshness": readiness.get("odds_freshness"),
    }


def discover_and_select_fixtures(
    *,
    date_arg: str = "tomorrow",
    timezone: str = TZ,
    settings: Settings | None = None,
    select_count: int = SELECT_COUNT,
) -> dict[str, Any]:
    settings = settings or get_settings()
    target = resolve_target_date(date_arg, timezone)
    conn = connect(settings.sqlite_path)
    ensure_ecse_live_tables(conn)

    client = ApiFootballClient(settings) if settings.api_football_configured else None
    candidates: list[dict[str, Any]] = []
    audit: list[dict[str, Any]] = []

    if client:
        for item in _fetch_api_fixtures_for_date(client, target):
            cand = _candidate_from_api_item(item)
            if not cand:
                continue
            scored = _score_candidate(conn, cand, settings)
            candidates.append(scored)

    # DB fallback for domestic leagues
    start_utc, end_utc = vienna_day_utc_bounds(target, timezone)
    db_fixtures = discover_fixtures_from_db(
        conn,
        competition_keys=list(SUPPORTED_BATCH_KEYS),
        start_utc=start_utc,
        end_utc=end_utc,
        limit=80,
    )
    seen = {c["fixture_id"] for c in candidates}
    for fx in db_fixtures:
        if fx.provider_fixture_id in seen:
            continue
        if str(fx.status).upper() not in NOT_STARTED:
            continue
        comp = get_competition(fx.competition_key)
        cand = {
            "fixture_id": fx.provider_fixture_id,
            "provider_fixture_id": fx.provider_fixture_id,
            "api_item": None,
            "competition_key": fx.competition_key,
            "competition_name": comp.name,
            "competition_type": classify_competition_type(fx.competition_key, comp=comp),
            "country": comp.country,
            "home_team": fx.home_team,
            "away_team": fx.away_team,
            "kickoff_utc": fx.kickoff_utc,
            "status": fx.status,
            "league_id": comp.league_id,
            "season": fx.season or comp.season,
        }
        scored = _score_candidate(conn, cand, settings)
        candidates.append(scored)
        seen.add(fx.provider_fixture_id)

    for c in candidates:
        audit.append(
            {
                "fixture_id": c["fixture_id"],
                "match": f"{c['home_team']} vs {c['away_team']}",
                "competition": c["competition_name"],
                "score": c["selection_score"],
                "selected": False,
                "rejection_reason": c.get("rejection_reason"),
                "reasons": c.get("selection_reasons"),
                "bookmaker_count": c.get("bookmaker_count"),
                "odds_freshness": c.get("odds_freshness"),
            }
        )

    eligible = [c for c in candidates if not c.get("rejection_reason")]
    domestic_eligible = [c for c in eligible if c.get("competition_type") == "domestic_league"]
    pool = domestic_eligible if len(domestic_eligible) >= select_count else eligible
    pool.sort(key=lambda x: (-x["selection_score"], x["kickoff_utc"], x["fixture_id"]))
    preselect_count = max(select_count * 3, 12)
    selected = pool[:preselect_count]

    selected_ids = {s["fixture_id"] for s in selected[:select_count]}
    for row in audit:
        if row["fixture_id"] in selected_ids:
            row["selected"] = True
        elif not row["rejection_reason"] and row["fixture_id"] not in selected_ids:
            row["rejection_reason"] = "lower_selection_score"

    conn.close()
    return {
        "target_date": target.isoformat(),
        "timezone": timezone,
        "batch_id": batch_id_for(target),
        "candidate_count": len(candidates),
        "eligible_count": len(eligible),
        "selected_count": len(selected[:select_count]),
        "preselected_count": len(selected),
        "selected": selected,
        "all_candidates": candidates,
        "selection_audit": audit,
    }


def _upsert_fixtures(repo: FootballIntelligenceRepository, selected: list[dict[str, Any]]) -> list[DailyFixture]:
    fixtures: list[DailyFixture] = []
    for d in selected:
        comp_key = d["competition_key"]
        comp = get_competition(comp_key)
        repo.upsert_competition(comp)
        if d.get("api_item"):
            parsed = parse_api_fixture_item(d["api_item"], source="api_football")
            if parsed:
                repo.upsert_fixture(
                    parsed,
                    competition_key=comp_key,
                    league_id=int(d["league_id"]),
                    season=int(d["season"]) if d.get("season") else None,
                )
        fixtures.append(
            DailyFixture(
                fixture_id=int(d["fixture_id"]),
                provider_fixture_id=int(d["fixture_id"]),
                competition_key=comp_key,
                home_team=str(d["home_team"]),
                away_team=str(d["away_team"]),
                kickoff_utc=str(d["kickoff_utc"]),
                status=str(d.get("status") or "NS"),
                season=int(d["season"]) if d.get("season") else None,
                coverage_sources=["api_football"],
                provider_ids={"api_football": int(d["fixture_id"])},
            )
        )
    return fixtures


def _ecse_top_list(pred: dict | None, n: int) -> list[dict[str, Any]]:
    if not pred:
        return []
    rows = pred.get("top_10_scorelines") or []
    return [
        {"scoreline": r["scoreline"], "probability": round(float(r["probability"]) * 100, 2)}
        for r in rows[:n]
    ]


def _btts_mass(top10: list[dict]) -> float:
    mass = 0.0
    for r in top10:
        try:
            h, a = str(r["scoreline"]).split("-", 1)
            if int(h) > 0 and int(a) > 0:
                mass += float(r.get("probability") or 0)
        except (ValueError, TypeError):
            pass
    return mass


def _ou_mass(top10: list[dict], line: float = 2.5) -> float:
    over = 0.0
    for r in top10:
        try:
            h, a = str(r["scoreline"]).split("-", 1)
            if int(h) + int(a) > line:
                over += float(r.get("probability") or 0) / (100.0 if float(r.get("probability") or 0) > 1 else 1)
        except (ValueError, TypeError):
            pass
    return over


def _consistency(wde: dict | None, ecse_pred: dict | None) -> dict[str, Any]:
    reasons: list[str] = []
    if not wde or not ecse_pred:
        return {"status": "MAJOR_DIVERGENCE", "reasons": ["missing_wde_or_ecse"]}
    wde_x2 = _normalize_1x2(wde.get("predicted_1x2"))
    top10 = ecse_pred.get("top_10_scorelines") or []
    top3 = top10[:3]
    top3_x2 = [_scoreline_to_1x2(r.get("scoreline")) for r in top3]
    if wde_x2 == "home_win" and top3_x2.count("away_win") >= 2:
        reasons.append("wde_home_but_ecse_top3_favor_away")
    if wde_x2 == "away_win" and top3_x2.count("home_win") >= 2:
        reasons.append("wde_away_but_ecse_top3_favor_home")
    wde_ou = str(wde.get("predicted_over_under_2_5") or "").lower()
    ou_over = _ou_mass(top10)
    if "under" in wde_ou and ou_over > 0.55:
        reasons.append("wde_under_but_ecse_high_scoring_mass")
    if "over" in wde_ou and ou_over < 0.35:
        reasons.append("wde_over_but_ecse_low_scoring_mass")
    wde_btts = str(wde.get("btts_pick") or "").lower()
    btts_mass = _btts_mass(top10)
    if wde_btts == "no" and btts_mass > 0.55:
        reasons.append("wde_btts_no_but_ecse_btts_mass_high")
    if wde_btts == "yes" and btts_mass < 0.25:
        reasons.append("wde_btts_yes_but_ecse_btts_mass_low")
    if not reasons:
        return {"status": "CONSISTENT", "reasons": []}
    major = any(
        x in reasons
        for x in (
            "wde_home_but_ecse_top3_favor_away",
            "wde_away_but_ecse_top3_favor_home",
            "wde_under_but_ecse_high_scoring_mass",
            "wde_btts_no_but_ecse_btts_mass_high",
        )
    )
    return {"status": "MAJOR_DIVERGENCE" if major else "MINOR_DIVERGENCE", "reasons": reasons}


def _parse_wde_full(conn, fixture_id: int, comp_key: str, settings: Settings) -> dict[str, Any]:
    wde = _load_wde(fixture_id, settings, comp_key) or {}
    row = conn.execute(
        "SELECT payload_json FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1",
        (fixture_id,),
    ).fetchone()
    payload: dict[str, Any] = {}
    if row:
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            payload = {}
    probs = payload.get("probabilities") or {}
    one = payload.get("one_x_two") or {}
    if not probs and one:
        probs = {
            "home_win": one.get("home") or one.get("home_win"),
            "draw": one.get("draw"),
            "away_win": one.get("away") or one.get("away_win"),
        }
    ou = probs.get("over_under_2_5") or (payload.get("detailed_markets") or {}).get("over_under_25") or {}
    btts = probs.get("btts") or (payload.get("extended_markets") or {}).get("btts") or {}
    return {
        **wde,
        "home_prob": probs.get("home_win") or probs.get("home"),
        "draw_prob": probs.get("draw"),
        "away_prob": probs.get("away_win") or probs.get("away"),
        "btts": btts,
        "over_under": ou,
        "model_version": payload.get("prediction_engine_version") or payload.get("model_version"),
        "generated_at": payload.get("predicted_at") or payload.get("generated_at"),
        "no_bet": payload.get("no_bet_flag"),
    }


def _first_goal_block(
    service: GoalTimingPredictionService,
    fixture_id: int,
    comp_key: str,
    *,
    persist: bool,
) -> dict[str, Any]:
    try:
        fg = service.predict_fixture(fixture_id, persist=persist, competition_key=comp_key)
    except Exception as exc:
        return {"available": False, "error": str(exc)}
    if fg.get("error"):
        return {"available": False, "error": fg.get("error"), "enabled_leagues": fg.get("enabled_leagues")}
    pred = fg.get("prediction") or {}
    scorers = pred.get("top_scorers") or pred.get("scorer_candidates") or []
    top_scorer = scorers[0] if scorers else {}
    return {
        "available": True,
        "first_goal_team": pred.get("first_goal_team"),
        "first_goal_time_range": pred.get("first_goal_time_range"),
        "display_estimated_first_goal_minute": pred.get("display_estimated_first_goal_minute"),
        "top_scorer": top_scorer.get("name") or top_scorer.get("player_name"),
        "top_scorer_probability": top_scorer.get("probability"),
        "scorer_candidates": scorers[:5],
        "model_version": pred.get("model_version"),
        "prediction_id": fg.get("prediction_id"),
        "persisted": fg.get("persisted"),
    }


def _reliability_tier(wde_conf: float, ecse_top1_prob: float, consistency: str, data_score: int) -> str:
    if consistency == "MAJOR_DIVERGENCE" or data_score < 2:
        return "LOW"
    if wde_conf >= 60 and ecse_top1_prob >= 0.12 and consistency == "CONSISTENT":
        return "HIGH"
    if wde_conf >= 50 and ecse_top1_prob >= 0.08:
        return "MEDIUM"
    return "LOW"


def freeze_batch_snapshot(
    conn: sqlite3.Connection,
    *,
    batch_id: str,
    target_date: str,
    report: dict[str, Any],
) -> tuple[int | None, str]:
    ensure_batch_tables(conn)
    fid = int(report["fixture"]["fixture_id"])
    existing = conn.execute(
        "SELECT id FROM owner_league_batch_snapshots WHERE batch_id=? AND fixture_id=?",
        (batch_id, fid),
    ).fetchone()
    if existing:
        return None, "already_exists"
    snap = {
        "batch_id": batch_id,
        "target_date": target_date,
        "fixture_id": fid,
        "prediction_timestamp": _utc_now(),
        "prediction_date": target_date,
        "kickoff": report["fixture"].get("kickoff_utc"),
        "competition": report["fixture"].get("competition_name"),
        "competition_type": report["fixture"].get("competition_type"),
        "home_team": report["fixture"].get("home_team"),
        "away_team": report["fixture"].get("away_team"),
        "wde": report.get("wde"),
        "ecse": report.get("ecse"),
        "first_goal": report.get("first_goal"),
        "confidence": report.get("reliability", {}).get("tier"),
        "consistency_flag": report.get("consistency", {}).get("status"),
        "no_bet": report.get("wde", {}).get("no_bet"),
        "odds": report.get("data_readiness"),
        "pipeline": PHASE,
    }
    try:
        cur = conn.execute(
            """
            INSERT INTO owner_league_batch_snapshots
            (batch_id, target_date, fixture_id, competition_key, competition_type,
             kickoff_utc, snapshot_json, prediction_timestamp, is_frozen)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                batch_id,
                target_date,
                fid,
                report["fixture"].get("competition_key"),
                report["fixture"].get("competition_type"),
                report["fixture"].get("kickoff_utc"),
                json.dumps(snap, ensure_ascii=False, default=str),
                snap["prediction_timestamp"],
            ),
        )
        conn.commit()
        return int(cur.lastrowid), "inserted"
    except sqlite3.IntegrityError:
        conn.rollback()
        return None, "duplicate"


def load_frozen_snapshot(conn: sqlite3.Connection, batch_id: str, fixture_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT snapshot_json FROM owner_league_batch_snapshots WHERE batch_id=? AND fixture_id=? AND is_frozen=1",
        (batch_id, int(fixture_id)),
    ).fetchone()
    if not row:
        return None
    raw = row["snapshot_json"] if isinstance(row, sqlite3.Row) else row[0]
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def run_batch_predictions(
    *,
    date_arg: str = "tomorrow",
    timezone: str = TZ,
    dry_run: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    discovery = discover_and_select_fixtures(date_arg=date_arg, timezone=timezone, settings=settings)
    target = date.fromisoformat(discovery["target_date"])
    batch_id = discovery["batch_id"]

    if discovery["preselected_count"] < SELECT_COUNT:
        return {
            "status": "TOMORROW_4_LEAGUE_PREDICTIONS_BLOCKED",
            "reason": f"only_{discovery['preselected_count']}_candidates",
            "discovery": discovery,
        }

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    conn = connect(settings.sqlite_path)
    ensure_ecse_live_tables(conn)
    ensure_batch_tables(conn)
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()

    selected_pool = list(discovery["selected"])
    all_by_id = {int(c["fixture_id"]): c for c in discovery.get("all_candidates") or []}

    final_selected: list[dict[str, Any]] = []
    tried: set[int] = set()

    def _try_add_candidate(cand: dict[str, Any]) -> bool:
        fid = int(cand["fixture_id"])
        if fid in tried:
            return False
        tried.add(fid)
        _upsert_fixtures(repo, [cand])
        fx = DailyFixture(
            fixture_id=fid,
            provider_fixture_id=fid,
            competition_key=cand["competition_key"],
            home_team=str(cand["home_team"]),
            away_team=str(cand["away_team"]),
            kickoff_utc=str(cand["kickoff_utc"]),
            status=str(cand.get("status") or "NS"),
            season=int(cand["season"]) if cand.get("season") else None,
            coverage_sources=["api_football"],
            provider_ids={"api_football": fid},
        )
        if not dry_run:
            run_odds_freshness_refresh(
                date_arg=discovery["target_date"],
                timezone=timezone,
                fixture_id=fid,
                mode="refresh",
                max_provider_calls=15,
                dry_run=False,
                source="auto",
                settings=settings,
            )
        after = scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)
        if not after.get("has_1x2"):
            return False
        if after.get("odds_freshness") == "stale":
            return False
        fx_row = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
        ecse_pred = build_ecse_live_prediction(conn, fid, fx_row)
        if not ecse_pred:
            return False
        cand["post_refresh_readiness"] = after
        cand["post_refresh_ecse"] = bool(ecse_pred)
        final_selected.append(cand)
        return True

    for cand in selected_pool:
        if len(final_selected) >= SELECT_COUNT:
            break
        _try_add_candidate(cand)

    for cand in sorted(
        [all_by_id[i] for i in all_by_id if int(i) not in tried],
        key=lambda x: -x.get("selection_score", 0),
    ):
        if len(final_selected) >= SELECT_COUNT:
            break
        _try_add_candidate(cand)

    if len(final_selected) < SELECT_COUNT:
        repo.close()
        conn.close()
        return {
            "status": "TOMORROW_4_LEAGUE_PREDICTIONS_BLOCKED",
            "reason": f"only_{len(final_selected)}_fixtures_with_fresh_odds_after_refresh",
            "discovery": discovery,
            "post_refresh_selected": final_selected,
        }

    fixtures = _upsert_fixtures(repo, final_selected[:SELECT_COUNT])
    fg_service = GoalTimingPredictionService(settings)

    match_reports: list[dict[str, Any]] = []
    freeze_results: list[dict[str, Any]] = []

    for fx in fixtures:
        fid = fx.provider_fixture_id
        refresh = {"skipped": True, "reason": "already_refreshed_in_selection"}
        if dry_run:
            refresh = run_odds_freshness_refresh(
                date_arg=discovery["target_date"],
                timezone=timezone,
                fixture_id=fid,
                mode="audit",
                max_provider_calls=15,
                dry_run=True,
                source="auto",
                settings=settings,
            )
        after = scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)
        snap = _latest_odds_snapshot(conn, fid)
        payload = snap.get("payload") if snap else None
        if snap and snap.get("payload_json"):
            try:
                payload = json.loads(snap["payload_json"])
            except json.JSONDecodeError:
                pass
        norm = normalize_uefa_odds_snapshot(payload, fixture_id=fid) if payload and not is_fake_odds_payload(payload) else None
        readiness = assess_ecse_readiness(conn, fid, normalized=norm)

        if not dry_run:
            run_daily_predictions([fx], mode="wde_and_ecse", dry_run=False, force=False, settings=settings)

        fx_row = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
        ecse_pred = build_ecse_live_prediction(conn, fid, fx_row)
        wde = _parse_wde_full(conn, fid, fx.competition_key, settings)
        ecse_db = _load_ecse(conn, fid)
        consistency = _consistency(wde, ecse_pred)
        owner = _owner_label(
            wde,
            ecse_db
            or (
                {
                    "top_1_score": ecse_pred.get("top_1_score"),
                    "confidence_score": ecse_pred.get("confidence_score"),
                }
                if ecse_pred
                else None
            ),
        )
        first_goal = _first_goal_block(fg_service, fid, fx.competition_key, persist=not dry_run)

        top10 = _ecse_top_list(ecse_pred, 10)
        top1_prob = (top10[0]["probability"] / 100.0) if top10 else 0.0
        data_score = sum(
            [
                bool(after.get("has_1x2")),
                bool(after.get("has_ou25")),
                bool(after.get("has_btts")),
                bool(wde.get("predicted_1x2")),
                bool(ecse_pred),
            ]
        )
        tier = _reliability_tier(float(wde.get("confidence_score") or 0), top1_prob, consistency["status"], data_score)
        comp = get_competition(fx.competition_key)

        report = {
            "fixture": {
                "fixture_id": fid,
                "provider_fixture_id": fid,
                "competition_key": fx.competition_key,
                "competition_name": comp.name,
                "competition_type": classify_competition_type(
                    fx.competition_key, comp=comp, round_name=fx_row.get("round_name")
                ),
                "country": comp.country,
                "home_team": fx.home_team,
                "away_team": fx.away_team,
                "kickoff_utc": fx.kickoff_utc,
                "kickoff_vienna": _kickoff_vienna(fx.kickoff_utc),
                "status": fx.status,
                "data_source": "api_football",
            },
            "data_readiness": {
                "has_1x2": after.get("has_1x2"),
                "has_btts": after.get("has_btts"),
                "has_ou25": after.get("has_ou25"),
                "bookmaker_count": norm.bookmaker_count if norm else after.get("bookmaker_count"),
                "odds_provider": after.get("odds_source"),
                "odds_timestamp": after.get("odds_snapshot_time"),
                "odds_freshness": after.get("odds_freshness"),
                "ecse_ready": readiness.get("ecse_ready"),
                "odds_refresh": refresh.to_dict() if hasattr(refresh, "to_dict") else refresh,
            },
            "wde": wde,
            "ecse": {
                "ready": bool(ecse_pred),
                "lambda_home": ecse_pred.get("lambda_home") if ecse_pred else None,
                "lambda_away": ecse_pred.get("lambda_away") if ecse_pred else None,
                "top1": top10[0] if top10 else None,
                "top2": top10[1] if len(top10) > 1 else None,
                "top3": top10[2] if len(top10) > 2 else None,
                "top3_list": top10[:3],
                "top5": top10[:5],
                "model_version": ecse_pred.get("model_version") if ecse_pred else None,
                "frozen_snapshot": has_snapshot(conn, fid),
                "ecse_snapshot": get_snapshot(conn, fid),
            },
            "first_goal": first_goal,
            "consistency": consistency,
            "owner_label": owner,
            "reliability": {
                "tier": tier,
                "wde_confidence": wde.get("confidence_score"),
                "ecse_top1_concentration": top1_prob,
                "data_completeness": data_score,
                "agreement": consistency["status"],
            },
        }
        match_reports.append(report)

        if not dry_run:
            sid, reason = freeze_batch_snapshot(
                conn,
                batch_id=batch_id,
                target_date=discovery["target_date"],
                report=report,
            )
            freeze_results.append({"fixture_id": fid, "snapshot_id": sid, "status": reason})

    def rank_key(m: dict) -> float:
        c = float(m["reliability"].get("wde_confidence") or 0)
        e = float(m["reliability"].get("ecse_top1_concentration") or 0)
        pen = 0.5 if m["consistency"]["status"] == "MAJOR_DIVERGENCE" else (
            0.85 if m["consistency"]["status"] == "MINOR_DIVERGENCE" else 1.0
        )
        return c * (0.5 + e) * pen

    ranked = sorted(match_reports, key=rank_key, reverse=True)
    for i, m in enumerate(ranked, 1):
        m["reliability"]["confidence_rank"] = i

    payload = {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "target_date": discovery["target_date"],
        "batch_id": batch_id,
        "timezone": timezone,
        "dry_run": dry_run,
        "discovery": discovery,
        "matches": match_reports,
        "ranking": [
            {
                "rank": m["reliability"]["confidence_rank"],
                "match": f"{m['fixture']['home_team']} vs {m['fixture']['away_team']}",
                "tier": m["reliability"]["tier"],
            }
            for m in ranked
        ],
        "strongest_3_picks": ranked[:3],
        "freeze_results": freeze_results,
        "status": "TOMORROW_4_LEAGUE_PRODUCTION_PREDICTIONS_READY"
        if len(match_reports) == SELECT_COUNT and not dry_run
        else ("DRY_RUN" if dry_run else "TOMORROW_4_LEAGUE_PREDICTIONS_BLOCKED"),
    }

    out_dir = artifact_dir_for(target)
    out_dir.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    payload_path = out_dir / "payload.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    prediction_report_path(target).write_text(_render_prediction_md(payload), encoding="utf-8")
    payload["payload_path"] = str(payload_path)
    payload["prediction_report_path"] = str(prediction_report_path(target))

    repo.close()
    conn.close()
    return payload


def _scorelines_from_rows(rows: list[Any]) -> list[str]:
    out: list[str] = []
    for item in rows:
        if isinstance(item, dict):
            sl = item.get("scoreline") or item.get("label")
            if sl:
                out.append(str(sl))
        elif item:
            out.append(str(item))
    return out


def _eval_symbol(hit: bool | None) -> str:
    if hit is None:
        return "➖ NOT EVALUATED"
    return "✅ HIT" if hit else "❌ MISS"


def _is_finished(status: str) -> bool:
    s = status.upper()
    return s in FINISHED_STATUSES or s in ("FT", "AET", "PEN", "FINISHED")


def evaluate_batch(
    *,
    date_arg: str = "tomorrow",
    timezone: str = TZ,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    target = resolve_target_date(date_arg, timezone)
    batch_id = batch_id_for(target)
    conn = connect(settings.sqlite_path)
    ensure_batch_tables(conn)

    rows = conn.execute(
        "SELECT fixture_id, snapshot_json, competition_type FROM owner_league_batch_snapshots WHERE batch_id=?",
        (batch_id,),
    ).fetchall()
    if not rows:
        conn.close()
        return {
            "status": "no_frozen_snapshots",
            "batch_id": batch_id,
            "target_date": target.isoformat(),
        }

    evaluations: list[dict[str, Any]] = []
    metrics = {
        "wde_1x2": {"correct": 0, "evaluated": 0},
        "btts": {"correct": 0, "evaluated": 0},
        "over_under": {"correct": 0, "evaluated": 0},
        "ecse_top1": {"correct": 0, "evaluated": 0},
        "ecse_top3": {"correct": 0, "evaluated": 0},
        "ecse_top5": {"correct": 0, "evaluated": 0},
        "first_goal_team": {"correct": 0, "evaluated": 0},
        "first_goal_bucket": {"correct": 0, "evaluated": 0},
        "first_goal_scorer": {"correct": 0, "evaluated": 0},
    }
    segment_buckets: dict[str, list[dict[str, Any]]] = {}

    for row in rows:
        snap = json.loads(row["snapshot_json"])
        fid = int(row["fixture_id"])
        comp_type = row["competition_type"] or snap.get("competition_type") or "other/unknown"
        fx_row = conn.execute("SELECT status FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        status = str(fx_row["status"] if fx_row else "NS").upper()
        result = load_fixture_result(conn, fid)

        ev: dict[str, Any] = {
            "fixture_id": fid,
            "match": f"{snap.get('home_team')} vs {snap.get('away_team')}",
            "competition_type": comp_type,
            "evaluation_status": "WAITING_RESULT",
        }

        if not result or result.get("home_goals") is None or not _is_finished(status):
            evaluations.append(ev)
            continue

        hg = int(result["home_goals"])
        ag = int(result["away_goals"])
        actual_score = f"{hg}-{ag}"
        wde = snap.get("wde") or {}
        ecse = snap.get("ecse") or {}
        fg = snap.get("first_goal") or {}

        actual_x2 = actual_1x2(hg, ag)
        actual_ou = actual_over_under(hg, ag)
        btts_actual = "yes" if hg > 0 and ag > 0 else "no"
        pred_x2 = wde.get("predicted_1x2")
        pred_ou = wde.get("predicted_over_under_2_5") or (wde.get("over_under") or {}).get("selection")
        btts_pred = wde.get("btts_pick") or (wde.get("btts") or {}).get("selection")

        top1 = str((ecse.get("top1") or {}).get("scoreline") or "")
        top3 = _scorelines_from_rows(ecse.get("top3_list") or ecse.get("top3") or [])
        top5_rows = ecse.get("top5") or []
        top5 = _scorelines_from_rows(top5_rows)

        wde_1x2_hit = pred_x2 == actual_x2 if pred_x2 else None
        btts_hit = btts_pred == btts_actual if btts_pred else None
        ou_hit = pred_ou == actual_ou if pred_ou else None
        top1_hit = top1 == actual_score if top1 else None
        top3_hit = actual_score in top3 if top3 else None
        top5_hit = actual_score in top5 if top5 else None

        fg_team_hit = None
        fg_bucket_hit = None
        fg_scorer_hit = None
        if fg.get("available"):
            first_team = result.get("first_goal_team")
            if first_team and fg.get("first_goal_team"):
                pred_team = str(fg.get("first_goal_team")).lower()
                fg_team_hit = pred_team in str(first_team).lower() or str(first_team).lower() in pred_team
            minute = result.get("first_goal_minute")
            bucket = fg.get("first_goal_time_range")
            if minute is not None and bucket:
                fg_bucket_hit = _minute_in_bucket(int(minute), str(bucket))
            scorer = result.get("first_goal_scorer") or result.get("first_goal_player")
            pred_scorer = fg.get("top_scorer")
            if scorer and pred_scorer:
                fg_scorer_hit = _names_match(str(pred_scorer), str(scorer))

        ev.update(
            {
                "evaluation_status": "EVALUATED",
                "actual_score": actual_score,
                "wde_1x2": {"predicted": pred_x2, "actual": actual_x2, "hit": wde_1x2_hit},
                "btts": {"predicted": btts_pred, "actual": btts_actual, "hit": btts_hit},
                "over_under": {"predicted": pred_ou, "actual": actual_ou, "hit": ou_hit},
                "ecse_top1": {"predicted": top1, "hit": top1_hit},
                "ecse_top3": {"hit": top3_hit},
                "ecse_top5": {"hit": top5_hit},
                "first_goal_team": {"predicted": fg.get("first_goal_team"), "hit": fg_team_hit},
                "first_goal_bucket": {"predicted": fg.get("first_goal_time_range"), "hit": fg_bucket_hit},
                "first_goal_scorer": {"predicted": fg.get("top_scorer"), "hit": fg_scorer_hit},
            }
        )

        for key, hit in (
            ("wde_1x2", wde_1x2_hit),
            ("btts", btts_hit),
            ("over_under", ou_hit),
            ("ecse_top1", top1_hit),
            ("ecse_top3", top3_hit),
            ("ecse_top5", top5_hit),
            ("first_goal_team", fg_team_hit),
            ("first_goal_bucket", fg_bucket_hit),
            ("first_goal_scorer", fg_scorer_hit),
        ):
            if hit is not None:
                metrics[key]["evaluated"] += 1
                if hit:
                    metrics[key]["correct"] += 1

        segment_buckets.setdefault(comp_type, []).append(ev)
        evaluations.append(ev)

        conn.execute(
            """
            INSERT INTO owner_league_batch_evaluations (batch_id, fixture_id, competition_type, evaluation_json, evaluated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(batch_id, fixture_id) DO UPDATE SET
                competition_type=excluded.competition_type,
                evaluation_json=excluded.evaluation_json,
                evaluated_at=excluded.evaluated_at
            """,
            (batch_id, fid, comp_type, json.dumps(ev, ensure_ascii=False, default=str), _utc_now()),
        )
    conn.commit()

    segment_stats = _segment_stats(segment_buckets)
    out = {
        "phase": PHASE,
        "batch_id": batch_id,
        "target_date": target.isoformat(),
        "evaluated_count": sum(1 for e in evaluations if e.get("evaluation_status") == "EVALUATED"),
        "waiting_count": sum(1 for e in evaluations if e.get("evaluation_status") != "EVALUATED"),
        "metrics": {
            k: {
                **v,
                "accuracy": round(v["correct"] / v["evaluated"], 4) if v["evaluated"] else None,
            }
            for k, v in metrics.items()
        },
        "fixtures": evaluations,
        "competition_type_segments": segment_stats,
        "small_sample_warning": len(evaluations) < 10,
    }

    evaluation_report_path(target).write_text(_render_evaluation_md(out), encoding="utf-8")
    artifact_dir_for(target).mkdir(parents=True, exist_ok=True)
    eval_path = artifact_dir_for(target) / "evaluation.json"
    eval_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    out["evaluation_report_path"] = str(evaluation_report_path(target))
    out["evaluation_json_path"] = str(eval_path)
    conn.close()
    return out


def _minute_in_bucket(minute: int, bucket: str) -> bool:
    b = bucket.strip()
    if b == "0-15":
        return 0 <= minute <= 15
    if b == "16-30":
        return 16 <= minute <= 30
    if b in ("31-45+", "31-45"):
        return 31 <= minute <= 45
    if b == "46-60":
        return 46 <= minute <= 60
    if b == "61-75":
        return 61 <= minute <= 75
    if b in ("76-90+", "76-90"):
        return minute >= 76
    return False


def _names_match(a: str, b: str) -> bool:
    na = _slug(a)
    nb = _slug(b)
    return na == nb or na in nb or nb in na


def _segment_stats(buckets: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for seg, rows in buckets.items():
        evaluated = [r for r in rows if r.get("evaluation_status") == "EVALUATED"]
        if not evaluated:
            out[seg] = {"evaluated_fixtures": 0, "warning": "no_evaluated_fixtures"}
            continue
        def acc(field: str) -> float | None:
            hits = [r[field]["hit"] for r in evaluated if r.get(field, {}).get("hit") is not None]
            return round(sum(1 for h in hits if h) / len(hits), 4) if hits else None
        out[seg] = {
            "evaluated_fixtures": len(evaluated),
            "wde_1x2_accuracy": acc("wde_1x2"),
            "btts_accuracy": acc("btts"),
            "over_under_accuracy": acc("over_under"),
            "ecse_top1_hit_rate": acc("ecse_top1"),
            "ecse_top3_hit_rate": acc("ecse_top3"),
            "ecse_top5_hit_rate": acc("ecse_top5"),
            "first_goal_team_accuracy": acc("first_goal_team"),
            "first_goal_bucket_accuracy": acc("first_goal_bucket"),
            "scorer_accuracy": acc("first_goal_scorer"),
            "small_sample_warning": len(evaluated) < 5,
        }
    return out


def _render_prediction_md(payload: dict[str, Any]) -> str:
    lines = [
        f"# Tomorrow 4 League Match Predictions",
        "",
        f"Date: **{payload.get('target_date')}** | Batch: `{payload.get('batch_id')}`",
        f"Generated: {payload.get('generated_at_utc')}",
        "",
        "## Summary table",
        "",
        "| Match | Competition | WDE 1X2 | BTTS | O/U | ECSE Top1 | Top2 | Top3 | First Goal Team | Confidence | Flag |",
        "|-------|-------------|---------|------|-----|-----------|------|------|-----------------|------------|------|",
    ]
    for m in payload.get("matches") or []:
        fx = m["fixture"]
        w = m["wde"]
        e = m["ecse"]
        fg = m.get("first_goal") or {}
        btts_sel = (w.get("btts") or {}).get("selection") or w.get("btts_pick")
        ou_sel = (w.get("over_under") or {}).get("selection") or w.get("predicted_over_under_2_5")
        lines.append(
            f"| {fx['home_team']} vs {fx['away_team']} | {fx['competition_name']} | {w.get('predicted_1x2') or '—'} | "
            f"{btts_sel or '—'} | {ou_sel or '—'} | {(e.get('top1') or {}).get('scoreline', '—')} | "
            f"{(e.get('top2') or {}).get('scoreline', '—')} | {(e.get('top3') or {}).get('scoreline', '—')} | "
            f"{fg.get('first_goal_team') or '—'} | {m['reliability']['tier']} | {m['consistency']['status']} |"
        )
    lines.extend(["", "## Fixture IDs and kickoff Vienna", ""])
    for m in payload.get("matches") or []:
        fx = m["fixture"]
        lines.append(
            f"- `{fx['fixture_id']}` — {fx['home_team']} vs {fx['away_team']} — {fx['kickoff_vienna']}"
        )
    lines.extend(["", "## Strongest 3 model picks", ""])
    for m in payload.get("strongest_3_picks") or []:
        fx = m["fixture"]
        lines.append(
            f"### Rank {m['reliability']['confidence_rank']}: {fx['home_team']} vs {fx['away_team']}"
        )
        lines.append(f"- Preferred market: WDE 1X2 `{m['wde'].get('predicted_1x2')}`")
        lines.append(f"- ECSE Top1: `{(m['ecse'].get('top1') or {}).get('scoreline')}`")
        lines.append(f"- Confidence: {m['reliability']['tier']} | Consistency: {m['consistency']['status']}")
        lines.append("")
    lines.extend(
        [
            "## Technical validation summary",
            "",
            f"- Canonical WDE: PredictPipeline",
            f"- Canonical ECSE: build_ecse_live_prediction",
            f"- First Goal: GoalTimingPredictionService (league-gated)",
            f"- Fixtures selected: {len(payload.get('matches') or [])}",
            f"- Status: `{payload.get('status')}`",
        ]
    )
    return "\n".join(lines)


def _render_evaluation_md(payload: dict[str, Any]) -> str:
    lines = [
        "# Tomorrow 4 League Match Evaluation",
        "",
        f"Batch: `{payload.get('batch_id')}` | Date: {payload.get('target_date')}",
        "",
        "## Overall summary",
        "",
        "| Metric | Correct | Evaluated | Accuracy |",
        "|--------|---------|-----------|----------|",
    ]
    for name, m in (payload.get("metrics") or {}).items():
        acc = f"{100 * m['accuracy']:.1f}%" if m.get("accuracy") is not None else "—"
        lines.append(f"| {name} | {m.get('correct', 0)} | {m.get('evaluated', 0)} | {acc} |")
    lines.extend(["", "## Match-by-match evaluation", ""])
    lines.append(
        "| Match | Actual Score | WDE 1X2 | BTTS | O/U | ECSE Top1 | ECSE Top3 | ECSE Top5 | FG Team | FG Bucket | Scorer |"
    )
    lines.append("|-------|--------------|---------|------|-----|-----------|-----------|-----------|---------|-----------|--------|")
    for ev in payload.get("fixtures") or []:
        if ev.get("evaluation_status") != "EVALUATED":
            lines.append(f"| {ev.get('match')} | — | ➖ | ➖ | ➖ | ➖ | ➖ | ➖ | ➖ | ➖ | ➖ |")
            continue
        lines.append(
            f"| {ev.get('match')} | {ev.get('actual_score')} | "
            f"{_eval_symbol(ev.get('wde_1x2', {}).get('hit'))} | "
            f"{_eval_symbol(ev.get('btts', {}).get('hit'))} | "
            f"{_eval_symbol(ev.get('over_under', {}).get('hit'))} | "
            f"{_eval_symbol(ev.get('ecse_top1', {}).get('hit'))} | "
            f"{_eval_symbol(ev.get('ecse_top3', {}).get('hit'))} | "
            f"{_eval_symbol(ev.get('ecse_top5', {}).get('hit'))} | "
            f"{_eval_symbol(ev.get('first_goal_team', {}).get('hit'))} | "
            f"{_eval_symbol(ev.get('first_goal_bucket', {}).get('hit'))} | "
            f"{_eval_symbol(ev.get('first_goal_scorer', {}).get('hit'))} |"
        )
    if payload.get("small_sample_warning"):
        lines.extend(["", "> Small-sample warning: do not overstate significance from this batch alone.", ""])
    lines.extend(["", "## Competition-type comparison", ""])
    for seg, stats in (payload.get("competition_type_segments") or {}).items():
        lines.append(f"### {seg}")
        lines.append(json.dumps(stats, indent=2))
        lines.append("")
    return "\n".join(lines)


def evaluate_all_pending_frozen_batches(*, settings: Settings | None = None) -> dict[str, Any]:
    """Post-match: evaluate every frozen league batch (idempotent)."""
    from worldcup_predictor.owner_predict_eval.domestic_league_control import _evaluate_batch_snapshots

    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    ensure_batch_tables(conn)
    rows = conn.execute(
        "SELECT DISTINCT batch_id FROM owner_league_batch_snapshots WHERE is_frozen=1 ORDER BY batch_id"
    ).fetchall()
    batches: dict[str, Any] = {}
    total_evaluated = 0
    total_waiting = 0
    for row in rows:
        batch_id = str(row[0] if not isinstance(row, sqlite3.Row) else row["batch_id"])
        out = _evaluate_batch_snapshots(conn, batch_id)
        batches[batch_id] = out
        total_evaluated += int(out.get("evaluated_count") or 0)
        total_waiting += int(out.get("waiting_count") or 0)
    conn.close()
    return {
        "phase": PHASE,
        "batch_count": len(batches),
        "total_evaluated": total_evaluated,
        "total_waiting": total_waiting,
        "batches": batches,
    }
