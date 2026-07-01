"""Part F — Daily final-score prediction report (owner/internal)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner_daily.constants import (
    OWNER_LABEL_DATA_MISSING,
    OWNER_LABEL_MEDIUM,
    OWNER_LABEL_NO_BET,
    OWNER_LABEL_STRONG,
    OWNER_LABEL_WEAK,
    REPORTS_DIR,
)
from worldcup_predictor.owner_daily.data_completeness import FixtureCompletenessReport
from worldcup_predictor.owner_daily.odds_import import scan_fixture_odds_readiness
from worldcup_predictor.research.ecse_live.store import get_snapshot
from worldcup_predictor.research.ecse_x2_m6.store import read_shadow_shortlists
from worldcup_predictor.research.ecse_x3_b.store import get_owner_shadow_for_fixture
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider


def _parse_kickoff(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _format_kickoff_local(value: str | None, tz: ZoneInfo) -> str:
    dt = _parse_kickoff(value)
    return dt.astimezone(tz).strftime("%Y-%m-%d %H:%M %Z") if dt else "TBD"


def _scoreline_to_1x2(scoreline: str | None) -> str | None:
    if not scoreline or "-" not in str(scoreline):
        return None
    try:
        home_s, away_s = str(scoreline).replace(":", "-").split("-", 1)
        hg, ag = int(home_s.strip()), int(away_s.strip())
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
    return {"home": "home_win", "away": "away_win", "1": "home_win", "x": "draw", "2": "away_win"}.get(
        text, text
    )


def _load_wde(fixture_id: int, settings: Settings, competition_key: str) -> dict[str, Any] | None:
    season = 2026 if competition_key == "world_cup_2026" else 2025
    store = WorldcupPredictionStore(settings)
    payload = store.get(fixture_id, competition_key=competition_key, season=season, locale="en")
    if payload is None:
        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        row = repo.get_worldcup_stored_prediction(fixture_id)
        if row and row.get("payload_json"):
            try:
                payload = json.loads(row["payload_json"])
            except json.JSONDecodeError:
                payload = None
    if not payload:
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
        "confidence_score": float(
            payload.get("confidence_score") or payload.get("confidence") or 0
        ),
        "no_bet_flag": bool(payload.get("no_bet_flag", False)),
        "risk_level": payload.get("risk_level") or "medium",
        "btts_pick": btts_pick,
        "generated_by": payload.get("generated_by"),
    }


def _load_ecse(conn, fixture_id: int) -> dict[str, Any] | None:
    snap = get_snapshot(conn, fixture_id)
    if not snap:
        return None
    top5 = snap.get("top_5_scores") or snap.get("top5_scores") or []
    top3 = snap.get("top_3_scores") or snap.get("top3_scores") or []
    if isinstance(top5, str):
        try:
            top5 = json.loads(top5)
        except json.JSONDecodeError:
            top5 = []
    if isinstance(top3, str):
        try:
            top3 = json.loads(top3)
        except json.JSONDecodeError:
            top3 = []
    raw = snap.get("raw_features") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    return {
        "top_1_score": snap.get("top_1_score"),
        "top_3_scores": top3,
        "top_5_scores": top5,
        "confidence_score": float(snap.get("confidence_score") or 0),
        "prediction_source": snap.get("prediction_source"),
        "ecse_layers_used": raw.get("ecse_layers_used") or [],
        "ecse_layers_missing": raw.get("ecse_layers_missing") or [],
        "ecse_completeness_score": raw.get("ecse_completeness_score"),
        "partial_snapshot": raw.get("partial_snapshot", False),
    }


def _shadow_enhanced_top1(fixture_id: int) -> str | None:
    for row in read_shadow_shortlists(limit=5000):
        if int(row.get("fixture_id") or 0) != int(fixture_id):
            continue
        enhanced = row.get("enhanced_top10") or []
        if enhanced and isinstance(enhanced[0], dict):
            return str(enhanced[0].get("scoreline") or "")
        if enhanced:
            return str(enhanced[0])
    owner = get_owner_shadow_for_fixture(fixture_id)
    if owner and owner.get("enhanced_top1"):
        return str(owner["enhanced_top1"])
    return None


def _owner_label(wde: dict[str, Any] | None, ecse: dict[str, Any] | None) -> str:
    if wde is None or ecse is None:
        return OWNER_LABEL_DATA_MISSING
    if wde.get("no_bet_flag"):
        return OWNER_LABEL_NO_BET
    ecse_x2 = _scoreline_to_1x2(ecse.get("top_1_score"))
    wde_x2 = _normalize_1x2(wde.get("predicted_1x2"))
    conf = float(wde.get("confidence_score") or 0)
    ecse_conf = float(ecse.get("confidence_score") or 0)
    agree = ecse_x2 is not None and wde_x2 is not None and ecse_x2 == wde_x2
    if agree and conf >= 70 and ecse_conf >= 0.12:
        return OWNER_LABEL_STRONG
    if agree and conf >= 55:
        return OWNER_LABEL_MEDIUM
    if ecse_conf < 0.10 or conf < 55:
        return OWNER_LABEL_WEAK
    return OWNER_LABEL_MEDIUM if agree else OWNER_LABEL_WEAK


def _top_scores_text(rows: list[Any], n: int = 3) -> str:
    parts: list[str] = []
    for item in (rows or [])[:n]:
        if isinstance(item, dict):
            parts.append(str(item.get("scoreline") or item.get("label") or ""))
        else:
            parts.append(str(item))
    return ", ".join(p for p in parts if p)


@dataclass
class DailyReportResult:
    md_path: Path
    json_path: Path
    summary: dict[str, Any] = field(default_factory=dict)
    rows: list[dict[str, Any]] = field(default_factory=list)


def build_daily_report(
    fixtures: list[DailyFixture],
    completeness: list[FixtureCompletenessReport],
    *,
    target_date: str,
    timezone_name: str = "Europe/Vienna",
    provider_calls: dict[str, int] | None = None,
    settings: Settings | None = None,
    include_shadow: bool = False,
) -> DailyReportResult:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    tz = ZoneInfo(timezone_name)
    sm = SportmonksProvider(settings)
    oa = OddAlertsClient()
    comp_by_id = {c.fixture_id: c for c in completeness}
    rows: list[dict[str, Any]] = []

    wde_count = ecse_count = odds_count = missing_count = no_bet_count = strong_count = 0

    for idx, fx in enumerate(fixtures, start=1):
        wde = _load_wde(fx.provider_fixture_id, settings, fx.competition_key)
        ecse = _load_ecse(conn, fx.provider_fixture_id)
        comp = comp_by_id.get(fx.provider_fixture_id)
        label = _owner_label(wde, ecse)
        shadow_top1 = _shadow_enhanced_top1(fx.provider_fixture_id) if include_shadow else None
        odds_info = scan_fixture_odds_readiness(conn, fx, settings=settings, sm=sm, oa=oa)

        if wde:
            wde_count += 1
        if ecse:
            ecse_count += 1
        if comp and not comp.complete:
            missing_count += 1
        if label == OWNER_LABEL_NO_BET:
            no_bet_count += 1
        if label == OWNER_LABEL_STRONG:
            strong_count += 1
        if comp and "odds_snapshot" in comp.present:
            odds_count += 1

        missing_warn = ""
        if comp:
            high = [m.missing_field for m in comp.missing if m.priority == "HIGH"]
            missing_warn = ", ".join(high[:5])

        row = {
            "index": idx,
            "fixture": f"{fx.home_team} vs {fx.away_team}",
            "competition": fx.competition_key,
            "kickoff_local": _format_kickoff_local(fx.kickoff_utc, tz),
            "kickoff_utc": fx.kickoff_utc,
            "wde_1x2": wde.get("predicted_1x2") if wde else None,
            "wde_ou_25": wde.get("predicted_over_under_2_5") if wde else None,
            "wde_btts": wde.get("btts_pick") if wde else None,
            "wde_confidence": wde.get("confidence_score") if wde else None,
            "ecse_top1": ecse.get("top_1_score") if ecse else None,
            "ecse_top3": _top_scores_text(ecse.get("top_3_scores") if ecse else [], 3),
            "shadow_enhanced_top1": shadow_top1,
            "odds_source": odds_info.get("odds_source"),
            "odds_freshness": odds_info.get("odds_freshness"),
            "odds_snapshot_time": odds_info.get("odds_snapshot_time"),
            "owner_label": label,
            "missing_warning": missing_warn,
            "coverage_sources": fx.coverage_sources,
            "detail": {
                "wde": wde,
                "ecse": ecse,
                "completeness": comp.to_dict() if comp else None,
                "owner_note": (
                    "Use Top-3 exact-score cover, not single-score confidence. "
                    "ECSE exact-score Top-1 is naturally low probability."
                ),
                "final_score_shortlist": {
                    "main_exact_score": ecse.get("top_1_score") if ecse else None,
                    "cover_score_1": _top_scores_text(ecse.get("top_3_scores") if ecse else [], 2).split(", ")[1:2],
                    "cover_score_2": _top_scores_text(ecse.get("top_3_scores") if ecse else [], 3).split(", ")[2:3],
                },
            },
        }
        rows.append(row)

    summary = {
        "date": target_date,
        "timezone": timezone_name,
        "fixtures_found": len(fixtures),
        "fixtures_with_wde": wde_count,
        "fixtures_with_ecse": ecse_count,
        "fixtures_with_odds": odds_count,
        "fixtures_with_missing_data": missing_count,
        "provider_calls_used": provider_calls or {},
        "strongest_signals": strong_count,
        "no_bet_count": no_bet_count,
    }

    ymd = target_date.replace("-", "")
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    md_path = REPORTS_DIR / f"daily_predictions_{ymd}.md"
    json_path = REPORTS_DIR / f"daily_predictions_{ymd}.json"

    lines = [
        f"# Owner Daily Predictions — {target_date}",
        "",
        f"Timezone: **{timezone_name}** | Owner/internal only",
        "",
        "## Summary",
        "",
        f"- Fixtures found: **{summary['fixtures_found']}**",
        f"- WDE coverage: **{wde_count}** | ECSE coverage: **{ecse_count}** | Odds: **{odds_count}**",
        f"- Missing data warnings: **{missing_count}** | NO_BET: **{no_bet_count}** | Strong signals: **{strong_count}**",
        f"- Provider calls: `{json.dumps(provider_calls or {})}`",
        "",
        "## Main table",
        "",
        "| # | Fixture | Competition | Kickoff | WDE 1X2 | WDE O/U 2.5 | WDE BTTS | WDE conf | ECSE Top-1 | ECSE Top-3 | Shadow Top-1 | Label | Missing |",
        "|---|---------|-------------|---------|---------|-------------|----------|----------|------------|------------|--------------|-------|---------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['index']} | {r['fixture']} | {r['competition']} | {r['kickoff_local']} | "
            f"{r.get('wde_1x2') or '—'} | {r.get('wde_ou_25') or '—'} | {r.get('wde_btts') or '—'} | "
            f"{r.get('wde_confidence') or '—'} | {r.get('ecse_top1') or '—'} | {r.get('ecse_top3') or '—'} | "
            f"{r.get('shadow_enhanced_top1') or '—'} | **{r['owner_label']}** | {r.get('missing_warning') or '—'} |"
        )

    lines.extend(["", "## Match details", ""])
    for r in rows:
        lines.append(f"### {r['index']}. {r['fixture']} ({r['competition']})")
        lines.append(f"- Kickoff: {r['kickoff_local']}")
        lines.append(f"- Coverage: {', '.join(r.get('coverage_sources') or [])}")
        lines.append(f"- Odds source: {r.get('odds_source') or '—'} | Freshness: {r.get('odds_freshness') or '—'}")
        lines.append(f"- Owner label: **{r['owner_label']}**")
        detail = r.get("detail") or {}
        lines.append(f"- Owner note: {detail.get('owner_note', '')}")
        if detail.get("ecse"):
            lines.append(f"- ECSE Top-5: {_top_scores_text(detail['ecse'].get('top_5_scores'), 5)}")
        lines.append("")

    md_path.write_text("\n".join(lines), encoding="utf-8")
    json_path.write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return DailyReportResult(md_path=md_path, json_path=json_path, summary=summary, rows=rows)
