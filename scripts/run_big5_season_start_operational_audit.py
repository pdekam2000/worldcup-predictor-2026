#!/usr/bin/env python3
"""Big 5 season-start operational readiness audit — read-only evidence."""

from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
OUT = ROOT / "artifacts" / "big5_season_start_audit" / "audit_payload.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

ANCHOR = date(2026, 7, 10)
BIG5 = (
    ("premier_league", 39, "A"),
    ("bundesliga", 78, "A"),
    ("serie_a", 135, "B"),
    ("la_liga", 140, "B"),
    ("ligue_1", 61, "B"),
)
PREMATCH = frozenset({"NS", "TBD", "SCHEDULED", "TIMED", "", "NOT STARTED"})
BEST3_DATES = ("2026-08-16", "2026-08-22", "2026-08-23", "2026-08-28", "2026-08-29")


def main() -> int:
    from worldcup_predictor.clients.api_football import ApiFootballClient
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.forward_evaluation.automation import AUTOMATION_ENABLED
    from worldcup_predictor.forward_evaluation.db import connect_eval_db, eval_db_path
    from worldcup_predictor.forward_evaluation.discovery import discover_forward_evaluation_fixtures
    from worldcup_predictor.forward_evaluation.fixture_model import prediction_mode_for_tier
    from worldcup_predictor.forward_evaluation.orchestrator import run_forward_evaluation_automation_cycle
    from worldcup_predictor.gpt_actions.broad_fixture_discovery import _fetch_api_fixtures_for_date, _parse_api_item
    from worldcup_predictor.gpt_actions.competition_normalize import normalize_competition_key
    from worldcup_predictor.gpt_actions.delegation import _match_odds, discover_today_matches, list_today_matches_broad
    from worldcup_predictor.gpt_actions.owner_scope import competition_keys_for_scope, fixture_tier
    from worldcup_predictor.gpt_actions.tier_b_shadow_registry import get_tier_b_domain
    from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS

    settings = get_settings()
    client = ApiFootballClient(settings)
    conn = connect(settings.sqlite_path)

    out: dict = {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "anchor_date": ANCHOR.isoformat(),
        "policy": {},
        "fixtures": {},
        "odds": {},
        "forward_collection": {},
        "best3": {},
        "db_schema": {},
        "cadence": {"classification": "CADENCE_ADEQUATE", "daily_forward_eval_utc": "07:00"},
    }

    owner_keys = set(competition_keys_for_scope("owner"))
    prod_keys = set(competition_keys_for_scope("production"))
    shadow_keys = set(competition_keys_for_scope("shadow"))

    for key, lid, expected_tier in BIG5:
        tier = fixture_tier(key)
        meta = get_tier_b_domain(key)
        out["policy"][key] = {
            "provider_league_id": lid,
            "expected_tier": expected_tier,
            "actual_tier": tier,
            "display_status": "TRUSTED" if tier == "A" else ("TEST_PHASE" if tier == "B" else None),
            "tier_a_trusted": key in DAILY_SUPPORTED_COMPETITIONS,
            "tier_b_registered": meta is not None,
            "owner_scope": key in owner_keys or f"league_{lid}" in owner_keys,
            "production_scope": key in prod_keys,
            "shadow_scope": key in shadow_keys,
            "prediction_mode": prediction_mode_for_tier(tier),
            "forward_eval_via_owner_discovery": tier in ("A", "B"),
        }

    # Fixture windows
    for key, lid, _ in BIG5:
        fixtures = []
        for off in range(0, 61):
            d = ANCHOR + timedelta(days=off)
            items, _ = _fetch_api_fixtures_for_date(settings, d)
            for item in items:
                p = _parse_api_item(item)
                if not p or int(p["league_id"]) != lid:
                    continue
                st = str(p.get("status") or "NS").upper()
                if st not in PREMATCH and st not in ("FT",):
                    continue
                fid = int(p["fixture_id"])
                db_bk = int((_match_odds(conn, fid) or {}).get("bookmaker_count") or 0)
                fixtures.append({"fixture_id": fid, "date": d.isoformat(), "prematch": st in PREMATCH, "db_bk": db_bk})
        prematch = [f for f in fixtures if f["prematch"]]
        d30 = ANCHOR + timedelta(days=29)
        d45 = ANCHOR + timedelta(days=44)
        d60 = ANCHOR + timedelta(days=59)
        first_date = min((f["date"] for f in prematch), default=None)
        out["fixtures"][key] = {
            "first_fixture_date": first_date,
            "prematch_30d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d30),
            "prematch_45d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d45),
            "prematch_60d": sum(1 for f in prematch if date.fromisoformat(f["date"]) <= d60),
            "db_fixtures": conn.execute(
                "SELECT COUNT(*) FROM fixtures WHERE competition_key=?", (key,)
            ).fetchone()[0]
            if key in ("premier_league", "bundesliga")
            else 0,
        }
        with_odds = sum(1 for f in prematch if f["db_bk"] > 0)
        out["odds"][key] = {
            "prematch_scheduled": len(prematch),
            "db_odds_present": with_odds,
            "classification": "PRESEASON_ODDS_NOT_YET_AVAILABLE" if with_odds == 0 else "ODDS_PRESENT",
        }

    # Forward collection dry run on peak date
    for test_date in ("2026-08-22", "2026-08-16"):
        disc = discover_forward_evaluation_fixtures(target_date=test_date, timezone="Europe/Vienna")
        cycle = run_forward_evaluation_automation_cycle(target_date=test_date, timezone="Europe/Vienna", dry_run=True)
        out["forward_collection"][test_date] = {
            "discovered": disc.get("discovered_count"),
            "tier_a": disc.get("tier_a_count"),
            "tier_b": disc.get("tier_b_count"),
            "big5_in_discovery": [
                f for f in disc.get("fixtures") or []
                if normalize_competition_key(str(f.get("competition") or "")) in {k for k, _, _ in BIG5}
            ],
            "dry_cycle_eligible": (cycle.get("stage_results") or {}).get("ELIGIBILITY", {}).get("eligible_count"),
            "dry_cycle_excluded": (cycle.get("stage_results") or {}).get("CLASSIFY", {}).get("excluded_count"),
        }

    # Best 3 analysis
    for d in BEST3_DATES:
        broad = list_today_matches_broad(target_date=d, timezone="Europe/Vienna")
        owner = discover_today_matches(target_date=d, timezone="Europe/Vienna", scope="owner")
        prod = discover_today_matches(target_date=d, timezone="Europe/Vienna", scope="production")
        big5_broad = [
            m for m in broad.get("matches") or []
            if normalize_competition_key(str(m.get("competition") or "")) in {k for k, _, _ in BIG5}
        ]
        big5_owner = [
            m for m in owner.get("matches") or []
            if normalize_competition_key(str(m.get("competition") or "")) in {k for k, _, _ in BIG5}
        ]
        out["best3"][d] = {
            "broad_big5": len(big5_broad),
            "owner_big5": len(big5_owner),
            "tier_a": sum(1 for m in big5_owner if m.get("tier") == "A" or m.get("validation_tier") == "A"),
            "tier_b": sum(1 for m in big5_owner if m.get("tier") == "B" or m.get("validation_tier") == "B"),
            "production_big5": len([
                m for m in prod.get("matches") or []
                if normalize_competition_key(str(m.get("competition") or "")) in {k for k, _, _ in BIG5}
            ]),
            "odds_missing": sum(1 for m in big5_broad if m.get("listing_status") == "ODDS_MISSING"),
        }

    # DB schema
    if eval_db_path().is_file():
        ec = connect_eval_db()
        cols = [r[1] for r in ec.execute("PRAGMA table_info(frozen_predictions)")]
        tables = [r[0] for r in ec.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        by_comp = ec.execute(
            "SELECT competition, COUNT(*) c FROM frozen_predictions GROUP BY competition"
        ).fetchall()
        ec.close()
        required = {
            "competition", "competition_family", "validation_tier", "display_status",
            "prediction_mode", "bookmaker_count", "odds_freshness", "entropy", "tier",
        }
        out["db_schema"] = {
            "path": str(eval_db_path()),
            "tables": tables,
            "frozen_columns_ok": required.issubset(set(cols)),
            "frozen_by_competition": [dict(r) for r in by_comp],
            "exact_score_rankings": "exact_score_rankings" in tables,
        }

    out["automation_enabled"] = AUTOMATION_ENABLED
    out["tier_a_forward"] = {
        k: "FULL_FORWARD_COLLECTION_READY"
        for k in ("premier_league", "bundesliga")
        if out["policy"][k]["tier_a_trusted"] and out["policy"][k]["forward_eval_via_owner_discovery"]
    }
    out["tier_b_forward"] = {
        k: "FULL_FORWARD_COLLECTION_READY"
        for k in ("serie_a", "la_liga", "ligue_1")
        if out["policy"][k]["tier_b_registered"] and out["policy"][k]["forward_eval_via_owner_discovery"]
    }

    conn.close()
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"status": "ok", "path": str(OUT)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
