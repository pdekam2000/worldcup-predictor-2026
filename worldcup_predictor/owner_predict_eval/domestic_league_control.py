"""Domestic league control batch — nearest-date discovery, freeze, A/B evaluation."""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.competitions import CompetitionConfig
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.goal_timing.prediction_service import GoalTimingPredictionService
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.owner.euro_c_odds_import import (
    _latest_odds_snapshot,
    assess_ecse_readiness,
    is_fake_odds_payload,
    normalize_uefa_odds_snapshot,
)
from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
from worldcup_predictor.owner_daily.odds_import import import_odds_for_single_fixture, scan_fixture_odds_readiness
from worldcup_predictor.owner_daily.predictions import run_daily_predictions
from worldcup_predictor.owner_daily.report import _load_ecse, _load_wde, _owner_label
from worldcup_predictor.owner_predict_eval.constants import ARTIFACTS_DIR, REPORTS_DIR
from worldcup_predictor.owner_predict_eval.dates import date_tag
from worldcup_predictor.owner_predict_eval.tomorrow_league_batch import (
    SELECT_COUNT,
    TZ,
    _consistency,
    _ecse_top_list,
    _first_goal_block,
    _kickoff_vienna,
    _parse_wde_full,
    _reliability_tier,
    _utc_now,
    ensure_batch_tables,
    freeze_batch_snapshot,
    load_frozen_snapshot,
)
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.research.ecse_live.prediction_builder import build_ecse_live_prediction
from worldcup_predictor.research.ecse_live.store import ensure_ecse_live_tables, get_snapshot, has_snapshot

PHASE = "DOMESTIC-LEAGUE-CONTROL-BATCH"
BATCH_PREFIX = "domestic_league_control"
UEFA_REFERENCE_BATCH = "tomorrow_4_league_20260707"
SCAN_START = date(2026, 7, 8)
SCAN_DAYS = 30
PREFERRED_BOOKMAKERS = 5
NOT_STARTED = {"NS", "TBD", "SCHEDULED", "TIMED"}

# Leagues with verified production support in this repository.
PROVEN_DOMESTIC_LEAGUE_IDS: dict[int, str] = {
    113: "allsvenskan",
    114: "superettan",
    362: "a_lyga",
    365: "virsliga",
    164: "urvalsdeild",
}

PROVEN_DOMESTIC_LEAGUES: dict[str, dict[str, Any]] = {
    "allsvenskan": {"name": "Allsvenskan", "league_id": 113, "country": "Sweden", "season": 2026},
    "superettan": {"name": "Superettan", "league_id": 114, "country": "Sweden", "season": 2026},
    "a_lyga": {"name": "A Lyga", "league_id": 362, "country": "Lithuania", "season": 2026},
    "virsliga": {"name": "Virsliga", "league_id": 365, "country": "Latvia", "season": 2026},
    "urvalsdeild": {"name": "Úrvalsdeild", "league_id": 164, "country": "Iceland", "season": 2026},
}


def batch_id_for(target: date) -> str:
    return f"{BATCH_PREFIX}_{date_tag(target)}"


def artifact_dir_for(target: date) -> Path:
    return ARTIFACTS_DIR / f"domestic_league_control_{date_tag(target)}"


def prediction_report_path(target: date) -> Path:
    return REPORTS_DIR / f"DOMESTIC_LEAGUE_CONTROL_PREDICTIONS_{target.isoformat()}.md"


def evaluation_report_path(target: date) -> Path:
    return REPORTS_DIR / f"DOMESTIC_LEAGUE_CONTROL_EVALUATION_{target.isoformat()}.md"


def comparison_report_path(target: date) -> Path:
    return REPORTS_DIR / f"DOMESTIC_VS_INTERNATIONAL_CLUB_COMPARISON_{target.isoformat()}.md"


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


def _candidate_from_api_item(item: dict[str, Any]) -> dict[str, Any] | None:
    league = item.get("league") or {}
    league_id = int(league.get("id") or 0)
    comp_key = PROVEN_DOMESTIC_LEAGUE_IDS.get(league_id)
    if not comp_key:
        return None
    meta = PROVEN_DOMESTIC_LEAGUES[comp_key]
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
        "competition_name": meta["name"],
        "competition_type": "domestic_league",
        "country": meta["country"],
        "home_team": str((teams.get("home") or {}).get("name") or ""),
        "away_team": str((teams.get("away") or {}).get("name") or ""),
        "kickoff_utc": str(fx.get("date") or ""),
        "status": status,
        "league_id": league_id,
        "season": int(league.get("season") or meta["season"]),
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
    bm = int(norm.bookmaker_count if norm else readiness.get("bookmaker_count") or 0)
    db_row = conn.execute("SELECT 1 FROM fixtures WHERE fixture_id=? LIMIT 1", (fid,)).fetchone()
    wde_row = conn.execute(
        "SELECT 1 FROM worldcup_stored_predictions WHERE fixture_id=? LIMIT 1", (fid,)
    ).fetchone()

    score = 0
    reasons: list[str] = ["domestic_league", f"proven_league:{cand['competition_key']}"]
    if db_row:
        score += 15
        reasons.append("db_fixture_coverage")
    if wde_row:
        score += 5
        reasons.append("historical_wde_path")
    if readiness.get("has_1x2"):
        score += 20
        reasons.append("prematch_1x2")
    if bm >= PREFERRED_BOOKMAKERS:
        score += 25
        reasons.append(f"bookmakers>={PREFERRED_BOOKMAKERS}")
    elif bm >= 2:
        score += 10
        reasons.append("thin_bookmaker_coverage")
    if readiness.get("odds_freshness") == "fresh":
        score += 10
    elif readiness.get("odds_freshness") == "stale":
        score -= 10
        reasons.append("stale_odds_penalty")
    if ecse_ready.get("ecse_ready"):
        score += 20
        reasons.append("ecse_ready_prematch")
    if readiness.get("has_ou25"):
        score += 5
    if readiness.get("has_btts"):
        score += 5

    quality_flags: list[str] = []
    if bm < PREFERRED_BOOKMAKERS:
        quality_flags.append("below_preferred_bookmaker_threshold")
    if not ecse_ready.get("ecse_ready"):
        quality_flags.append("ecse_not_ready_prematch")

    return {
        **cand,
        "selection_score": score,
        "selection_reasons": reasons,
        "bookmaker_count_prematch": bm,
        "odds_freshness_prematch": readiness.get("odds_freshness"),
        "ecse_ready_prematch": ecse_ready.get("ecse_ready"),
        "quality_flags": quality_flags,
        "odds_readiness": readiness,
        "ecse_readiness": ecse_ready,
    }


def scan_domestic_dates(
    *,
    start: date = SCAN_START,
    days: int = SCAN_DAYS,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    settings = settings or get_settings()
    client = ApiFootballClient(settings) if settings.api_football_configured else None
    conn = connect(settings.sqlite_path)
    scan_rows: list[dict[str, Any]] = []

    for offset in range(days):
        target = start + timedelta(days=offset)
        proven: list[dict[str, Any]] = []
        if client:
            for item in _fetch_api_fixtures_for_date(client, target):
                cand = _candidate_from_api_item(item)
                if cand:
                    proven.append(_score_candidate(conn, cand, settings))
        scan_rows.append(
            {
                "date": target.isoformat(),
                "proven_domestic_count": len(proven),
                "candidates": proven,
            }
        )
    conn.close()
    return scan_rows


def find_nearest_eligible_date(scan_rows: list[dict[str, Any]], *, min_count: int = SELECT_COUNT) -> date | None:
    for row in scan_rows:
        if int(row.get("proven_domestic_count") or 0) >= min_count:
            return date.fromisoformat(str(row["date"]))
    return None


def discover_domestic_control_fixtures(
    *,
    target_date: date | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    scan_rows = scan_domestic_dates(settings=settings)
    chosen = target_date or find_nearest_eligible_date(scan_rows)
    if not chosen:
        return {
            "status": "DOMESTIC_LEAGUE_CONTROL_BATCH_BLOCKED",
            "reason": "no_date_with_4_proven_domestic_fixtures",
            "scan": scan_rows,
        }

    day_row = next((r for r in scan_rows if r["date"] == chosen.isoformat()), None)
    candidates = list((day_row or {}).get("candidates") or [])
    candidates.sort(key=lambda x: (-x["selection_score"], x["kickoff_utc"], x["fixture_id"]))

    audit = [
        {
            "fixture_id": c["fixture_id"],
            "match": f"{c['home_team']} vs {c['away_team']}",
            "league": c["competition_name"],
            "score": c["selection_score"],
            "bookmakers_prematch": c.get("bookmaker_count_prematch"),
            "ecse_ready_prematch": c.get("ecse_ready_prematch"),
            "quality_flags": c.get("quality_flags"),
            "selected": False,
        }
        for c in candidates
    ]
    preselected = candidates[: max(SELECT_COUNT * 3, 12)]

    return {
        "status": "discovered",
        "target_date": chosen.isoformat(),
        "batch_id": batch_id_for(chosen),
        "scan_summary": [
            {
                "date": r["date"],
                "proven_domestic_count": r["proven_domestic_count"],
                "eligible_after_quality": r["proven_domestic_count"],
            }
            for r in scan_rows
        ],
        "chosen_reason": (
            f"earliest date on/after {SCAN_START.isoformat()} with >={SELECT_COUNT} "
            f"proven domestic-league fixtures ({len(candidates)} found)"
        ),
        "candidates": candidates,
        "preselected": preselected,
        "selection_audit": audit,
    }


def _upsert_fixtures(repo: FootballIntelligenceRepository, selected: list[dict[str, Any]]) -> list[DailyFixture]:
    fixtures: list[DailyFixture] = []
    for d in selected:
        comp_key = d["competition_key"]
        meta = PROVEN_DOMESTIC_LEAGUES[comp_key]
        repo.upsert_competition(
            CompetitionConfig(
                key=comp_key,
                name=meta["name"],
                league_id=int(meta["league_id"]),
                season=int(d.get("season") or meta["season"]),
                country=str(meta["country"]),
                compensation_type="league",
                supports_table=True,
            )
        )
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


def _try_select_after_refresh(
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    cand: dict[str, Any],
    *,
    settings: Settings,
    target_date: str,
    dry_run: bool,
    sm: SportmonksProvider,
    oa: OddAlertsClient,
) -> dict[str, Any] | None:
    fid = int(cand["fixture_id"])
    _upsert_fixtures(repo, [cand])
    fx = DailyFixture(
        fixture_id=fid,
        provider_fixture_id=fid,
        competition_key=cand["competition_key"],
        home_team=cand["home_team"],
        away_team=cand["away_team"],
        kickoff_utc=cand["kickoff_utc"],
        status=cand.get("status") or "NS",
        season=cand.get("season"),
        coverage_sources=["api_football"],
        provider_ids={"api_football": fid},
    )
    if not dry_run:
        import_odds_for_single_fixture(fx, settings=settings, force=True, dry_run=False)
    after = scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)
    snap = _latest_odds_snapshot(conn, fid)
    payload = None
    if snap and snap.get("payload_json"):
        try:
            payload = json.loads(snap["payload_json"])
        except json.JSONDecodeError:
            pass
    norm = (
        normalize_uefa_odds_snapshot(payload, fixture_id=fid)
        if payload and not is_fake_odds_payload(payload)
        else None
    )
    bm = int(norm.bookmaker_count if norm else after.get("bookmaker_count") or 0)
    if not after.get("has_1x2"):
        return None
    if after.get("odds_freshness") == "stale":
        return None
    fx_row = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
    ecse_pred = build_ecse_live_prediction(conn, fid, fx_row)
    if not ecse_pred:
        return None
    cand = dict(cand)
    cand["post_refresh"] = {
        "bookmaker_count": bm,
        "odds_freshness": after.get("odds_freshness"),
        "odds_source": after.get("odds_source"),
        "odds_timestamp": after.get("odds_snapshot_time"),
        "ecse_ready": True,
        "below_preferred_bookmakers": bm < PREFERRED_BOOKMAKERS,
        "quality_downgrade": bm < PREFERRED_BOOKMAKERS,
    }
    return cand


def run_domestic_control_batch(
    *,
    target_date: date | None = None,
    dry_run: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any]:
    settings = settings or get_settings()
    discovery = discover_domestic_control_fixtures(target_date=target_date, settings=settings)
    if discovery.get("status") != "discovered":
        return discovery

    batch_id = discovery["batch_id"]
    target = date.fromisoformat(discovery["target_date"])
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    conn = connect(settings.sqlite_path)
    ensure_ecse_live_tables(conn)
    ensure_batch_tables(conn)
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()
    fg_service = GoalTimingPredictionService(settings)

    final_selected: list[dict[str, Any]] = []
    tried: set[int] = set()
    for cand in discovery["preselected"]:
        if len(final_selected) >= SELECT_COUNT:
            break
        fid = int(cand["fixture_id"])
        if fid in tried:
            continue
        tried.add(fid)
        picked = _try_select_after_refresh(
            conn, repo, cand, settings=settings, target_date=discovery["target_date"], dry_run=dry_run, sm=sm, oa=oa
        )
        if picked:
            final_selected.append(picked)

    if len(final_selected) < SELECT_COUNT:
        for cand in discovery["candidates"]:
            if len(final_selected) >= SELECT_COUNT:
                break
            fid = int(cand["fixture_id"])
            if fid in tried:
                continue
            tried.add(fid)
            picked = _try_select_after_refresh(
                conn, repo, cand, settings=settings, target_date=discovery["target_date"], dry_run=dry_run, sm=sm, oa=oa
            )
            if picked:
                final_selected.append(picked)

    if len(final_selected) < SELECT_COUNT:
        conn.close()
        repo.close()
        return {
            "status": "DOMESTIC_LEAGUE_CONTROL_BATCH_BLOCKED",
            "reason": f"only_{len(final_selected)}_fixtures_passed_post_refresh_gates",
            "discovery": discovery,
            "post_refresh_selected": final_selected,
        }

    fixtures = _upsert_fixtures(repo, final_selected[:SELECT_COUNT])
    match_reports: list[dict[str, Any]] = []
    freeze_results: list[dict[str, Any]] = []
    quality_notes: list[str] = []

    for fx in fixtures:
        fid = fx.provider_fixture_id
        cand = next(c for c in final_selected if int(c["fixture_id"]) == fid)
        pr = cand.get("post_refresh") or {}
        if pr.get("below_preferred_bookmakers"):
            quality_notes.append(
                f"fixture {fid}: bookmaker_count={pr.get('bookmaker_count')} < preferred {PREFERRED_BOOKMAKERS}"
            )

        if not dry_run:
            run_daily_predictions([fx], mode="wde_and_ecse", dry_run=False, force=False, settings=settings)

        fx_row = dict(conn.execute("SELECT * FROM fixtures WHERE fixture_id=?", (fid,)).fetchone() or {})
        ecse_pred = build_ecse_live_prediction(conn, fid, fx_row)
        wde = _parse_wde_full(conn, fid, fx.competition_key, settings)
        ecse_db = _load_ecse(conn, fid)
        consistency = _consistency(wde, ecse_pred)
        first_goal = _first_goal_block(fg_service, fid, fx.competition_key, persist=not dry_run)
        top10 = _ecse_top_list(ecse_pred, 10)
        top1_prob = (top10[0]["probability"] / 100.0) if top10 else 0.0
        data_score = sum(
            [
                bool(pr.get("bookmaker_count")),
                bool(wde.get("predicted_1x2")),
                bool(ecse_pred),
                bool(pr.get("odds_freshness") == "fresh"),
            ]
        )
        tier = _reliability_tier(
            float(wde.get("confidence_score") or 0), top1_prob, consistency["status"], data_score
        )
        meta = PROVEN_DOMESTIC_LEAGUES[fx.competition_key]

        report = {
            "fixture": {
                "fixture_id": fid,
                "competition_key": fx.competition_key,
                "competition_name": meta["name"],
                "competition_type": "domestic_league",
                "country": meta["country"],
                "home_team": fx.home_team,
                "away_team": fx.away_team,
                "kickoff_utc": fx.kickoff_utc,
                "kickoff_vienna": _kickoff_vienna(fx.kickoff_utc),
                "status": fx.status,
            },
            "data_readiness": pr,
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
            },
            "first_goal": first_goal,
            "consistency": consistency,
            "owner_label": _owner_label(wde, ecse_db),
            "reliability": {
                "tier": tier,
                "wde_confidence": wde.get("confidence_score"),
                "ecse_top1_concentration": top1_prob,
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
        "experiment_id": batch_id,
        "competition_type_segment": "domestic_league",
        "generated_at_utc": _utc_now(),
        "target_date": discovery["target_date"],
        "batch_id": batch_id,
        "discovery": discovery,
        "quality_notes": quality_notes,
        "matches": match_reports,
        "strongest_3_picks": ranked[:3],
        "freeze_results": freeze_results,
        "status": "DOMESTIC_LEAGUE_CONTROL_BATCH_READY"
        if len(match_reports) == SELECT_COUNT and not dry_run
        else ("DRY_RUN" if dry_run else "DOMESTIC_LEAGUE_CONTROL_BATCH_BLOCKED"),
    }

    out_dir = artifact_dir_for(target)
    out_dir.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (out_dir / "payload.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "date_scan.json").write_text(
        json.dumps(discovery.get("scan_summary") or [], indent=2), encoding="utf-8"
    )
    prediction_report_path(target).write_text(_render_prediction_md(payload), encoding="utf-8")
    payload["payload_path"] = str(out_dir / "payload.json")
    payload["prediction_report_path"] = str(prediction_report_path(target))
    conn.close()
    repo.close()
    return payload


def _render_prediction_md(payload: dict[str, Any]) -> str:
    disc = payload.get("discovery") or {}
    lines = [
        "# Domestic League Control Batch Predictions",
        "",
        f"Experiment: `{payload.get('batch_id')}` | Segment: **domestic_league**",
        f"Date: **{payload.get('target_date')}** | Generated: {payload.get('generated_at_utc')}",
        "",
        "## Nearest eligible date",
        "",
        f"- Chosen: **{disc.get('target_date')}**",
        f"- Reason: {disc.get('chosen_reason')}",
        "",
        "### Date scan (proven domestic leagues)",
        "",
        "| Date | Proven domestic fixtures |",
        "|------|--------------------------|",
    ]
    for row in disc.get("scan_summary") or []:
        if row.get("proven_domestic_count"):
            lines.append(f"| {row['date']} | {row['proven_domestic_count']} |")
    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Match | League | WDE 1X2 | BTTS | O/U | ECSE Top1 | Top2 | Top3 | Confidence | Flag |",
            "|-------|--------|---------|------|-----|-----------|------|------|------------|------|",
        ]
    )
    for m in payload.get("matches") or []:
        fx = m["fixture"]
        w = m["wde"]
        e = m["ecse"]
        btts = (w.get("btts") or {}).get("selection") or w.get("btts_pick")
        ou = (w.get("over_under") or {}).get("selection") or w.get("predicted_over_under_2_5")
        lines.append(
            f"| {fx['home_team']} vs {fx['away_team']} | {fx['competition_name']} | {w.get('predicted_1x2')} | "
            f"{btts} | {ou} | {(e.get('top1') or {}).get('scoreline', '—')} | "
            f"{(e.get('top2') or {}).get('scoreline', '—')} | {(e.get('top3') or {}).get('scoreline', '—')} | "
            f"{m['reliability']['tier']} | {m['consistency']['status']} |"
        )
    if payload.get("quality_notes"):
        lines.extend(["", "## Quality downgrades", ""])
        for note in payload["quality_notes"]:
            lines.append(f"- {note}")
    lines.extend(["", "## Strongest 3 picks", ""])
    for m in payload.get("strongest_3_picks") or []:
        fx = m["fixture"]
        lines.append(f"### Rank {m['reliability']['confidence_rank']}: {fx['home_team']} vs {fx['away_team']}")
        lines.append(f"- WDE `{m['wde'].get('predicted_1x2')}` | ECSE Top1 `{(m['ecse'].get('top1') or {}).get('scoreline')}`")
        lines.append(f"- {m['reliability']['tier']} | {m['consistency']['status']}")
        lines.append("")
    return "\n".join(lines)


def _metrics_from_frozen_snapshots(snapshots: list[dict[str, Any]], evaluations: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    eval_by_fid = {int(e["fixture_id"]): e for e in (evaluations or []) if e.get("fixture_id")}
    confs: list[float] = []
    top1_probs: list[float] = []
    flags: dict[str, int] = {}
    no_bet = 0
    for snap in snapshots:
        wde = snap.get("wde") or {}
        ecse = snap.get("ecse") or {}
        if wde.get("no_bet"):
            no_bet += 1
        if wde.get("confidence_score") is not None:
            confs.append(float(wde["confidence_score"]))
        t1 = ecse.get("top1") or {}
        if t1.get("probability") is not None:
            top1_probs.append(float(t1["probability"]) / (100.0 if float(t1["probability"]) > 1 else 1))
        flag = (snap.get("consistency_flag") or snap.get("consistency") or {}).get("status") if isinstance(snap.get("consistency"), dict) else snap.get("consistency_flag")
        if isinstance(snap.get("consistency"), dict):
            flag = snap["consistency"].get("status")
        flags[str(flag or "unknown")] = flags.get(str(flag or "unknown"), 0) + 1

    def acc(field: str) -> tuple[int, int, float | None]:
        hits = []
        for ev in eval_by_fid.values():
            if ev.get("evaluation_status") != "EVALUATED":
                continue
            block = ev.get(field) or {}
            if block.get("hit") is not None:
                hits.append(bool(block["hit"]))
        if not hits:
            return 0, 0, None
        return sum(hits), len(hits), round(sum(hits) / len(hits), 4)

    wde_h, wde_n, wde_a = acc("wde_1x2")
    btts_h, btts_n, btts_a = acc("btts")
    ou_h, ou_n, ou_a = acc("over_under")
    t1_h, t1_n, t1_a = acc("ecse_top1")
    t3_h, t3_n, t3_a = acc("ecse_top3")
    t5_h, t5_n, t5_a = acc("ecse_top5")

    return {
        "fixture_count": len(snapshots),
        "evaluated_count": sum(1 for e in eval_by_fid.values() if e.get("evaluation_status") == "EVALUATED"),
        "wde_1x2_accuracy": wde_a,
        "btts_accuracy": btts_a,
        "over_under_accuracy": ou_a,
        "ecse_top1_hit_rate": t1_a,
        "ecse_top3_hit_rate": t3_a,
        "ecse_top5_hit_rate": t5_a,
        "average_confidence": round(sum(confs) / len(confs), 2) if confs else None,
        "average_ecse_top1_probability": round(sum(top1_probs) / len(top1_probs), 4) if top1_probs else None,
        "consistency_flag_distribution": flags,
        "no_bet_rate": round(no_bet / len(snapshots), 4) if snapshots else None,
        "raw_accuracy_counts": {
            "wde_1x2": {"correct": wde_h, "evaluated": wde_n},
            "btts": {"correct": btts_h, "evaluated": btts_n},
            "over_under": {"correct": ou_h, "evaluated": ou_n},
            "ecse_top1": {"correct": t1_h, "evaluated": t1_n},
            "ecse_top3": {"correct": t3_h, "evaluated": t3_n},
            "ecse_top5": {"correct": t5_h, "evaluated": t5_n},
        },
    }


def load_batch_snapshots(conn: sqlite3.Connection, batch_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT fixture_id, snapshot_json, competition_type FROM owner_league_batch_snapshots WHERE batch_id=? AND is_frozen=1",
        (batch_id,),
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        raw = row[1] if not isinstance(row, sqlite3.Row) else row["snapshot_json"]
        try:
            snap = json.loads(raw)
        except json.JSONDecodeError:
            continue
        snap["fixture_id"] = int(row[0] if not isinstance(row, sqlite3.Row) else row["fixture_id"])
        snap["competition_type"] = row[2] if not isinstance(row, sqlite3.Row) else row["competition_type"]
        out.append(snap)
    return out


def evaluate_experiment_comparison(
    *,
    domestic_date: date | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Evaluate Group A (UEFA batch) vs Group B (domestic control) separately."""
    from worldcup_predictor.owner_predict_eval.tomorrow_league_batch import evaluate_batch

    settings = settings or get_settings()
    discovery = discover_domestic_control_fixtures(settings=settings)
    target = domestic_date or (
        date.fromisoformat(discovery["target_date"]) if discovery.get("target_date") else None
    )
    if not target:
        return {"status": "blocked", "reason": "no_domestic_batch_date"}

    domestic_batch = batch_id_for(target)
    conn = connect(settings.sqlite_path)
    domestic_eval = _evaluate_batch_snapshots(conn, domestic_batch)
    uefa_eval = evaluate_batch(date_arg="2026-07-07", settings=settings)

    domestic_snaps = load_batch_snapshots(conn, domestic_batch)
    uefa_snaps = load_batch_snapshots(conn, UEFA_REFERENCE_BATCH)

    group_a = {
        "label": "international_club_knockout",
        "batch_id": UEFA_REFERENCE_BATCH,
        "metrics": _metrics_from_frozen_snapshots(uefa_snaps, uefa_eval.get("fixtures")),
        "fixtures": uefa_eval.get("fixtures") or [],
    }
    group_b = {
        "label": "domestic_league",
        "batch_id": domestic_batch,
        "metrics": _metrics_from_frozen_snapshots(domestic_snaps, domestic_eval.get("fixtures")),
        "fixtures": domestic_eval.get("fixtures") or [],
    }

    comparison = {
        "phase": PHASE,
        "exploratory_warning": "4 vs 4 fixtures — not statistically significant; exploratory only",
        "group_a_international_club_knockout": group_a,
        "group_b_domestic_league": group_b,
        "domestic_eval": domestic_eval,
        "uefa_eval": uefa_eval,
    }

    out_dir = artifact_dir_for(target)
    out_dir.mkdir(parents=True, exist_ok=True)
    comparison_path = out_dir / "experiment_comparison.json"
    comparison_path.write_text(json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8")
    comparison_report_path(target).write_text(_render_comparison_md(comparison), encoding="utf-8")
    evaluation_report_path(target).write_text(_render_domestic_eval_md(domestic_eval), encoding="utf-8")
    comparison["comparison_report_path"] = str(comparison_report_path(target))
    comparison["comparison_json_path"] = str(comparison_path)
    conn.close()
    return comparison


def _evaluate_batch_snapshots(conn: sqlite3.Connection, batch_id: str) -> dict[str, Any]:
    from worldcup_predictor.owner_predict_eval.tomorrow_league_batch import (
        _eval_symbol,
        _is_finished,
        _minute_in_bucket,
        _names_match,
        _scorelines_from_rows,
        _utc_now,
        load_fixture_result,
    )
    from worldcup_predictor.accuracy.evaluator import actual_1x2, actual_over_under

    rows = conn.execute(
        "SELECT fixture_id, snapshot_json, competition_type FROM owner_league_batch_snapshots WHERE batch_id=? AND is_frozen=1",
        (batch_id,),
    ).fetchall()
    if not rows:
        return {"status": "no_frozen_snapshots", "batch_id": batch_id}

    evaluations: list[dict[str, Any]] = []
    metrics = {
        "wde_1x2": {"correct": 0, "evaluated": 0},
        "btts": {"correct": 0, "evaluated": 0},
        "over_under": {"correct": 0, "evaluated": 0},
        "ecse_top1": {"correct": 0, "evaluated": 0},
        "ecse_top3": {"correct": 0, "evaluated": 0},
        "ecse_top5": {"correct": 0, "evaluated": 0},
    }

    for row in rows:
        snap = json.loads(row[1] if not isinstance(row, sqlite3.Row) else row["snapshot_json"])
        fid = int(row[0] if not isinstance(row, sqlite3.Row) else row["fixture_id"])
        fx_row = conn.execute("SELECT status FROM fixtures WHERE fixture_id=?", (fid,)).fetchone()
        status = str(fx_row[0] if fx_row else "NS").upper()
        result = load_fixture_result(conn, fid)
        ev: dict[str, Any] = {
            "fixture_id": fid,
            "match": f"{snap.get('home_team')} vs {snap.get('away_team')}",
            "competition_type": snap.get("competition_type"),
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
        pred_x2 = wde.get("predicted_1x2")
        pred_ou = wde.get("predicted_over_under_2_5") or (wde.get("over_under") or {}).get("selection")
        btts_pred = wde.get("btts_pick") or (wde.get("btts") or {}).get("selection")
        top1 = str((ecse.get("top1") or {}).get("scoreline") or "")
        top3 = _scorelines_from_rows(ecse.get("top3_list") or ecse.get("top3") or [])
        top5 = _scorelines_from_rows(ecse.get("top5") or [])
        wde_hit = pred_x2 == actual_1x2(hg, ag) if pred_x2 else None
        btts_hit = btts_pred == ("yes" if hg > 0 and ag > 0 else "no") if btts_pred else None
        ou_hit = pred_ou == actual_over_under(hg, ag) if pred_ou else None
        top1_hit = top1 == actual_score if top1 else None
        top3_hit = actual_score in top3 if top3 else None
        top5_hit = actual_score in top5 if top5 else None
        ev.update(
            {
                "evaluation_status": "EVALUATED",
                "actual_score": actual_score,
                "wde_1x2": {"predicted": pred_x2, "hit": wde_hit},
                "btts": {"predicted": btts_pred, "hit": btts_hit},
                "over_under": {"predicted": pred_ou, "hit": ou_hit},
                "ecse_top1": {"predicted": top1, "hit": top1_hit},
                "ecse_top3": {"hit": top3_hit},
                "ecse_top5": {"hit": top5_hit},
            }
        )
        for key, hit in (
            ("wde_1x2", wde_hit),
            ("btts", btts_hit),
            ("over_under", ou_hit),
            ("ecse_top1", top1_hit),
            ("ecse_top3", top3_hit),
            ("ecse_top5", top5_hit),
        ):
            if hit is not None:
                metrics[key]["evaluated"] += 1
                if hit:
                    metrics[key]["correct"] += 1
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
            (batch_id, fid, snap.get("competition_type"), json.dumps(ev, default=str), _utc_now()),
        )
    conn.commit()
    return {
        "batch_id": batch_id,
        "evaluated_count": sum(1 for e in evaluations if e.get("evaluation_status") == "EVALUATED"),
        "waiting_count": sum(1 for e in evaluations if e.get("evaluation_status") != "EVALUATED"),
        "metrics": {
            k: {**v, "accuracy": round(v["correct"] / v["evaluated"], 4) if v["evaluated"] else None}
            for k, v in metrics.items()
        },
        "fixtures": evaluations,
    }


def _render_comparison_md(comp: dict[str, Any]) -> str:
    a = comp["group_a_international_club_knockout"]["metrics"]
    b = comp["group_b_domestic_league"]["metrics"]
    lines = [
        "# Domestic vs International Club — Exploratory Comparison",
        "",
        f"> {comp.get('exploratory_warning')}",
        "",
        "| Metric | Group A (international_club_knockout) | Group B (domestic_league) |",
        "|--------|--------------------------------------|---------------------------|",
    ]
    for key in (
        "wde_1x2_accuracy",
        "btts_accuracy",
        "over_under_accuracy",
        "ecse_top1_hit_rate",
        "ecse_top3_hit_rate",
        "ecse_top5_hit_rate",
        "average_confidence",
        "average_ecse_top1_probability",
        "no_bet_rate",
    ):
        lines.append(f"| {key} | {a.get(key)} | {b.get(key)} |")
    lines.extend(["", "## Consistency flag distribution", "", "### Group A", "", json.dumps(a.get("consistency_flag_distribution"), indent=2)])
    lines.extend(["", "### Group B", "", json.dumps(b.get("consistency_flag_distribution"), indent=2)])
    return "\n".join(lines)


def _render_domestic_eval_md(ev: dict[str, Any]) -> str:
    lines = [
        "# Domestic League Control Evaluation",
        "",
        f"Batch: `{ev.get('batch_id')}` | Evaluated: {ev.get('evaluated_count')} / waiting {ev.get('waiting_count')}",
        "",
        "| Metric | Correct | Evaluated | Accuracy |",
        "|--------|---------|-----------|----------|",
    ]
    for name, m in (ev.get("metrics") or {}).items():
        acc = f"{100 * m['accuracy']:.1f}%" if m.get("accuracy") is not None else "—"
        lines.append(f"| {name} | {m.get('correct', 0)} | {m.get('evaluated', 0)} | {acc} |")
    return "\n".join(lines)
