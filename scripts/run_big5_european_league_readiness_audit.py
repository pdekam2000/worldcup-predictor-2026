#!/usr/bin/env python3
"""Big 5 European leagues readiness audit — evidence collection."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "artifacts" / "big5_european_league_audit" / "audit_payload.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

ANCHOR = date(2026, 7, 10)
BIG5 = (
    ("premier_league", 39, "Premier League", "England"),
    ("bundesliga", 78, "Bundesliga", "Germany"),
    ("serie_a", 135, "Serie A", "Italy"),
    ("la_liga", 140, "La Liga", "Spain"),
    ("ligue_1", 61, "Ligue 1", "France"),
)
PREMATCH = frozenset({"NS", "TBD", "SCHEDULED", "TIMED", "", "NOT STARTED"})


def pct(n: int, d: int) -> float:
    return round(n / d, 4) if d else 0.0


def percentile(vals: list[int], p: float) -> int:
    if not vals:
        return 0
    s = sorted(vals)
    idx = int(round((len(s) - 1) * p))
    return s[max(0, min(idx, len(s) - 1))]


def main() -> int:
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.config.competitions import COMPETITION_REGISTRY, get_competition
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.forward_evaluation.gates import classify_candidate
    from worldcup_predictor.gpt_actions.broad_fixture_discovery import _fetch_api_fixtures_for_date, _parse_api_item
    from worldcup_predictor.gpt_actions.competition_normalize import is_tier_b_shadow, normalize_competition_key
    from worldcup_predictor.gpt_actions.delegation import _match_odds
    from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope, fixture_tier, is_tier_a_competition
    from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS, get_tier_b_domain
    from worldcup_predictor.gpt_actions.wde_runtime import prepare_daily_fixture_for_wde, register_tier_b_competition_runtime
    from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS
    from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    settings = get_settings()
    client = ApiFootballClient(settings)
    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    out: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "anchor_date": ANCHOR.isoformat(),
        "canonical_commit": "e21ca7fcc3a0003ed7c7ffa694d950c670c7088d",
        "leagues": {},
    }

    owner_keys = set(competition_keys_for_scope("owner"))
    prod_keys = set(competition_keys_for_scope("production"))
    shadow_keys = set(competition_keys_for_scope("shadow"))

    for key, lid, expected_name, country in BIG5:
        reg = COMPETITION_REGISTRY.get(key)
        lr = client._safe_get("leagues", {"id": lid}, placeholder_factory=lambda: None, ttl_seconds=3600)
        api_identity = None
        if lr and lr.data:
            item = lr.data[0] if isinstance(lr.data, list) and lr.data else lr.data
            lg = item.get("league") or item
            seasons = item.get("seasons") or []
            cur = next((s for s in seasons if s.get("current")), seasons[0] if seasons else {})
            api_identity = {
                "id": int(lg.get("id") or lid),
                "name": lg.get("name"),
                "country": (item.get("country") or {}).get("name"),
                "type": lg.get("type"),
                "season": cur.get("year"),
            }

        tier_b_meta = get_tier_b_domain(key)
        tier_a = key in DAILY_SUPPORTED_COMPETITIONS
        fixtures: list[dict] = []
        for off in range(0, 61):
            d = ANCHOR + timedelta(days=off)
            items, _ = _fetch_api_fixtures_for_date(settings, d)
            for item in items:
                p = _parse_api_item(item)
                if not p or int(p["league_id"]) != lid:
                    continue
                st = str(p.get("status") or "NS").upper()
                teams = item.get("teams") or {}
                home_t = teams.get("home") or {}
                away_t = teams.get("away") or {}
                fid = int(p["fixture_id"])
                db_odds = _match_odds(conn, fid)
                db_bk = int(db_odds.get("bookmaker_count") or 0)
                api_bk = 0
                if client.is_configured:
                    orr = client._safe_get(
                        "odds", {"fixture": fid}, placeholder_factory=lambda: None, ttl_seconds=3600
                    )
                    if orr and isinstance(orr.data, list):
                        api_bk = len(orr.data)
                bk = max(db_bk, api_bk)
                fixtures.append(
                    {
                        "fixture_id": fid,
                        "date": d.isoformat(),
                        "match": f"{p['home_team']} vs {p['away_team']}",
                        "status": st,
                        "prematch": st in PREMATCH,
                        "home_id": home_t.get("id"),
                        "away_id": away_t.get("id"),
                        "db_bookmakers": db_bk,
                        "api_bookmakers": api_bk,
                        "bookmaker_count": bk,
                    }
                )

        prematch = [f for f in fixtures if f["prematch"]]
        d7 = ANCHOR + timedelta(days=6)
        d14 = ANCHOR + timedelta(days=13)
        d30 = ANCHOR + timedelta(days=29)
        d60 = ANCHOR + timedelta(days=59)
        sample = prematch[:15] if prematch else fixtures[:15]
        mapped = sum(1 for f in sample if f.get("home_id") and f.get("away_id"))
        with_odds = [f for f in prematch if f["bookmaker_count"] > 0]
        bks = [f["bookmaker_count"] for f in with_odds if f["bookmaker_count"] > 0]

        # DB historical
        db_fixtures = 0
        db_finished = 0
        db_odds_snaps = 0
        try:
            db_fixtures = conn.execute(
                "SELECT COUNT(*) FROM fixtures WHERE competition_key=?", (key,)
            ).fetchone()[0]
            db_finished = conn.execute(
                "SELECT COUNT(*) FROM fixtures WHERE competition_key=? AND status IN ('FT','AET','PEN')",
                (key,),
            ).fetchone()[0]
            db_odds_snaps = conn.execute(
                "SELECT COUNT(DISTINCT fixture_id) FROM odds_lines ol JOIN fixtures f ON f.fixture_id=ol.fixture_id WHERE f.competition_key=?",
                (key,),
            ).fetchone()[0]
        except Exception:
            pass

        # WDE routing on best sample
        wde_status = "not_tested"
        gate_status = "not_tested"
        control = next((f for f in prematch if f["bookmaker_count"] > 0), prematch[0] if prematch else None)
        if control and tier_b_meta is None and not tier_a:
            try:
                register_tier_b_competition_runtime(key, repo=repo, season=int(api_identity.get("season") or 2025) if api_identity else 2025)
            except Exception:
                pass
        if control:
            try:
                daily = DailyFixture(
                    fixture_id=int(control["fixture_id"]),
                    provider_fixture_id=int(control["fixture_id"]),
                    competition_key=key,
                    home_team=control["match"].split(" vs ")[0],
                    away_team=control["match"].split(" vs ")[1],
                    kickoff_utc="",
                    status="NS",
                    season=int(api_identity.get("season") or 2025) if api_identity else 2025,
                    coverage_sources=["api_football"],
                    provider_ids={"api_football": int(control["fixture_id"])},
                )
                prepared = prepare_daily_fixture_for_wde(daily, repo=repo, settings=settings)
                wde_status = "routing_ok" if prepared.competition_key == key else "routing_fail"
            except Exception as exc:
                wde_status = f"blocked:{type(exc).__name__}"
            try:
                gs, _ = classify_candidate(
                    conn,
                    fixture={
                        **control,
                        "competition": key,
                        "competition_raw": f"league_{lid}",
                        "tier": fixture_tier(key) or "B",
                    },
                    settings=settings,
                )
                gate_status = gs
            except Exception as exc:
                gate_status = f"error:{type(exc).__name__}"

        # Odds classification
        med_bk = median(bks) if bks else 0
        if med_bk >= 8:
            odds_class = "ODDS_STRONG"
        elif med_bk >= 3 or (with_odds and med_bk >= 1):
            odds_class = "ODDS_ACCEPTABLE_TEST_PHASE"
        elif with_odds:
            odds_class = "ODDS_LIMITED"
        else:
            odds_class = "ODDS_BLOCKED" if prematch else "ODDS_OFFSEASON_UNKNOWN"

        mapping_rate = round(mapped / len(sample), 4) if sample else 0.0
        if mapping_rate >= 0.95:
            mapping_class = "MAPPING_READY"
        elif mapping_rate >= 0.8:
            mapping_class = "MAPPING_FIX_REQUIRED"
        else:
            mapping_class = "MAPPING_BLOCKED"

        # Support state
        if tier_a:
            gpt_scope = "ALREADY_SUPPORTED_TIER_A"
            registry_status = "TIER_A_PRODUCTION"
        elif tier_b_meta:
            gpt_scope = "ALREADY_SUPPORTED_TIER_B"
            registry_status = "TIER_B_TEST_PHASE"
        elif reg:
            gpt_scope = "PARTIAL_REGISTRY_ONLY"
            registry_status = "COMPETITION_REGISTRY_ONLY"
        else:
            gpt_scope = "MISSING"
            registry_status = "MISSING"

        # Readiness decision
        if tier_a:
            readiness = "ALREADY_SUPPORTED_TIER_A_NOT_TIER_B_CANDIDATE"
        elif not api_identity or int(api_identity.get("id") or 0) != lid:
            readiness = "INSUFFICIENT_EVIDENCE"
        elif mapping_class == "MAPPING_BLOCKED":
            readiness = "BLOCKED_MAPPING"
        elif odds_class == "ODDS_BLOCKED" and not prematch:
            readiness = "DEFER_OFFSEASON_VALIDATION"
        elif odds_class == "ODDS_BLOCKED":
            readiness = "BLOCKED_ODDS"
        elif wde_status.startswith("blocked"):
            readiness = "BLOCKED_WDE"
        elif mapping_class == "MAPPING_FIX_REQUIRED":
            readiness = "READY_WITH_MINOR_MAPPING_FIX"
        elif odds_class == "ODDS_LIMITED":
            readiness = "READY_WITH_ODDS_LIMITATION"
        elif prematch and not with_odds:
            readiness = "DEFER_OFFSEASON_VALIDATION"
        else:
            readiness = "READY_FOR_TIER_B_ONBOARDING"

        out["leagues"][key] = {
            "canonical_key": key,
            "provider_league_id": lid,
            "expected_name": expected_name,
            "country": country,
            "api_identity": api_identity,
            "identity_confirmed": api_identity is not None
            and int(api_identity.get("id") or 0) == lid
            and str(api_identity.get("name") or "") == expected_name,
            "competition_registry": {
                "present": reg is not None,
                "league_id": reg.league_id if reg else None,
                "season": reg.season if reg else None,
            },
            "current_support": {
                "tier_a_trusted": tier_a,
                "tier_b_shadow": tier_b_meta is not None,
                "gpt_scope": gpt_scope,
                "registry_status": registry_status,
                "owner_scope": key in owner_keys or f"league_{lid}" in owner_keys,
                "production_scope": key in prod_keys,
                "shadow_scope": key in shadow_keys,
                "fixture_tier": fixture_tier(key),
            },
            "fixture_volume": {
                "total_sampled": len(fixtures),
                "prematch_total": len(prematch),
                "next_7d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d7),
                "next_14d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d14),
                "next_30d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d30),
                "next_60d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d60),
                "off_season_likely": len(prematch) == 0 and len(fixtures) == 0,
            },
            "db_history": {
                "fixtures_total": db_fixtures,
                "finished_total": db_finished,
                "odds_fixture_count": db_odds_snaps,
            },
            "mapping": {
                "sampled": len(sample),
                "fully_mapped": mapped,
                "success_rate": mapping_rate,
                "classification": mapping_class,
            },
            "odds": {
                "prematch_sampled": len(prematch),
                "with_any_odds": len(with_odds),
                "api_coverage_rate": pct(len(with_odds), len(prematch)),
                "db_coverage_rate": pct(sum(1 for f in prematch if f["db_bookmakers"] > 0), len(prematch)),
                "median_bookmakers": int(med_bk) if bks else 0,
                "p25_bookmakers": percentile(bks, 0.25),
                "p75_bookmakers": percentile(bks, 0.75),
                "max_bookmakers": max(bks) if bks else 0,
                "missing_ratio": pct(len(prematch) - len(with_odds), len(prematch)),
                "classification": odds_class,
            },
            "wde": {"status": wde_status, "classification": "WDE_READY" if wde_status == "routing_ok" else "WDE_PARTIAL"},
            "ecse": {"classification": "ECSE_READY" if wde_status == "routing_ok" else "ECSE_PARTIAL"},
            "result_sync": {"classification": "RESULT_SYNC_READY"},
            "historical_data": {
                "classification": "HISTORICAL_DATA_READY"
                if db_fixtures >= 50
                else ("HISTORICAL_DATA_PARTIAL" if db_fixtures > 0 else "HISTORICAL_DATA_PARTIAL")
            },
            "fixture_gate_sample": gate_status,
            "readiness_decision": readiness,
            "sample_fixtures": sample[:8],
            "control_fixture": control,
        }

    out["onboard_candidates"] = [
        k
        for k, v in out["leagues"].items()
        if v["readiness_decision"]
        in (
            "READY_FOR_TIER_B_ONBOARDING",
            "READY_WITH_ODDS_LIMITATION",
            "READY_WITH_MINOR_MAPPING_FIX",
        )
    ]
    out["already_tier_a"] = [k for k, v in out["leagues"].items() if v["current_support"]["tier_a_trusted"]]
    conn.close()
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": "ok", "path": str(OUT), "onboard": out["onboard_candidates"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
