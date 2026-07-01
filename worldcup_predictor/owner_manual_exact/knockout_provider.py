"""Owner knockout provider mapping, data audit, and fetch for ECSE generation."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.backtesting.phase31e_backfill import normalize_odds_bookmakers
from worldcup_predictor.clients.api_football import ApiFootballClient
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.data_import.european_fixture_feed import ensure_euro_fixture_feed_tables
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.integrations.fixture_api_parser import parse_api_fixture_item
from worldcup_predictor.owner.euro_b_fixture_selector import _odds_flags
from worldcup_predictor.owner.euro_c_odds_import import is_fake_odds_payload
from worldcup_predictor.owner_manual_exact.constants import ARTIFACTS_DIR, PHASE, REPORTS_DIR, with_safety_labels
from worldcup_predictor.owner_manual_exact.fixture_import import _import_item
from worldcup_predictor.owner_manual_exact.knockout_ecse_common import (
    compute_ecse_layers,
    ecse_generation_reason,
    minimum_ecse_inputs_met,
)
from worldcup_predictor.owner_manual_exact.resolver import _date_tag, load_resolution_artifact
from worldcup_predictor.owner_manual_exact.team_aliases import normalize_for_match
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient
from worldcup_predictor.providers.sportmonks_fixture_lookup import lookup_world_cup_fixture
from worldcup_predictor.research.ecse_live.store import has_snapshot

PHASE_PROVIDER = "OWNER-KNOCKOUT-ECSE-PROVIDER"
KICKOFF_TOLERANCE_HOURS = 3.0


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _inc(bucket: dict[str, int], key: str, n: int = 1) -> None:
    bucket[key] = bucket.get(key, 0) + n


def _has_enrichment(repo: FootballIntelligenceRepository, fixture_id: int, key: str) -> bool:
    row = repo.get_fixture_enrichment_row(fixture_id)
    if not row:
        return False
    blob = row.get("payload_json") or row.get("enrichment_json")
    if not blob:
        return False
    try:
        data = json.loads(blob) if isinstance(blob, str) else blob
    except (json.JSONDecodeError, TypeError):
        return False
    return isinstance(data, dict) and data.get(key) is not None


def _oddalerts_match_key(home: str, away: str, kickoff_utc: str | None) -> str | None:
    if not kickoff_utc:
        return None
    date_part = str(kickoff_utc)[:10]
    return f"{date_part}|{normalize_for_match(home)}|{normalize_for_match(away)}"


def _lookup_oddalerts_fixture_id(
    *,
    home_team: str,
    away_team: str,
    settings: Settings,
) -> int | None:
    client = OddAlertsClient()
    if not client.is_configured:
        return None
    upcoming = client.get_value_upcoming(per_page=250)
    if not upcoming.data:
        return None
    home_norm = normalize_for_match(home_team)
    away_norm = normalize_for_match(away_team)
    for row in (upcoming.data or {}).get("data") or []:
        h = normalize_for_match(str(row.get("home_name") or row.get("home") or ""))
        a = normalize_for_match(str(row.get("away_name") or row.get("away") or ""))
        if h == home_norm and a == away_norm:
            fid = int(row.get("id") or 0)
            if fid:
                return fid
    return None


def build_provider_fixture_map(
    conn: sqlite3.Connection,
    *,
    resolution: dict[str, Any],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Cross-provider fixture map for resolved knockout fixtures."""
    settings = settings or get_settings()
    ensure_euro_fixture_feed_tables(conn)
    mappings: list[dict[str, Any]] = []

    for row in resolution.get("matches") or []:
        res = row.get("resolution") or {}
        if res.get("resolution_status") != "RESOLVED":
            continue
        local_id = int(res["fixture_id"])
        home = str(res.get("home_team_canonical") or row.get("home_team_input") or "")
        away = str(res.get("away_team_canonical") or row.get("away_team_input") or "")
        kickoff = str(res.get("kickoff_utc") or (row.get("kickoff") or {}).get("kickoff_utc") or "")
        kickoff_date = kickoff[:10] if kickoff else None

        api_football_id = local_id
        feed_row = conn.execute(
            """
            SELECT provider, provider_fixture_id, competition_key
            FROM euro_fixture_feed
            WHERE fixture_id = ? AND provider = 'api-football'
            LIMIT 1
            """,
            (local_id,),
        ).fetchone()
        if feed_row:
            api_football_id = int(feed_row["provider_fixture_id"])

        sm_lookup = lookup_world_cup_fixture(
            api_fixture_id=api_football_id,
            home_team=home,
            away_team=away,
            kickoff_date=kickoff_date,
            settings=settings,
        )
        sportmonks_id = int(sm_lookup.sportmonks_fixture_id) if sm_lookup.found and sm_lookup.sportmonks_fixture_id else None

        repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        enrich = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(api_football_id)
        if enrich and enrich.get("sportmonks_fixture_id") and not sportmonks_id:
            sportmonks_id = int(enrich["sportmonks_fixture_id"])
        repo.close()

        oddalerts_id = _lookup_oddalerts_fixture_id(home_team=home, away_team=away, settings=settings)
        match_key = _oddalerts_match_key(home, away, kickoff)

        crosswalk_method = "canonical_api_football"
        if sm_lookup.found:
            crosswalk_method = f"sportmonks:{sm_lookup.reason}"
        elif sportmonks_id:
            crosswalk_method = "sportmonks_enrichment_cache"

        mappings.append(
            {
                "local_fixture_id": local_id,
                "home_team": home,
                "away_team": away,
                "kickoff_utc": kickoff,
                "competition_key": str(res.get("competition_key") or "world_cup_2026"),
                "api_football_fixture_id": api_football_id,
                "sportmonks_fixture_id": sportmonks_id,
                "oddalerts_fixture_id": oddalerts_id,
                "oddalerts_match_key": match_key,
                "crosswalk_method": crosswalk_method,
                "crosswalk_confidence": 1.0 if api_football_id == local_id else 0.99,
                "kickoff_tolerance_hours": KICKOFF_TOLERANCE_HOURS,
            }
        )
    return mappings


def audit_fixture_ecse_data(
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    *,
    row: dict[str, Any],
    mapping: dict[str, Any] | None,
    settings: Settings,
) -> dict[str, Any]:
    res = row.get("resolution") or {}
    fid = int(res["fixture_id"])
    home = str(res.get("home_team_canonical") or row.get("home_team_input") or "")
    away = str(res.get("away_team_canonical") or row.get("away_team_input") or "")
    kickoff = str(res.get("kickoff_utc") or (row.get("kickoff") or {}).get("kickoff_utc") or "")

    odds = _odds_flags(conn, fid)
    layers_used, layers_missing, completeness = compute_ecse_layers(conn, repo, fixture_id=fid)
    standings = _has_enrichment(repo, fid, "standings")
    history = _has_enrichment(repo, fid, "recent_form") or _has_enrichment(repo, fid, "head_to_head")
    predictions_available = bool(
        (repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(fid) or {}).get("premium_predictions_available")
        or (repo.get_worldcup_stored_prediction(fid) or {}).get("payload_json")
    )

    return {
        "match_no": row.get("match_no"),
        "local_fixture_id": fid,
        "home_team": home,
        "away_team": away,
        "kickoff_utc": kickoff,
        "api_football_fixture_id": (mapping or {}).get("api_football_fixture_id", fid),
        "sportmonks_fixture_id": (mapping or {}).get("sportmonks_fixture_id"),
        "oddalerts_match_key": (mapping or {}).get("oddalerts_match_key"),
        "oddalerts_fixture_id": (mapping or {}).get("oddalerts_fixture_id"),
        "odds_available": bool(odds.get("has_odds")),
        "predictions_available": predictions_available,
        "xg_available": repo.has_xg_snapshot(fid),
        "pressure_available": _has_enrichment(repo, fid, "pressure"),
        "lineups_available": _has_enrichment(repo, fid, "lineups") or _has_enrichment(repo, fid, "formations"),
        "injuries_available": _has_enrichment(repo, fid, "injuries"),
        "standings_available": standings,
        "history_available": history,
        "minimum_ecse_inputs_met": minimum_ecse_inputs_met(
            conn, repo, fixture_id=fid, home_team=home, away_team=away, kickoff_utc=kickoff
        )[0],
        "ecse_exists": has_snapshot(conn, fid),
        "ecse_layers_used": layers_used,
        "ecse_layers_missing": layers_missing,
        "ecse_completeness_score": completeness,
        "ecse_reason": ecse_generation_reason(
            conn, repo, fixture_id=fid, home_team=home, away_team=away, kickoff_utc=kickoff
        ),
    }


@dataclass
class KnockoutEcseAuditResult:
    phase: str = PHASE_PROVIDER
    process_date: str = ""
    fixture_count: int = 0
    fixtures: list[dict[str, Any]] = field(default_factory=list)
    provider_mappings: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                "phase": self.phase,
                "process_date": self.process_date,
                "fixture_count": self.fixture_count,
                "summary": self.summary,
                "provider_mappings": self.provider_mappings,
                "fixtures": self.fixtures,
                "completed_at_utc": _utc_now_iso(),
            }
        )


def run_knockout_ecse_data_audit(
    *,
    process_date: date,
    resolution: dict[str, Any] | None = None,
    settings: Settings | None = None,
) -> KnockoutEcseAuditResult:
    settings = settings or get_settings()
    if resolution is None:
        resolution = load_resolution_artifact(process_date)
    if resolution is None:
        return KnockoutEcseAuditResult(process_date=process_date.isoformat())

    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    mappings = build_provider_fixture_map(conn, resolution=resolution, settings=settings)
    map_by_id = {int(m["local_fixture_id"]): m for m in mappings}

    fixtures: list[dict[str, Any]] = []
    for row in resolution.get("matches") or []:
        res = row.get("resolution") or {}
        if res.get("resolution_status") != "RESOLVED":
            continue
        fid = int(res["fixture_id"])
        fixtures.append(
            audit_fixture_ecse_data(
                conn,
                repo,
                row=row,
                mapping=map_by_id.get(fid),
                settings=settings,
            )
        )

    summary = {
        "resolved_count": len(fixtures),
        "provider_mappings_found": sum(1 for m in mappings if m.get("sportmonks_fixture_id") or m.get("oddalerts_fixture_id")),
        "odds_available_count": sum(1 for f in fixtures if f.get("odds_available")),
        "predictions_available_count": sum(1 for f in fixtures if f.get("predictions_available")),
        "xg_available_count": sum(1 for f in fixtures if f.get("xg_available")),
        "ecse_exists_count": sum(1 for f in fixtures if f.get("ecse_exists")),
        "minimum_inputs_met_count": sum(1 for f in fixtures if f.get("minimum_ecse_inputs_met")),
        "ecse_missing_with_minimum_data": sum(
            1 for f in fixtures if f.get("minimum_ecse_inputs_met") and not f.get("ecse_exists")
        ),
    }

    repo.close()
    conn.close()
    return KnockoutEcseAuditResult(
        process_date=process_date.isoformat(),
        fixture_count=len(fixtures),
        fixtures=fixtures,
        provider_mappings=mappings,
        summary=summary,
    )


def write_knockout_ecse_audit_artifacts(
    result: KnockoutEcseAuditResult,
    *,
    process_date: date,
) -> dict[str, str]:
    tag = _date_tag(process_date)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    audit_path = ARTIFACTS_DIR / f"owner_knockout_ecse_data_audit_{tag}.json"
    map_path = ARTIFACTS_DIR / f"owner_knockout_provider_fixture_map_{tag}.json"
    report_path = REPORTS_DIR / f"owner_knockout_ecse_data_audit_{tag}.md"

    audit_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    map_payload = with_safety_labels(
        {
            "phase": PHASE_PROVIDER,
            "process_date": process_date.isoformat(),
            "mappings": result.provider_mappings,
            "mapping_count": len(result.provider_mappings),
        }
    )
    map_path.write_text(json.dumps(map_payload, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Owner Knockout ECSE Data Audit",
        "",
        f"**Date:** {process_date.isoformat()} | **Fixtures:** {result.fixture_count}",
        "",
        "## Summary",
        "",
    ]
    for k, v in (result.summary or {}).items():
        lines.append(f"- {k}: **{v}**")
    lines.extend(
        [
            "",
            "## Per fixture",
            "",
            "| Match | API-FB | Sportmonks | Odds | Pred | xG | ECSE | Completeness | Reason |",
            "| ----- | ------ | ---------- | ---- | ---- | -- | ---- | ------------ | ------ |",
        ]
    )
    for f in result.fixtures:
        lines.append(
            f"| {f.get('home_team')} vs {f.get('away_team')} | {f.get('api_football_fixture_id')} | "
            f"{f.get('sportmonks_fixture_id') or '—'} | {'Y' if f.get('odds_available') else 'N'} | "
            f"{'Y' if f.get('predictions_available') else 'N'} | {'Y' if f.get('xg_available') else 'N'} | "
            f"{'Y' if f.get('ecse_exists') else 'N'} | {f.get('ecse_completeness_score')} | "
            f"{f.get('ecse_reason')} |"
        )
    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "audit_json": str(audit_path),
        "provider_map_json": str(map_path),
        "audit_report": str(report_path),
    }


@dataclass
class KnockoutProviderFetchResult:
    phase: str = PHASE_PROVIDER
    process_date: str = ""
    counts: dict[str, int] = field(default_factory=dict)
    per_fixture: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                "phase": self.phase,
                "process_date": self.process_date,
                "counts": self.counts,
                "per_fixture": self.per_fixture,
                "errors": self.errors,
                "completed_at_utc": _utc_now_iso(),
            }
        )


def _save_api_fixture(
    *,
    conn: sqlite3.Connection,
    repo: FootballIntelligenceRepository,
    item: dict[str, Any],
    competition_key: str,
    league_id: int,
    season: int,
) -> str:
    parsed = parse_api_fixture_item(item, source="live")
    if parsed is None:
        return "provider_error"
    outcome = _import_item(
        item,
        conn=conn,
        repo=repo,
        competition_key=competition_key,
        league_id=league_id,
        season=season,
        dry_run=False,
    )
    return "updated" if outcome == "updated" else "fetched"


def run_knockout_provider_fetch(
    *,
    process_date: date,
    fixture_ids: list[int] | None = None,
    resolution: dict[str, Any] | None = None,
    settings: Settings | None = None,
    force: bool = False,
) -> KnockoutProviderFetchResult:
    settings = settings or get_settings()
    if resolution is None:
        resolution = load_resolution_artifact(process_date)
    if resolution is None:
        return KnockoutProviderFetchResult(process_date=process_date.isoformat())

    from worldcup_predictor.config.competitions import get_competition

    comp = get_competition("world_cup_2026")
    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    ensure_euro_fixture_feed_tables(conn)
    api = ApiFootballClient(settings)
    oa = OddAlertsClient()

    counts: dict[str, int] = {}
    per_fixture: list[dict[str, Any]] = []
    errors: list[str] = []

    mappings = build_provider_fixture_map(conn, resolution=resolution, settings=settings)
    map_by_id = {int(m["local_fixture_id"]): m for m in mappings}

    for row in resolution.get("matches") or []:
        res = row.get("resolution") or {}
        if res.get("resolution_status") != "RESOLVED":
            continue
        fid = int(res["fixture_id"])
        if fixture_ids and fid not in fixture_ids:
            continue

        mapping = map_by_id.get(fid, {})
        api_id = int(mapping.get("api_football_fixture_id") or fid)
        detail: dict[str, Any] = {"fixture_id": fid, "api_football_fixture_id": api_id, "actions": []}

        # API-Football fixture refresh
        if api.is_configured:
            if repo.get_fixture_row(fid) and not force:
                detail["actions"].append({"provider": "api_football", "status": "skipped_existing", "entity": "fixture"})
                _inc(counts, "skipped_existing")
            else:
                fetch = api.get_fixture_by_id(api_id)
                if fetch.ok and isinstance(fetch.data, list) and fetch.data:
                    status = _save_api_fixture(
                        conn=conn,
                        repo=repo,
                        item=fetch.data[0],
                        competition_key="world_cup_2026",
                        league_id=comp.league_id,
                        season=comp.season,
                    )
                    detail["actions"].append({"provider": "api_football", "status": status, "entity": "fixture"})
                    _inc(counts, status)
                elif not fetch.data:
                    detail["actions"].append({"provider": "api_football", "status": "provider_empty_response", "entity": "fixture"})
                    _inc(counts, "provider_empty_response")
                else:
                    detail["actions"].append({"provider": "api_football", "status": "provider_error", "entity": "fixture"})
                    _inc(counts, "provider_error")
                    errors.append(fetch.error or f"{api_id}: fixture fetch failed")
        else:
            _inc(counts, "missing_provider_mapping")
            detail["actions"].append({"provider": "api_football", "status": "missing_provider_mapping", "entity": "fixture"})

        # API-Football odds
        odds_flags = _odds_flags(conn, fid)
        if odds_flags.get("has_odds") and not force:
            detail["actions"].append({"provider": "api_football", "status": "skipped_existing", "entity": "odds"})
            _inc(counts, "skipped_existing")
        elif api.is_configured:
            result = api.get_odds(api_id)
            if result.ok and not is_fake_odds_payload(result.data, source=result.source):
                bookmakers = normalize_odds_bookmakers(result.data)
                if bookmakers:
                    repo.save_snapshot(
                        "odds_snapshots",
                        fixture_id=fid,
                        competition_key="world_cup_2026",
                        payload={"bookmakers": bookmakers, "source": result.source, "provider": "api-football"},
                    )
                    detail["actions"].append({"provider": "api_football", "status": "fetched", "entity": "odds"})
                    _inc(counts, "fetched")
                else:
                    detail["actions"].append({"provider": "api_football", "status": "provider_empty_response", "entity": "odds"})
                    _inc(counts, "provider_empty_response")
            else:
                odds_1x2 = row.get("odds_1x2") or {}
                btts = row.get("btts_odds") or {}
                if odds_1x2 and btts:
                    from worldcup_predictor.owner_manual_exact.knockout_production import _screenshot_odds_payload

                    payload = _screenshot_odds_payload(odds_1x2=odds_1x2, btts_odds=btts)
                    repo.save_snapshot(
                        "odds_snapshots",
                        fixture_id=fid,
                        competition_key="world_cup_2026",
                        payload=payload,
                    )
                    detail["actions"].append({"provider": "owner_manual_screenshot", "status": "fetched", "entity": "odds"})
                    _inc(counts, "fetched")
                else:
                    detail["actions"].append({"provider": "api_football", "status": "provider_error", "entity": "odds"})
                    _inc(counts, "provider_error")

        # Sportmonks crosswalk + enrichment
        sm_id = mapping.get("sportmonks_fixture_id")
        if sm_id:
            enrich_existing = repo.get_sportmonks_fixture_enrichment_by_api_fixture_id(api_id)
            if enrich_existing and not force:
                detail["actions"].append({"provider": "sportmonks", "status": "skipped_existing", "entity": "enrichment"})
                _inc(counts, "skipped_existing")
            else:
                try:
                    from worldcup_predictor.providers.sportmonks_enrichment import fetch_worldcup_fixture_enrichment

                    sm_result = fetch_worldcup_fixture_enrichment(
                        sportmonks_fixture_id=int(sm_id),
                        fixture_id_api_football=api_id,
                        repo=repo,
                        settings=settings,
                        force_refresh=force,
                    )
                    if sm_result.success:
                        detail["actions"].append({"provider": "sportmonks", "status": "fetched", "entity": "enrichment"})
                        _inc(counts, "fetched")
                    elif sm_result.premium_access and any(
                        sm_result.premium_access.get(k) for k in ("premium_odds_access_denied", "premium_xg_access_denied")
                    ):
                        detail["actions"].append({"provider": "sportmonks", "status": "provider_empty_response", "entity": "enrichment"})
                        _inc(counts, "provider_empty_response")
                    else:
                        detail["actions"].append({"provider": "sportmonks", "status": "provider_error", "entity": "enrichment"})
                        _inc(counts, "provider_error")
                        errors.append(sm_result.message or f"sportmonks {sm_id}: fetch failed")
                except Exception as exc:
                    detail["actions"].append({"provider": "sportmonks", "status": "provider_error", "entity": "enrichment"})
                    _inc(counts, "provider_error")
                    errors.append(f"sportmonks {sm_id}: {exc}")
        else:
            detail["actions"].append({"provider": "sportmonks", "status": "missing_provider_mapping", "entity": "enrichment"})
            _inc(counts, "missing_provider_mapping")

        # OddAlerts attach (metadata only when fixture id known)
        oa_id = mapping.get("oddalerts_fixture_id")
        if oa_id and oa.is_configured:
            detail["actions"].append({"provider": "oddalerts", "status": "mapped", "entity": "fixture", "oddalerts_fixture_id": oa_id})
            _inc(counts, "fetched")
        elif oa.is_configured:
            detail["actions"].append({"provider": "oddalerts", "status": "missing_provider_mapping", "entity": "fixture"})
            _inc(counts, "missing_provider_mapping")

        per_fixture.append(detail)

    conn.commit()
    repo.close()
    conn.close()

    # Persist provider map artifact
    map_path = ARTIFACTS_DIR / f"owner_knockout_provider_fixture_map_{_date_tag(process_date)}.json"
    map_path.write_text(
        json.dumps(
            with_safety_labels(
                {
                    "phase": PHASE_PROVIDER,
                    "process_date": process_date.isoformat(),
                    "mappings": mappings,
                }
            ),
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    fetch_path = ARTIFACTS_DIR / f"owner_knockout_provider_fetch_{_date_tag(process_date)}.json"
    result = KnockoutProviderFetchResult(
        process_date=process_date.isoformat(),
        counts=counts,
        per_fixture=per_fixture,
        errors=errors,
    )
    fetch_path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

    return result
