#!/usr/bin/env python3
"""Build owner WC today report (world_cup_2026, Europe/Vienna). Internal only."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import get_db_path
from worldcup_predictor.data_import.oddalerts_enrichment_csv_importer import load_fixture_enrichment
from worldcup_predictor.owner_daily.constants import (
    OWNER_LABEL_DATA_MISSING,
    OWNER_LABEL_MEDIUM,
    OWNER_LABEL_NO_BET,
    OWNER_LABEL_STRONG,
    OWNER_LABEL_WEAK,
    REPORTS_DIR,
)
from worldcup_predictor.owner_daily.fixture_discovery import (
    DailyFixture,
    discover_fixtures_from_db,
    resolve_target_date,
    vienna_day_utc_bounds,
)
from worldcup_predictor.owner_daily.odds_import import scan_fixture_odds_readiness
from worldcup_predictor.owner_daily.report import (
    _format_kickoff_local,
    _owner_label,
    _shadow_enhanced_top1,
    _top_scores_text,
)
from worldcup_predictor.research.ecse_live.store import get_snapshot
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
from worldcup_predictor.research.ecse_live.smoke_targets import WIN2DAY_SMOKE_TARGETS
from worldcup_predictor.research.ecse_x3_b.store import get_owner_shadow_for_fixture

EXPECTED_TODAY = (
    ("Ivory Coast", "Norway"),
    ("France", "Sweden"),
    ("Mexico", "Ecuador"),
)


def _load_ecse_row(conn, fixture_id: int) -> dict[str, Any] | None:
    snap = get_snapshot(conn, int(fixture_id))
    if not snap:
        return None
    top5 = snap.get("top_5_scores") or []
    top3 = snap.get("top_3_scores") or []
    return {
        "top_1_score": snap.get("top_1_score"),
        "top_3_scores": top3,
        "top_5_scores": top5,
        "top_10_scorelines": snap.get("top_10_scorelines") or top5,
        "confidence_score": float(snap.get("confidence_score") or 0),
        "lambda_home": snap.get("lambda_home"),
        "lambda_away": snap.get("lambda_away"),
        "prediction_source": snap.get("prediction_source"),
    }


def _load_wde_readonly(conn, fixture_id: int, competition_key: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT payload_json, source FROM worldcup_stored_predictions WHERE fixture_id = ? LIMIT 1",
        (int(fixture_id),),
    ).fetchone()
    if not row or not row["payload_json"]:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except json.JSONDecodeError:
        return None
    one_x_two = payload.get("one_x_two") or {}
    over_under = payload.get("over_under") or {}
    detailed = payload.get("detailed_markets") or {}
    if not one_x_two and detailed.get("match_winner"):
        one_x_two = detailed["match_winner"]
    if not over_under and detailed.get("over_under_25"):
        over_under = detailed["over_under_25"]
    btts = (payload.get("extended_markets") or {}).get("btts") or detailed.get("btts") or {}
    btts_pick = None
    if btts:
        if btts.get("selection"):
            btts_pick = str(btts.get("selection")).lower()
        else:
            yes = float(btts.get("yes") or btts.get("option_a") or btts.get("probability") or 0)
            btts_pick = "yes" if yes >= 0.5 else "no"
    scoreline = payload.get("scoreline") or {}
    predicted_scoreline = scoreline.get("label") if isinstance(scoreline, dict) else None
    return {
        "predicted_1x2": one_x_two.get("selection"),
        "predicted_over_under_2_5": over_under.get("selection"),
        "predicted_scoreline": predicted_scoreline,
        "confidence_score": float(payload.get("confidence_score") or payload.get("confidence") or 0),
        "no_bet_flag": bool(payload.get("no_bet_flag", False)),
        "risk_level": payload.get("risk_level") or "medium",
        "btts_pick": btts_pick,
        "generated_by": payload.get("generated_by") or row["source"],
    }


def _scoreline_to_1x2(scoreline: str | None) -> str | None:
    if not scoreline or "-" not in str(scoreline):
        return None
    try:
        hg, ag = [int(x.strip()) for x in str(scoreline).replace(":", "-").split("-", 1)]
    except (TypeError, ValueError):
        return None
    if hg > ag:
        return "home_win"
    if hg < ag:
        return "away_win"
    return "draw"


def _normalize_1x2(value: str | None) -> str | None:
    if not value:
        return None
    text = str(value).lower().strip().replace(" ", "_")
    return {"home": "home_win", "away": "away_win", "1": "home_win", "x": "draw", "2": "away_win"}.get(text, text)


def _draw_pen_warning(wde: dict[str, Any] | None, ecse: dict[str, Any] | None) -> str | None:
    if not ecse:
        return None
    top10 = ecse.get("top_10_scorelines") or ecse.get("top_5_scores") or []
    scorelines = []
    for item in top10:
        if isinstance(item, dict):
            scorelines.append(str(item.get("scoreline") or ""))
        else:
            scorelines.append(str(item))
    draw_in_top10 = any(s in ("1-1", "0-0") for s in scorelines[:10])
    ecse_top1 = str(ecse.get("top_1_score") or "")
    wde_draw = False
    wde_under = False
    wde_no_bet = False
    balanced = False
    if wde:
        pick = _normalize_1x2(wde.get("predicted_1x2"))
        wde_draw = pick == "draw"
        ou = str(wde.get("predicted_over_under_2_5") or "").lower()
        wde_under = "under" in ou
        wde_no_bet = bool(wde.get("no_bet_flag"))
    if draw_in_top10 or ecse_top1 in ("1-1", "0-0"):
        if wde_draw or wde_under or wde_no_bet or draw_in_top10:
            return "Draw/PEN risk — 1-1 should be considered as cover score."
    return None


def _resolve_expected_fixtures(
    conn,
    api: ApiFootballClient,
    *,
    target_date: str,
    tz_name: str,
) -> list[DailyFixture]:
    start_utc, end_utc = vienna_day_utc_bounds(resolve_target_date(target_date, tz_name), tz_name)
    out: list[DailyFixture] = []
    seen: set[int] = set()

    for home, away in EXPECTED_TODAY:
        row = conn.execute(
            """
            SELECT fixture_id, competition_key, home_team, away_team, kickoff_utc, status, season
            FROM fixtures
            WHERE competition_key = 'world_cup_2026'
              AND lower(home_team) LIKE ?
              AND lower(away_team) LIKE ?
            ORDER BY kickoff_utc DESC LIMIT 1
            """,
            (f"%{home.lower().split()[0]}%", f"%{away.lower().split()[0]}%"),
        ).fetchone()
        if row:
            fid = int(row["fixture_id"])
            if fid not in seen:
                seen.add(fid)
                out.append(
                    DailyFixture(
                        fixture_id=fid,
                        provider_fixture_id=fid,
                        competition_key="world_cup_2026",
                        home_team=str(row["home_team"]),
                        away_team=str(row["away_team"]),
                        kickoff_utc=str(row["kickoff_utc"]),
                        status=str(row["status"] or "NS"),
                        season=int(row["season"]) if row["season"] is not None else 2026,
                        coverage_sources=["local_db"],
                    )
                )
            continue

        snap = conn.execute(
            """
            SELECT fixture_id, home_team, away_team, kickoff_utc
            FROM ecse_prediction_snapshots
            WHERE competition_key = 'world_cup_2026'
              AND lower(home_team) LIKE ?
              AND lower(away_team) LIKE ?
            ORDER BY generated_at DESC LIMIT 1
            """,
            (f"%{home.lower().split()[0]}%", f"%{away.lower().split()[0]}%"),
        ).fetchone()
        if snap:
            fid = int(snap["fixture_id"])
            if fid not in seen:
                seen.add(fid)
                out.append(
                    DailyFixture(
                        fixture_id=fid,
                        provider_fixture_id=fid,
                        competition_key="world_cup_2026",
                        home_team=str(snap["home_team"]),
                        away_team=str(snap["away_team"]),
                        kickoff_utc=str(snap["kickoff_utc"]),
                        status="NS",
                        season=2026,
                        coverage_sources=["ecse_snapshot"],
                    )
                )
            continue

        if api.is_configured:
            for target in WIN2DAY_SMOKE_TARGETS:
                if target.home_team == home and target.away_team == away:
                    pass
            for fid_hint in _fixture_ids_for_pair(home, away):
                result = api.get_fixture_by_id(fid_hint)
                if result.ok and isinstance(result.data, list) and result.data:
                    item = result.data[0]
                    fix = item.get("fixture") or {}
                    teams = item.get("teams") or {}
                    fid = int(fix.get("id") or fid_hint)
                    if fid in seen:
                        break
                    seen.add(fid)
                    ko = str(fix.get("date") or "").replace("+00:00", "")
                    if ko and (ko < start_utc or ko > end_utc):
                        pass
                    out.append(
                        DailyFixture(
                            fixture_id=fid,
                            provider_fixture_id=fid,
                            competition_key="world_cup_2026",
                            home_team=str(teams.get("home", {}).get("name") or home),
                            away_team=str(teams.get("away", {}).get("name") or away),
                            kickoff_utc=ko,
                            status=str((fix.get("status") or {}).get("short") or "NS"),
                            season=2026,
                            coverage_sources=["api_football"],
                        )
                    )
                    break
    out.sort(key=lambda f: f.kickoff_utc or "")
    return out


def _fixture_ids_for_pair(home: str, away: str) -> tuple[int, ...]:
    mapping = {
        ("Ivory Coast", "Norway"): (1564789,),
        ("France", "Sweden"): (1565177,),
        ("Mexico", "Ecuador"): (1567306,),
    }
    return mapping.get((home, away), ())


def _readonly_conn(settings):
    db_path = get_db_path(settings.sqlite_path)
    conn = sqlite3.connect(f"file:{db_path.as_posix()}?mode=ro", uri=True, timeout=60.0)
    conn.row_factory = sqlite3.Row
    return conn


def build_wc_today_report(*, date_arg: str = "today", tz_name: str = "Europe/Vienna") -> dict[str, Any]:
    settings = get_settings()
    conn = _readonly_conn(settings)
    tz = ZoneInfo(tz_name)
    target = resolve_target_date(date_arg, tz_name)
    ymd = target.isoformat().replace("-", "")

    start_utc, end_utc = vienna_day_utc_bounds(target, tz_name)
    discovery_fixtures = discover_fixtures_from_db(
        conn,
        competition_keys=["world_cup_2026"],
        start_utc=start_utc,
        end_utc=end_utc,
        limit=20,
    )
    fixtures = list(discovery_fixtures)
    api = ApiFootballClient(settings)
    expected = _resolve_expected_fixtures(conn, api, target_date=target.isoformat(), tz_name=tz_name)
    by_id = {f.provider_fixture_id: f for f in fixtures}
    for fx in expected:
        by_id.setdefault(fx.provider_fixture_id, fx)
    fixtures = sorted(by_id.values(), key=lambda f: f.kickoff_utc or "")

    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()
    rows: list[dict[str, Any]] = []
    wde_count = ecse_count = odds_count = shadow_count = 0
    missing_warnings: list[str] = []
    no_bet_matches: list[str] = []
    strongest: str | None = None
    strongest_conf = -1.0

    for idx, fx in enumerate(fixtures, start=1):
        wde = _load_wde_readonly(conn, fx.provider_fixture_id, fx.competition_key)
        ecse = _load_ecse_row(conn, fx.provider_fixture_id)
        shadow_top1 = _shadow_enhanced_top1(fx.provider_fixture_id)
        owner_shadow = get_owner_shadow_for_fixture(fx.provider_fixture_id)
        odds_info = scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)
        label = _owner_label(wde, ecse)

        if wde and wde.get("predicted_1x2") is None and wde.get("confidence_score"):
            label = OWNER_LABEL_DATA_MISSING if ecse is None else OWNER_LABEL_WEAK

        if wde is None and ecse is not None:
            label = OWNER_LABEL_DATA_MISSING
            missing_warnings.append(f"{fx.home_team} vs {fx.away_team}: WDE missing")
        if ecse is None:
            missing_warnings.append(f"{fx.home_team} vs {fx.away_team}: ECSE missing")
        if not odds_info.get("has_1x2"):
            missing_warnings.append(f"{fx.home_team} vs {fx.away_team}: odds 1X2 missing")

        if wde:
            wde_count += 1
        if ecse:
            ecse_count += 1
        if odds_info.get("has_1x2"):
            odds_count += 1
        if shadow_top1 or owner_shadow:
            shadow_count += 1
        if label == OWNER_LABEL_NO_BET:
            no_bet_matches.append(f"{fx.home_team} vs {fx.away_team}")
        conf = float((wde or {}).get("confidence_score") or 0)
        if label == OWNER_LABEL_STRONG and conf > strongest_conf:
            strongest_conf = conf
            strongest = f"{fx.home_team} vs {fx.away_team}"

        pen_warn = _draw_pen_warning(wde, ecse)
        enrichment = load_fixture_enrichment(conn, fx.provider_fixture_id)
        note_parts = [
            "Use Top-3 exact-score cover, not single-score confidence.",
        ]
        if pen_warn:
            note_parts.append(pen_warn)
        if owner_shadow and owner_shadow.get("rejection_reason"):
            note_parts.append(f"Shadow: {owner_shadow.get('rejection_reason')}")
        if fx.provider_fixture_id not in {f.provider_fixture_id for f in discovery_fixtures}:
            note_parts.append("Fixture not in daily discovery DB window — sourced from ECSE/API.")
        if enrichment.get("referee"):
            ref = enrichment["referee"]
            note_parts.append(
                f"Enrichment (info): ref {ref.get('referee_name')} "
                f"YC avg {ref.get('yellow_cards_avg')} BTB {ref.get('both_teams_booked_per')}"
            )

        enhanced = shadow_top1 or (owner_shadow or {}).get("m5_shadow_top1")
        row = {
            "index": idx,
            "match": f"{fx.home_team} vs {fx.away_team}",
            "fixture_id": fx.provider_fixture_id,
            "kickoff_vienna": _format_kickoff_local(fx.kickoff_utc, tz),
            "kickoff_utc": fx.kickoff_utc,
            "status": fx.status,
            "wde_1x2": wde.get("predicted_1x2") if wde else None,
            "wde_ou_25": wde.get("predicted_over_under_2_5") if wde else None,
            "wde_btts": wde.get("btts_pick") if wde else None,
            "wde_confidence": wde.get("confidence_score") if wde else None,
            "wde_no_bet": wde.get("no_bet_flag") if wde else None,
            "wde_reason": (wde or {}).get("generated_by"),
            "ecse_top1": ecse.get("top_1_score") if ecse else None,
            "ecse_top3": _top_scores_text(ecse.get("top_3_scores") if ecse else [], 3),
            "ecse_top5": _top_scores_text(ecse.get("top_5_scores") if ecse else [], 5),
            "ecse_confidence": ecse.get("confidence_score") if ecse else None,
            "lambda_home": ecse.get("lambda_home") if ecse else None,
            "lambda_away": ecse.get("lambda_away") if ecse else None,
            "shadow_enhanced_top1": enhanced,
            "shadow_baseline_top1": (owner_shadow or {}).get("baseline_top1"),
            "shadow_applied": (owner_shadow or {}).get("m5_shadow_applied"),
            "shadow_exclusion": (owner_shadow or {}).get("rejection_reason"),
            "owner_label": label,
            "note": " | ".join(note_parts),
            "odds_source": odds_info.get("odds_source"),
            "coverage_sources": fx.coverage_sources,
            "oddalerts_enrichment": enrichment,
        }
        rows.append(row)

    summary = {
        "date": target.isoformat(),
        "timezone": tz_name,
        "competition": "world_cup_2026",
        "fixtures_found": len(fixtures),
        "fixtures_with_wde": wde_count,
        "fixtures_with_ecse": ecse_count,
        "fixtures_with_odds": odds_count,
        "fixtures_with_shadow_data": shadow_count,
        "provider_calls_used": {},
        "missing_data_warnings": missing_warnings,
        "strongest_signal_of_the_day": strongest,
        "no_bet_matches": no_bet_matches,
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / f"wc_today_predictions_{ymd}.md"
    json_path = REPORTS_DIR / f"wc_today_predictions_{ymd}.json"

    lines = [
        f"# Owner WC Today Predictions — {target.isoformat()}",
        "",
        f"Timezone: **{tz_name}** | Competition: **world_cup_2026** | Owner/internal only",
        "",
        "## Summary",
        "",
        f"- Fixtures found: **{summary['fixtures_found']}**",
        f"- WDE: **{wde_count}** | ECSE: **{ecse_count}** | Odds: **{odds_count}** | Shadow: **{shadow_count}**",
        f"- Strongest signal: **{strongest or '—'}**",
        f"- No-bet matches: **{', '.join(no_bet_matches) or '—'}**",
        "",
    ]
    if missing_warnings:
        lines.append("### Missing data warnings")
        for w in missing_warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines.extend(
        [
            "## Main table",
            "",
            "| # | Match | Kickoff Europe/Vienna | WDE 1X2 | WDE O/U 2.5 | WDE BTTS | WDE confidence | ECSE Top-1 | ECSE Top-3 | Shadow enhanced Top-1 | Owner label | Note |",
            "|---|-------|----------------------|---------|-------------|----------|----------------|------------|------------|----------------------|-------------|------|",
        ]
    )
    for r in rows:
        lines.append(
            f"| {r['index']} | {r['match']} | {r['kickoff_vienna']} | "
            f"{r.get('wde_1x2') or '—'} | {r.get('wde_ou_25') or '—'} | {r.get('wde_btts') or '—'} | "
            f"{r.get('wde_confidence') or '—'} | {r.get('ecse_top1') or '—'} | {r.get('ecse_top3') or '—'} | "
            f"{r.get('shadow_enhanced_top1') or '—'} | **{r['owner_label']}** | {r.get('note', '')[:80]} |"
        )

    lines.extend(["", "## Match details", ""])
    for r in rows:
        lines.append(f"### {r['index']}. {r['match']} (fixture {r['fixture_id']})")
        lines.append(f"- Kickoff: {r['kickoff_vienna']} | Status: {r.get('status')}")
        lines.append(f"- ECSE Top-5: {r.get('ecse_top5') or '—'}")
        lines.append(f"- λ home/away: {r.get('lambda_home')} / {r.get('lambda_away')}")
        lines.append(f"- Shadow baseline Top-1: {r.get('shadow_baseline_top1') or '—'} | enhanced: {r.get('shadow_enhanced_top1') or '—'}")
        lines.append(f"- Shadow applied: {r.get('shadow_applied')} | exclusion: {r.get('shadow_exclusion') or '—'}")
        lines.append(f"- Owner label: **{r['owner_label']}**")
        enr = r.get("oddalerts_enrichment") or {}
        ref = enr.get("referee")
        if ref:
            lines.append(
                f"- **OddAlerts enrichment (info only):** Referee **{ref.get('referee_name')}** | "
                f"yellow_cards_avg **{ref.get('yellow_cards_avg')}** | "
                f"both_teams_booked_per **{ref.get('both_teams_booked_per')}**"
            )
        for label, key in (
            ("Top goals", "top_goals"),
            ("Top shots", "top_shots"),
            ("Top shots OT", "top_shots_ot"),
            ("Top rating", "top_rating"),
        ):
            top = enr.get(key) or []
            if top:
                bits = []
                for p in top[:5]:
                    cap = " (C)" if p.get("is_captain") else ""
                    inj = " (inj)" if p.get("is_injured") else ""
                    bits.append(f"{p.get('player')}{cap}{inj}={p.get('value')}")
                lines.append(f"- {label}: {', '.join(bits)}")
        if not ref and not any(enr.get(k) for k in ("top_goals", "top_rating")):
            lines.append("- OddAlerts enrichment: —")
        lines.append(f"- Note: {r.get('note')}")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False), encoding="utf-8")

    return {"summary": summary, "md_path": str(md_path), "json_path": str(json_path), "rows": rows}


def main() -> int:
    result = build_wc_today_report()
    print(json.dumps({k: result[k] for k in ("summary", "md_path", "json_path")}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
