#!/usr/bin/env python3
"""Owner-only today exact-score prediction report (read-only, no public changes)."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.accuracy.history_store import PredictionHistoryStore
from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import get_competition, list_competition_keys
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.quota.prediction_cache import get_cached_prediction
from worldcup_predictor.research.ecse_wc.knockout_draw_pen_risk import evaluate_fixture_knockout_risk
from worldcup_predictor.research.ecse_live.store import get_snapshot
from worldcup_predictor.research.ecse_x2_m6.store import read_shadow_shortlists
from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.owner.euro_c3_odds_watch import readiness_for_owner_report
from worldcup_predictor.research.ecse_x3_b.store import get_owner_shadow_for_fixture

REPORT_DIR = ROOT / "reports" / "owner"
SUPPORTED_API_LEAGUES = {
    1: ("world_cup_2026", "World Cup 2026", "2026"),
    78: ("bundesliga", "Bundesliga", "2025"),
    39: ("premier_league", "Premier League", "2025"),
    2: ("champions_league", "UEFA Champions League", "2025"),
    3: ("europa_league", "UEFA Europa League", "2025"),
    848: ("conference_league", "UEFA Conference League", "2025"),
}
LIVE_STATUSES = frozenset({"1H", "HT", "2H", "ET", "BT", "P", "LIVE", "INT"})
FINISHED_STATUSES = frozenset({"FT", "AET", "PEN", "AWD", "WO", "CANC", "ABD", "PST"})


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _kickoff_date(value: str | None) -> str | None:
    dt = _parse_kickoff(value)
    return dt.date().isoformat() if dt else None


def _format_kickoff(value: str | None, tz: ZoneInfo) -> tuple[str | None, str | None]:
    dt = _parse_kickoff(value)
    if dt is None:
        return None, None
    utc_text = dt.strftime("%Y-%m-%d %H:%M UTC")
    local_text = dt.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z")
    return utc_text, local_text


def _scoreline_to_1x2(scoreline: str | None) -> str | None:
    if not scoreline or "-" not in scoreline:
        return None
    try:
        home_s, away_s = scoreline.replace(":", "-").split("-", 1)
        home_g, away_g = int(home_s.strip()), int(away_s.strip())
    except (TypeError, ValueError):
        return None
    if home_g > away_g:
        return "home_win"
    if home_g < away_g:
        return "away_win"
    return "draw"


def _normalize_1x2(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).lower().strip().replace(" ", "_")
    mapping = {
        "home": "home_win",
        "away": "away_win",
        "1": "home_win",
        "x": "draw",
        "2": "away_win",
    }
    return mapping.get(text, text)


def _status_label(api_status: str | None, kickoff_utc: str | None) -> str:
    code = str(api_status or "").upper()
    if code in LIVE_STATUSES:
        return "live"
    if code in FINISHED_STATUSES:
        return "finished"
    if code in {"", "NS", "TBD", "SCHEDULED", "TIMED", "NOT STARTED"}:
        kickoff = _parse_kickoff(kickoff_utc)
        if kickoff and kickoff < datetime.now(timezone.utc):
            return "finished"
        return "upcoming"
    return "upcoming"


def _top1_from_rows(rows: list[dict[str, Any]] | None) -> str | None:
    if not rows:
        return None
    first = rows[0]
    if isinstance(first, dict):
        return str(first.get("scoreline") or first.get("label") or "")
    return str(first)


def _score_rows(snapshot: dict[str, Any], key: str, fallback_key: str) -> list[dict[str, Any]]:
    rows = snapshot.get(key) or snapshot.get(fallback_key) or []
    if isinstance(rows, str):
        try:
            rows = json.loads(rows)
        except json.JSONDecodeError:
            rows = []
    out: list[dict[str, Any]] = []
    for item in rows:
        if isinstance(item, dict):
            out.append(item)
        elif isinstance(item, str):
            out.append({"scoreline": item})
    return out


def _load_wde(fixture_id: int, settings: Settings, competition_key: str | None = None) -> dict[str, Any] | None:
    comp_key = competition_key or "world_cup_2026"
    season = 2026 if comp_key == "world_cup_2026" else 2025
    store = WorldcupPredictionStore(settings)
    payload = store.get(fixture_id, competition_key=comp_key, season=season, locale="en")
    source = "worldcup_stored_predictions"
    if payload is None:
        payload = get_cached_prediction(
            fixture_id,
            competition_key=comp_key,
            season=season,
            locale="en",
            settings=settings,
        )
        source = "prediction_cache"
    if payload is None:
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        row = repo.get_worldcup_stored_prediction(fixture_id)
        if row and str(row.get("competition_key") or "") == comp_key and row.get("payload_json"):
            try:
                payload = json.loads(row["payload_json"])
                source = "worldcup_stored_predictions"
            except json.JSONDecodeError:
                payload = None
    if payload is None:
        record = PredictionHistoryStore().latest_for_fixture(fixture_id)
        if record is None:
            return None
        ext: dict[str, Any] = {}
        if record.extended_markets_json:
            try:
                ext = json.loads(record.extended_markets_json)
            except json.JSONDecodeError:
                ext = {}
        btts_pick = None
        btts_block = ext.get("btts") or {}
        if btts_block:
            yes_prob = float(btts_block.get("option_a") or 0)
            label_a = str(btts_block.get("label_a") or "yes").lower()
            btts_pick = "yes" if (label_a == "yes" and yes_prob >= 0.5) else "no"
        return {
            "source": "prediction_history",
            "predicted_1x2": record.predicted_1x2,
            "predicted_over_under_2_5": record.predicted_over_under_2_5,
            "predicted_scoreline": record.predicted_scoreline,
            "confidence_score": record.confidence_score,
            "no_bet_flag": record.no_bet_flag,
            "risk_level": record.risk_level,
            "btts_pick": btts_pick,
            "short_reason": (
                "No-bet flag active — caution advised"
                if record.no_bet_flag
                else f"Confidence {record.confidence_score:.0f}; risk {record.risk_level}"
            ),
        }

    one_x_two = payload.get("one_x_two") or {}
    over_under = payload.get("over_under") or {}
    btts = (payload.get("extended_markets") or {}).get("btts") or {}
    btts_pick = None
    if btts:
        yes = float(btts.get("yes") or btts.get("option_a") or 0)
        btts_pick = "yes" if yes >= 0.5 else "no"

    explanation = payload.get("explanation")
    if isinstance(explanation, dict):
        reason = explanation.get("en") or explanation.get("de") or ""
    else:
        reason = str(explanation or "")

    scoreline = payload.get("scoreline") or {}
    predicted_scoreline = None
    if isinstance(scoreline, dict):
        predicted_scoreline = scoreline.get("label") or scoreline.get("selection")

    return {
        "source": source,
        "predicted_1x2": one_x_two.get("selection") if isinstance(one_x_two, dict) else payload.get("predicted_1x2"),
        "predicted_over_under_2_5": (
            over_under.get("selection") if isinstance(over_under, dict) else payload.get("predicted_over_under")
        ),
        "predicted_scoreline": predicted_scoreline,
        "confidence_score": float(payload.get("confidence_score") or payload.get("confidence") or 0),
        "no_bet_flag": bool(payload.get("no_bet_flag", False)),
        "risk_level": payload.get("risk_level") or "medium",
        "btts_pick": btts_pick,
        "short_reason": reason[:240] if reason else f"Confidence {float(payload.get('confidence_score') or 0):.0f}",
    }


def _shadow_for_fixture(fixture_id: int) -> dict[str, Any] | None:
    for row in read_shadow_shortlists(limit=10_000):
        if int(row.get("fixture_id") or 0) == int(fixture_id):
            baseline = row.get("baseline_top10") or []
            enhanced = row.get("enhanced_top10") or []
            baseline_top1 = _top1_from_rows(baseline)
            enhanced_top1 = _top1_from_rows(enhanced)
            comparison = "no_change"
            if baseline_top1 and enhanced_top1:
                if baseline_top1 == enhanced_top1:
                    comparison = "no_change"
                elif row.get("applied"):
                    comparison = "enhanced_differs"
            return {
                "baseline_top1": baseline_top1,
                "enhanced_top1": enhanced_top1,
                "rank_movements": row.get("rank_movements") or {},
                "comparison": comparison,
                "applied": bool(row.get("applied")),
                "exclusion_reason": row.get("exclusion_reason"),
                "source": "ecse_x2_m6_shadow",
            }
    return None


def _owner_label(ecse: dict[str, Any] | None, wde: dict[str, Any] | None) -> str:
    if ecse is None or wde is None:
        return "DATA_MISSING"
    if wde.get("no_bet_flag"):
        return "NO_BET"
    ecse_x2 = _scoreline_to_1x2(ecse.get("top_1_score"))
    wde_x2 = _normalize_1x2(wde.get("predicted_1x2"))
    conf = float(wde.get("confidence_score") or 0)
    ecse_conf = float(ecse.get("confidence_score") or 0)
    agree = ecse_x2 is not None and wde_x2 is not None and ecse_x2 == wde_x2
    score_agree = (
        ecse.get("top_1_score")
        and wde.get("predicted_scoreline")
        and str(ecse.get("top_1_score")) == str(wde.get("predicted_scoreline")).replace(":", "-")
    )
    if agree and conf >= 70 and (score_agree or ecse_conf >= 0.12):
        return "STRONG_SIGNAL"
    if agree and conf >= 55:
        return "MEDIUM_SIGNAL"
    if ecse_conf < 0.10 or conf < 55 or wde.get("risk_level") == "high":
        return "WEAK_SIGNAL"
    return "MEDIUM_SIGNAL" if agree else "WEAK_SIGNAL"


def _owner_shortlist(ecse: dict[str, Any] | None, wde: dict[str, Any] | None, label: str) -> dict[str, Any]:
    top3 = ecse.get("top_3_scores") if ecse else []
    if isinstance(top3, list) and top3 and isinstance(top3[0], dict):
        alt_scores = [str(x.get("scoreline")) for x in top3[1:3] if x.get("scoreline")]
    elif isinstance(top3, list):
        alt_scores = [str(x) for x in top3[1:3]]
    else:
        alt_scores = []

    market_angle = None
    if wde:
        market_angle = {
            "1x2": wde.get("predicted_1x2"),
            "over_under_2_5": wde.get("predicted_over_under_2_5"),
            "btts": wde.get("btts_pick"),
            "double_chance": None,
        }

    note = "Exact score is high variance; prefer Top-3 cover over single-score staking."
    if label == "NO_BET":
        note = "WDE no-bet active — treat exact-score ideas as research only."
    elif label == "DATA_MISSING":
        note = "Incomplete model coverage — do not stake on missing signals."
    elif label == "STRONG_SIGNAL" and ecse:
        note = "ECSE Top-1 aligns with WDE 1X2 and scoreline; still high variance for exact score."

    return {
        "main_exact_score": ecse.get("top_1_score") if ecse else None,
        "cover_scores": alt_scores[:2],
        "best_market_angle": market_angle,
        "note": note,
    }


def _fetch_api_fixtures_for_date(target_date: str, settings: Settings) -> dict[int, dict[str, Any]]:
    client = ApiFootballClient(settings)
    out: dict[int, dict[str, Any]] = {}
    for league_id, (comp_key, comp_label, season) in SUPPORTED_API_LEAGUES.items():
        result = client._safe_get(
            "fixtures",
            {"date": target_date, "league": str(league_id), "season": season},
            placeholder_factory=lambda: None,
            ttl_seconds=300,
        )
        if not result or not result.data:
            continue
        for item in result.data:
            fx = item.get("fixture") or {}
            teams = item.get("teams") or {}
            fid = int(fx.get("id") or 0)
            if not fid:
                continue
            out[fid] = {
                "fixture_id": fid,
                "competition_key": comp_key,
                "competition_label": comp_label,
                "home_team": (teams.get("home") or {}).get("name"),
                "away_team": (teams.get("away") or {}).get("name"),
                "kickoff_utc": fx.get("date"),
                "status": (fx.get("status") or {}).get("short"),
                "source": "api_football",
            }
    return out


def discover_fixtures(
    conn,
    settings: Settings,
    *,
    target_date: str,
    competition: str | None,
    competitions: list[str] | None,
    upcoming_only: bool,
    limit: int,
    days_ahead: int | None = None,
) -> list[dict[str, Any]]:
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    candidates: dict[int, dict[str, Any]] = {}

    if days_ahead and competitions:
        from worldcup_predictor.owner.euro_b_fixture_selector import select_upcoming_uefa_fixtures

        for sel in select_upcoming_uefa_fixtures(
            conn, competition_keys=competitions, days_ahead=int(days_ahead)
        ):
            if sel.skip_reason or sel.duplicate_risk:
                continue
            fid = sel.provider_fixture_id
            candidates[fid] = {
                "fixture_id": fid,
                "competition_key": sel.competition_key,
                "competition_label": sel.competition_key.replace("_", " ").title(),
                "home_team": sel.home_team,
                "away_team": sel.away_team,
                "kickoff_utc": sel.kickoff_utc,
                "status": sel.status,
                "has_ecse": sel.has_ecse,
                "priority": 1,
                "source": sel.provider_source,
            }
    else:
        ecse_rows = conn.execute(
            """
            SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc
            FROM ecse_prediction_snapshots
            WHERE substr(COALESCE(kickoff_utc, ''), 1, 10) = ?
            """,
            (target_date,),
        ).fetchall()
        for row in ecse_rows:
            item = dict(row)
            item["has_ecse"] = True
            item["priority"] = 0 if item.get("competition_key") == "world_cup_2026" else 1
            candidates[int(item["fixture_id"])] = item

        db_rows = conn.execute(
            """
            SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status
            FROM fixtures
            WHERE substr(replace(replace(COALESCE(kickoff_utc, ''), 'T', ' '), 'Z', ''), 1, 10) = ?
              AND is_placeholder = 0
            """,
            (target_date,),
        ).fetchall()
        for row in db_rows:
            fid = int(row["fixture_id"])
            item = dict(row)
            item.setdefault("has_ecse", fid in candidates)
            item["priority"] = 0 if item.get("competition_key") == "world_cup_2026" else 2
            item["source"] = "fixtures_table"
            if fid in candidates:
                candidates[fid].update({k: v for k, v in item.items() if v is not None})
            else:
                candidates[fid] = item

        api_map = _fetch_api_fixtures_for_date(target_date, settings)
        for fid, item in api_map.items():
            if competition and item.get("competition_key") != competition:
                continue
            if fid in candidates:
                candidates[fid]["status"] = item.get("status") or candidates[fid].get("status")
                candidates[fid].setdefault("source", item.get("source"))
            else:
                item["has_ecse"] = False
                item["priority"] = 0 if item.get("competition_key") == "world_cup_2026" else 3
                candidates[fid] = item

    if competitions:
        candidates = {
            fid: row
            for fid, row in candidates.items()
            if row.get("competition_key") in competitions
        }
    elif competition:
        candidates = {fid: row for fid, row in candidates.items() if row.get("competition_key") == competition}

    if days_ahead and competitions and not candidates:
        pass
    elif days_ahead and competitions:
        end = datetime.now(timezone.utc) + timedelta(days=int(days_ahead))
        filtered: dict[int, dict[str, Any]] = {}
        for fid, row in candidates.items():
            kick = _parse_kickoff(row.get("kickoff_utc"))
            if kick and kick <= end:
                filtered[fid] = row
        candidates = filtered

    ranked: list[dict[str, Any]] = []
    for fid, row in candidates.items():
        comp_key = str(row.get("competition_key") or "world_cup_2026")
        wde = _load_wde(fid, settings, competition_key=comp_key)
        shadow = _shadow_for_fixture(fid)
        score = (
            -int(row.get("priority", 9)),
            -int(bool(row.get("has_ecse"))),
            -int(wde is not None),
            -int(shadow is not None),
            str(row.get("kickoff_utc") or ""),
        )
        row["fixture_id"] = fid
        row["_sort"] = score
        ranked.append(row)

    ranked.sort(key=lambda item: item["_sort"])
    selected: list[dict[str, Any]] = []
    for row in ranked:
        status = _status_label(row.get("status"), row.get("kickoff_utc"))
        if upcoming_only and status != "upcoming":
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def build_match_report(
    conn,
    settings: Settings,
    fixture_row: dict[str, Any],
    *,
    tz: ZoneInfo,
    include_shadow: bool,
) -> dict[str, Any]:
    fixture_id = int(fixture_row["fixture_id"])
    ecse_raw = get_snapshot(conn, fixture_id)
    ecse: dict[str, Any] | None = None
    if ecse_raw:
        top10 = _score_rows(ecse_raw, "top_10_scorelines", "top_10_scorelines_json")
        top3 = _score_rows(ecse_raw, "top_3_scores", "top_3_scores_json")
        top5 = _score_rows(ecse_raw, "top_5_scores", "top_5_scores_json")
        if not top3:
            top3 = [{"scoreline": s} if not isinstance(s, dict) else s for s in (ecse_raw.get("top_3_scores") or [])]
        ecse = {
            "source": "ecse_prediction_snapshots",
            "top_1_score": ecse_raw.get("top_1_score"),
            "top_3_scores": top3,
            "top_5_scores": top5 or top3,
            "top_10_scorelines": top10,
            "lambda_home": ecse_raw.get("lambda_home"),
            "lambda_away": ecse_raw.get("lambda_away"),
            "confidence_score": ecse_raw.get("confidence_score"),
            "data_quality_score": ecse_raw.get("data_quality_score"),
            "model_version": ecse_raw.get("model_version"),
        }

    wde = _load_wde(fixture_id, settings, competition_key=str(fixture_row.get("competition_key") or "world_cup_2026"))
    shadow_m6 = _shadow_for_fixture(fixture_id) if include_shadow else None
    shadow_x3 = get_owner_shadow_for_fixture(fixture_id) if include_shadow else None

    kickoff_utc = fixture_row.get("kickoff_utc") or (ecse_raw or {}).get("kickoff_utc")
    kickoff_utc_fmt, kickoff_local_fmt = _format_kickoff(kickoff_utc, tz)
    status = _status_label(fixture_row.get("status"), kickoff_utc)
    label = _owner_label(ecse, wde)
    shortlist = _owner_shortlist(ecse, wde, label)
    knockout_risk: dict[str, Any] | None = None
    try:
        knockout_risk = evaluate_fixture_knockout_risk(conn, fixture_id, settings=settings)
    except Exception:
        knockout_risk = None

    shadow_block: dict[str, Any] | None = None
    if include_shadow and (shadow_m6 or shadow_x3):
        shadow_block = {
            "m6": shadow_m6,
            "x3": {
                "status": (shadow_x3 or {}).get("x3_status"),
                "top1": (shadow_x3 or {}).get("x3_top1"),
                "m5_shadow_top1": (shadow_x3 or {}).get("m5_shadow_top1"),
                "rejection_reason": (shadow_x3 or {}).get("rejection_reason"),
            }
            if shadow_x3
            else None,
        }

    comp_key = str(fixture_row.get("competition_key") or (ecse_raw or {}).get("competition_key") or "")
    uefa_odds_readiness: dict[str, Any] | None = None
    if comp_key in UEFA_CUP_KEYS:
        uefa_odds_readiness = readiness_for_owner_report(fixture_id) or {
            "wde_prediction_available": bool(wde),
            "ecse_readiness_status": "ODDS_MISSING",
            "available_markets": [],
            "missing_odds_reason": "no_euro_c3_readiness_artifact",
            "next_recheck_priority": "MEDIUM",
        }
        if uefa_odds_readiness is not None:
            uefa_odds_readiness["wde_prediction_available"] = bool(wde)

    return {
        "fixture_id": fixture_id,
        "competition": fixture_row.get("competition_key") or (ecse_raw or {}).get("competition_key"),
        "competition_label": fixture_row.get("competition_label")
        or (fixture_row.get("competition_key") or "").replace("_", " ").title(),
        "kickoff_utc": kickoff_utc_fmt,
        "kickoff_local": kickoff_local_fmt,
        "home_team": fixture_row.get("home_team") or (ecse_raw or {}).get("home_team"),
        "away_team": fixture_row.get("away_team") or (ecse_raw or {}).get("away_team"),
        "status": status,
        "ecse": ecse,
        "wde": wde,
        "shadow": shadow_block,
        "owner_label": label,
        "owner_shortlist": shortlist,
        "knockout_draw_pen_risk": knockout_risk,
        "uefa_odds_readiness": uefa_odds_readiness,
    }


def _fmt_top_list(scores: list[Any] | None, limit: int = 3) -> str:
    if not scores:
        return "—"
    parts: list[str] = []
    for item in scores[:limit]:
        if isinstance(item, dict):
            score = item.get("scoreline") or item.get("label")
            prob = item.get("probability")
            if prob is not None:
                parts.append(f"{score} ({float(prob):.1%})")
            else:
                parts.append(str(score))
        else:
            parts.append(str(item))
    return ", ".join(parts)


def render_markdown(report: dict[str, Any]) -> str:
    meta = report["meta"]
    lines = [
        "# Owner Today Exact-Score Predictions",
        "",
        "> **Owner personal analysis only.** Not public. Not betting advice.",
        "",
        f"**Report date:** {meta['report_date']}",
        f"**Timezone:** {meta['timezone']}",
        f"**Generated (UTC):** {meta['generated_at_utc']}",
        f"**Fixtures selected:** {meta['fixtures_selected']} / {meta['limit_requested']} requested",
        "",
        "## Summary",
        "",
        "| # | Fixture | Kickoff (local) | ECSE Top-1 | ECSE Top-3 | WDE pick | O/U 2.5 | BTTS | Confidence | Owner label | Note |",
        "|---:|---|---|---|---|---|---|---|---:|---|---|",
    ]
    for idx, match in enumerate(report["matches"], start=1):
        ecse = match.get("ecse") or {}
        wde = match.get("wde") or {}
        shortlist = match.get("owner_shortlist") or {}
        fixture = f"{match.get('home_team')} vs {match.get('away_team')}"
        lines.append(
            "| {idx} | {fixture} | {kickoff} | {top1} | {top3} | {x2} | {ou} | {btts} | {conf} | {label} | {note} |".format(
                idx=idx,
                fixture=fixture,
                kickoff=match.get("kickoff_local") or "—",
                top1=ecse.get("top_1_score") or "—",
                top3=_fmt_top_list(ecse.get("top_3_scores"), 3),
                x2=wde.get("predicted_1x2") or "—",
                ou=wde.get("predicted_over_under_2_5") or "—",
                btts=wde.get("btts_pick") or "—",
                conf=f"{float(wde.get('confidence_score') or 0):.0f}" if wde else "—",
                label=match.get("owner_label") or "—",
                note=(shortlist.get("note") or "")[:80],
            )
        )

    if meta.get("warnings"):
        lines.extend(["", "## Warnings", ""])
        for warning in meta["warnings"]:
            lines.append(f"- {warning}")

    lines.extend(["", "## Match Details", ""])
    for idx, match in enumerate(report["matches"], start=1):
        lines.extend(
            [
                f"### {idx}. {match.get('home_team')} vs {match.get('away_team')}",
                "",
                f"- **fixture_id:** {match.get('fixture_id')}",
                f"- **competition:** {match.get('competition')}",
                f"- **kickoff UTC:** {match.get('kickoff_utc') or '—'}",
                f"- **kickoff local:** {match.get('kickoff_local') or '—'}",
                f"- **status:** {match.get('status')}",
                "",
            ]
        )
        ecse = match.get("ecse")
        if ecse:
            lines.extend(
                [
                    "#### ECSE exact score",
                    f"- Top-1: **{ecse.get('top_1_score')}**",
                    f"- Top-3: {_fmt_top_list(ecse.get('top_3_scores'), 3)}",
                    f"- Top-5: {_fmt_top_list(ecse.get('top_5_scores'), 5)}",
                    f"- λ home / away: {ecse.get('lambda_home')} / {ecse.get('lambda_away')}",
                    f"- source: `{ecse.get('source')}`",
                    "",
                ]
            )
        else:
            lines.extend(["#### ECSE exact score", "- *No ECSE snapshot stored*", ""])

        wde = match.get("wde")
        if wde:
            lines.extend(
                [
                    "#### WDE prediction",
                    f"- 1X2: **{wde.get('predicted_1x2')}**",
                    f"- O/U 2.5: **{wde.get('predicted_over_under_2_5')}**",
                    f"- BTTS: **{wde.get('btts_pick') or '—'}**",
                    f"- confidence: **{float(wde.get('confidence_score') or 0):.1f}**",
                    f"- no-bet: **{wde.get('no_bet_flag')}**",
                    f"- reason: {wde.get('short_reason')}",
                    f"- source: `{wde.get('source')}`",
                    "",
                ]
            )
        else:
            lines.extend(["#### WDE prediction", "- *No WDE output stored*", ""])

        uefa_rd = match.get("uefa_odds_readiness")
        if uefa_rd:
            markets = ", ".join(uefa_rd.get("available_markets") or []) or "—"
            lines.extend(
                [
                    "#### UEFA ECSE readiness (owner-only)",
                    f"- WDE prediction available: **{uefa_rd.get('wde_prediction_available')}**",
                    f"- ECSE readiness status: **{uefa_rd.get('ecse_readiness_status') or '—'}**",
                    f"- odds markets available: {markets}",
                    f"- missing odds reason: {uefa_rd.get('missing_odds_reason') or '—'}",
                    f"- next recheck priority: **{uefa_rd.get('next_recheck_priority') or '—'}**",
                    f"- best provider source: `{uefa_rd.get('best_provider_source') or '—'}`",
                    f"- odds freshness: {uefa_rd.get('odds_freshness') or '—'}",
                    "- *ECSE prediction shown only when ECSE snapshot exists*",
                    "",
                ]
            )

        shadow = match.get("shadow")
        if shadow:
            m6 = shadow.get("m6") or {}
            lines.extend(
                [
                    "#### Shadow / Owner Lab",
                    f"- baseline Top-1: {m6.get('baseline_top1') or '—'}",
                    f"- enhanced Top-1: {m6.get('enhanced_top1') or '—'}",
                    f"- rank movements: {json.dumps(m6.get('rank_movements') or {})}",
                    f"- applied: {m6.get('applied')}",
                    f"- exclusion: {m6.get('exclusion_reason') or '—'}",
                    "",
                ]
            )

        shortlist = match.get("owner_shortlist") or {}
        angle = shortlist.get("best_market_angle") or {}
        risk = match.get("knockout_draw_pen_risk") or {}
        if risk.get("knockout_draw_pen_risk"):
            lines.extend(
                [
                    "#### Knockout Draw/PEN risk (owner-only)",
                    f"- **risk level:** {risk.get('risk_level')}",
                    f"- **label:** {risk.get('draw_pen_risk_label') or 'Draw/PEN risk'}",
                    f"- **1-1 rank:** {risk.get('rank_1_1') if risk.get('rank_1_1') is not None else '—'}",
                    f"- **0-0 rank:** {risk.get('rank_0_0') if risk.get('rank_0_0') is not None else '—'}",
                    f"- **recommended cover:** {', '.join(risk.get('recommended_cover_scores') or []) or '—'}",
                    f"- **note:** {risk.get('owner_note')}",
                    "- *Owner-only research — not public prediction*",
                    "",
                ]
            )
        lines.extend(
            [
                "#### Owner shortlist",
                f"- main exact score: **{shortlist.get('main_exact_score') or '—'}**",
                f"- cover scores: {', '.join(shortlist.get('cover_scores') or []) or '—'}",
                f"- best market angle: 1X2={angle.get('1x2')}, O/U={angle.get('over_under_2_5')}, BTTS={angle.get('btts')}",
                f"- note: {shortlist.get('note')}",
                f"- **owner label:** `{match.get('owner_label')}`",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def generate_report(
    *,
    limit: int = 10,
    timezone_name: str = "Europe/Vienna",
    competition: str | None = None,
    competitions: list[str] | None = None,
    include_shadow: bool = True,
    upcoming_only: bool = False,
    target_date: str | None = None,
    days_ahead: int | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    tz = ZoneInfo(timezone_name)
    report_date = target_date or date.today().isoformat()
    if competitions and days_ahead is None:
        days_ahead = 30
    conn = connect(settings.sqlite_path)

    fixtures = discover_fixtures(
        conn,
        settings,
        target_date=report_date,
        competition=competition,
        competitions=competitions,
        upcoming_only=upcoming_only,
        limit=limit,
        days_ahead=days_ahead,
    )
    matches = [
        build_match_report(conn, settings, row, tz=tz, include_shadow=include_shadow) for row in fixtures
    ]

    warnings: list[str] = []
    if len(matches) < limit:
        warnings.append(
            f"Only {len(matches)} fixture(s) available for {report_date}; fewer than {limit} requested."
        )

    ecse_count = sum(1 for m in matches if m.get("ecse"))
    wde_count = sum(1 for m in matches if m.get("wde"))
    shadow_count = sum(1 for m in matches if (m.get("shadow") or {}).get("m6"))

    if ecse_count < len(matches):
        warnings.append(f"{len(matches) - ecse_count} fixture(s) missing ECSE snapshot data.")
    if wde_count < len(matches):
        warnings.append(f"{len(matches) - wde_count} fixture(s) missing WDE output.")

    return {
        "meta": {
            "report_date": report_date,
            "timezone": timezone_name,
            "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "limit_requested": limit,
            "fixtures_found": len(fixtures),
            "fixtures_selected": len(matches),
            "with_ecse": ecse_count,
            "with_wde": wde_count,
            "with_shadow_enhanced": shadow_count,
            "competition_filter": competition,
            "competitions_filter": competitions,
            "days_ahead": days_ahead,
            "upcoming_only": upcoming_only,
            "include_shadow": include_shadow,
            "owner_only": True,
            "public_output_changed": False,
            "warnings": warnings,
        },
        "matches": matches,
    }


def write_reports(report: dict[str, Any]) -> tuple[Path, Path]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "today_10_exact_score_predictions.json"
    md_path = REPORT_DIR / "today_10_exact_score_predictions.md"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    return json_path, md_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Owner-only today exact-score prediction report")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--timezone", default="Europe/Vienna")
    parser.add_argument("--competition", default=None, help="Single competition key e.g. world_cup_2026")
    parser.add_argument(
        "--competitions",
        nargs="+",
        default=None,
        help="Multiple competition keys (e.g. champions_league europa_league)",
    )
    parser.add_argument("--days-ahead", type=int, default=None, help="Upcoming window when using --competitions")
    parser.add_argument("--include-shadow", action="store_true", default=True)
    parser.add_argument("--no-shadow", dest="include_shadow", action="store_false")
    parser.add_argument("--upcoming-only", action="store_true", default=False)
    parser.add_argument("--date", default=None, help="YYYY-MM-DD override (default: today)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = generate_report(
        limit=args.limit,
        timezone_name=args.timezone,
        competition=args.competition,
        competitions=args.competitions,
        include_shadow=args.include_shadow,
        upcoming_only=args.upcoming_only,
        target_date=args.date,
        days_ahead=args.days_ahead,
    )
    json_path, md_path = write_reports(report)
    meta = report["meta"]
    print(f"fixtures found: {meta['fixtures_found']}")
    print(f"with ECSE: {meta['with_ecse']}")
    print(f"with WDE: {meta['with_wde']}")
    print(f"with shadow enhanced: {meta['with_shadow_enhanced']}")
    print(f"markdown: {md_path}")
    print(f"json: {json_path}")
    for warning in meta.get("warnings") or []:
        print(f"WARNING: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
