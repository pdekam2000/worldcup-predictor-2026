#!/usr/bin/env python3
"""Controlled 1 Lyga Tier B pilot validation — evidence collection (read-only safe)."""

from __future__ import annotations

import json
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
ART = ROOT / "artifacts" / "one_lyga_tier_b_pilot"
ART.mkdir(parents=True, exist_ok=True)

PROVIDER_LEAGUE_ID = 361
CANONICAL_KEY = "one_lyga"
PILOT_DATE = "2026-07-18"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def main() -> int:
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.database.repository import FootballIntelligenceRepository
    from worldcup_predictor.forward_evaluation.fixture_model import enrich_unified_fixture
    from worldcup_predictor.forward_evaluation.gates import classify_candidate
    from worldcup_predictor.gpt_actions.broad_fixture_discovery import (
        _fetch_api_fixtures_for_date,
        _parse_api_item,
        discover_broad_fixtures,
    )
    from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
    from worldcup_predictor.gpt_actions.delegation import _match_odds, discover_today_matches, list_today_matches_broad
    from worldcup_predictor.gpt_actions.owner_odds import OwnerOddsBudget, controlled_owner_odds_lookup
    from worldcup_predictor.gpt_actions.owner_scope import (
        competition_keys_for_scope,
        fixture_allowed_for_discovery,
        fixture_allowed_for_prediction,
        fixture_tier,
    )
    from worldcup_predictor.gpt_actions.tier_b_shadow_registry import TIER_B_SHADOW_DOMAINS, get_tier_b_domain
    from worldcup_predictor.gpt_actions.wde_runtime import prepare_daily_fixture_for_wde, register_tier_b_competition_runtime
    from worldcup_predictor.owner_daily.fixture_discovery import DailyFixture

    settings = get_settings()
    client = ApiFootballClient(settings)
    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)

    out: dict = {
        "generated_at": _utc_now(),
        "provider_league_id": PROVIDER_LEAGUE_ID,
        "canonical_key": CANONICAL_KEY,
        "pilot_date": PILOT_DATE,
    }

    # Part A — identity
    lr = client._safe_get("leagues", {"id": PROVIDER_LEAGUE_ID}, placeholder_factory=lambda: None, ttl_seconds=3600)
    league_identity = None
    if lr and lr.data:
        item = lr.data[0] if isinstance(lr.data, list) and lr.data else lr.data
        lg = item.get("league") or item
        league_identity = {
            "id": lg.get("id"),
            "name": lg.get("name"),
            "country": (item.get("country") or {}).get("name"),
            "type": lg.get("type"),
        }
    out["league_identity"] = league_identity
    out["identity_confirmed"] = (
        league_identity is not None
        and int(league_identity.get("id") or 0) == PROVIDER_LEAGUE_ID
        and str(league_identity.get("name") or "") == "1 Lyga"
        and str(league_identity.get("country") or "") == "Lithuania"
    )

    meta = get_tier_b_domain(CANONICAL_KEY)
    out["registry_entry"] = meta

    # Fixture scan
    prematch = []
    for off in range(0, 35):
        d = date(2026, 7, 10) + timedelta(days=off)
        items, _ = _fetch_api_fixtures_for_date(settings, d)
        for item in items:
            p = _parse_api_item(item)
            if not p or int(p["league_id"]) != PROVIDER_LEAGUE_ID:
                continue
            st = str(p.get("status") or "NS").upper()
            if st not in ("NS", "TBD", "SCHEDULED", "TIMED", ""):
                continue
            teams = item.get("teams") or {}
            home_t = teams.get("home") or {}
            away_t = teams.get("away") or {}
            prematch.append(
                {
                    "fixture_id": p["fixture_id"],
                    "date": d.isoformat(),
                    "home_team": p["home_team"],
                    "away_team": p["away_team"],
                    "home_team_id": home_t.get("id"),
                    "away_team_id": away_t.get("id"),
                    "kickoff_utc": p["kickoff_utc"],
                    "competition_key": normalize_competition_key(f"league_{PROVIDER_LEAGUE_ID}"),
                }
            )

    anchor = date(2026, 7, 10)
    d7 = anchor + timedelta(days=6)
    d14 = anchor + timedelta(days=13)
    d30 = anchor + timedelta(days=29)
    out["fixture_volume"] = {
        "anchor": sum(1 for f in prematch if f["date"] == anchor.isoformat()),
        "next_7d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d7),
        "next_14d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d14),
        "next_30d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d30),
        "total_prematch_sampled": len(prematch),
    }

    # Team mapping
    team_rows = []
    for f in prematch[:12]:
        hid, aid = f.get("home_team_id"), f.get("away_team_id")
        status = "fully_mapped" if hid and aid and f.get("home_team") and f.get("away_team") else "partial"
        if not hid or not aid:
            status = "unresolved"
        team_rows.append({**f, "mapping_status": status})
    mapped = sum(1 for t in team_rows if t["mapping_status"] == "fully_mapped")
    out["team_mapping"] = {
        "fixtures_sampled": len(team_rows),
        "fully_mapped": mapped,
        "partial": sum(1 for t in team_rows if t["mapping_status"] == "partial"),
        "unresolved": sum(1 for t in team_rows if t["mapping_status"] == "unresolved"),
        "success_rate": round(mapped / len(team_rows), 4) if team_rows else 0.0,
        "samples": team_rows,
    }

    # Broad listing pilot date
    broad = discover_broad_fixtures(
        target_date=PILOT_DATE, timezone="Europe/Vienna", settings=settings, sync_prediction_candidates=True
    )
    one_lyga_broad = [
        m
        for m in broad.get("matches") or []
        if normalize_competition_key(str(m.get("competition") or m.get("competition_raw") or "")) == CANONICAL_KEY
        or str(m.get("competition_raw") or "") == f"league_{PROVIDER_LEAGUE_ID}"
    ]
    out["broad_listing"] = {
        "date": PILOT_DATE,
        "one_lyga_count": len(one_lyga_broad),
        "samples": one_lyga_broad[:5],
    }

    # Scope checks
    owner_keys = competition_keys_for_scope("owner")
    prod_keys = competition_keys_for_scope("production")
    shadow_keys = competition_keys_for_scope("shadow")
    out["scope"] = {
        "owner_includes_canonical": CANONICAL_KEY in owner_keys,
        "owner_includes_league_alias": f"league_{PROVIDER_LEAGUE_ID}" in owner_keys,
        "production_excludes_canonical": CANONICAL_KEY not in prod_keys,
        "production_excludes_league_alias": f"league_{PROVIDER_LEAGUE_ID}" not in prod_keys,
        "shadow_includes_canonical": CANONICAL_KEY in shadow_keys,
    }

    discover_owner = discover_today_matches(target_date=PILOT_DATE, timezone="Europe/Vienna", scope="owner")
    discover_prod = discover_today_matches(target_date=PILOT_DATE, timezone="Europe/Vienna", scope="production")
    discover_shadow = discover_today_matches(target_date=PILOT_DATE, timezone="Europe/Vienna", scope="shadow")
    out["discover"] = {
        "owner_count": discover_owner.get("count"),
        "production_count": discover_prod.get("count"),
        "shadow_count": discover_shadow.get("count"),
        "owner_one_lyga": [
            m for m in discover_owner.get("matches") or [] if m.get("competition") == CANONICAL_KEY or m.get("tier") == "B" and f"league_{PROVIDER_LEAGUE_ID}" in str(m.get("competition_raw") or "")
        ],
    }

    # Controlled fixture — first on pilot date
    control = next((f for f in prematch if f["date"] == PILOT_DATE), prematch[0] if prematch else None)
    out["controlled_fixture"] = control

    wde_result = None
    ecse_result = None
    odds_gate = None
    if control:
        fid = int(control["fixture_id"])
        comp = CANONICAL_KEY
        daily = DailyFixture(
            fixture_id=fid,
            provider_fixture_id=fid,
            competition_key=comp,
            home_team=control["home_team"],
            away_team=control["away_team"],
            kickoff_utc=control["kickoff_utc"],
            status="NS",
            season=2026,
            coverage_sources=["api_football"],
            provider_ids={"api_football": fid},
        )
        register_tier_b_competition_runtime(CANONICAL_KEY, repo=repo, season=2026)
        prepared = prepare_daily_fixture_for_wde(daily, repo=repo, settings=settings)
        wde_result = {
            "competition_before": daily.competition_key,
            "competition_after": prepared.competition_key,
            "normalization_ok": prepared.competition_key == CANONICAL_KEY,
            "tier": fixture_tier(prepared.competition_key),
        }

        budget = OwnerOddsBudget()
        odds_meta = controlled_owner_odds_lookup(
            prepared, tier="B", settings=settings, budget=budget, allow_provider=True
        )
        db_odds = _match_odds(conn, fid)
        odds_gate = {**odds_meta, "db_bookmaker_count": db_odds.get("bookmaker_count")}

        unified = enrich_unified_fixture(
            fixture_id=fid,
            home_team=control["home_team"],
            away_team=control["away_team"],
            competition_key=comp,
            kickoff_utc=control["kickoff_utc"],
            status="NS",
            scope="owner",
            odds_available=bool(odds_meta.get("bookmaker_count")),
        )
        gate_status, gate_detail = classify_candidate(conn, fixture={**control, **unified, "competition": comp, "competition_raw": f"league_{PROVIDER_LEAGUE_ID}", "tier": "B"}, settings=settings)
        out["fixture_gate"] = {"status": gate_status, "detail": gate_detail}

        # WDE dry run only if odds found
        if odds_meta.get("bookmaker_count", 0) > 0:
            try:
                from worldcup_predictor.owner_daily.predictions import run_daily_wde

                wde_payload = run_daily_wde(prepared, repo=repo, settings=settings)
                wde_result["executed"] = True
                wde_result["decision"] = wde_payload.get("prediction") or wde_payload.get("decision")
                wde_result["ft_marginal"] = wde_payload.get("ft_marginal_direction")
                wde_result["hda"] = [
                    wde_payload.get("home_probability"),
                    wde_payload.get("draw_probability"),
                    wde_payload.get("away_probability"),
                ]
                wde_result["confidence"] = wde_payload.get("confidence")
                wde_result["btts"] = wde_payload.get("btts_prediction")
                wde_result["ou25"] = wde_payload.get("over_under_25_prediction")
            except Exception as exc:
                wde_result["executed"] = False
                wde_result["error"] = str(exc)
        else:
            wde_result["executed"] = False
            wde_result["skip_reason"] = "odds_gate_not_passed_no_formula_test_without_fake_odds"

        # ECSE via MCP only if odds
        if odds_meta.get("bookmaker_count", 0) > 0:
            try:
                from worldcup_predictor.owner_daily.predictions import run_daily_ecse

                ecse_payload = run_daily_ecse(prepared, repo=repo, settings=settings)
                tops = (ecse_payload.get("top_10_scorelines") or ecse_payload.get("top_5_scores") or [])[:5]
                ecse_result = {
                    "executed": True,
                    "top1": tops[0] if len(tops) > 0 else None,
                    "top2": tops[1] if len(tops) > 1 else None,
                    "top3": tops[2] if len(tops) > 2 else None,
                    "top4": tops[3] if len(tops) > 3 else None,
                    "top5": tops[4] if len(tops) > 4 else None,
                    "top3_mass": ecse_payload.get("top3_mass"),
                    "top5_mass": ecse_payload.get("top5_mass"),
                    "entropy": ecse_payload.get("entropy"),
                }
            except Exception as exc:
                ecse_result = {"executed": False, "error": str(exc)}
        else:
            ecse_result = {"executed": False, "skip_reason": "odds_gate_not_passed"}

    out["wde"] = wde_result
    out["ecse"] = ecse_result
    out["odds"] = odds_gate

    new_ids = {int(m["provider_league_id"]) for m in TIER_B_SHADOW_DOMAINS.values()}
    out["tier_b_domain_count"] = len(TIER_B_SHADOW_DOMAINS)
    out["only_one_lyga_added"] = (
        PROVIDER_LEAGUE_ID in new_ids
        and 165 not in new_ids
        and 1087 not in new_ids
        and 329 not in new_ids
    )

    conn.close()
    path = ART / "pilot_evidence.json"
    path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": "ok", "path": str(path), "identity": out["identity_confirmed"], "gate": out.get("fixture_gate", {}).get("status")}))
    return 0 if out["identity_confirmed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
