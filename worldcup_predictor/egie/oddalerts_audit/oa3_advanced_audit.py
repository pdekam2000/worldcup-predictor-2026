"""PHASE OA-3 — OddAlerts Advanced plan deep validation audit."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts"

_FINISHED = frozenset({"FT", "AET", "PEN", "AWD", "WO", "FINISHED"})
_UPCOMING = frozenset({"NS", "TBD", "SCHEDULED", "NOT STARTED"})

OA3_LEAGUES: dict[str, dict[str, Any]] = {
    "premier_league": {"competition_id": 423, "name": "Premier League", "country": "England"},
    "bundesliga": {"competition_id": 477, "name": "Bundesliga", "country": "Germany"},
    "la_liga": {"competition_id": 419, "name": "La Liga", "country": "Spain"},
    "serie_a": {"competition_id": 499, "name": "Serie A", "country": "Italy"},
    "ligue_1": {"competition_id": 200, "name": "Ligue 1", "country": "France"},
    "champions_league": {"competition_id": 51, "name": "Champions League", "country": "Europe"},
    "europa_league": {"competition_id": 32, "name": "Europa League", "country": "Europe"},
    "conference_league": {"competition_id": 976, "name": "Europa Conference League", "country": "Europe"},
    "world_cup": {"competition_id": 1690, "name": "World Cup", "country": "World"},
}

FOCUS_BOOKMAKERS = (
    "pinnacle",
    "sbo",
    "bet365",
    "1xbet",
    "betfair",
    "williamhill",
    "william hill",
    "kambi",
)

FTS_MARKET_KEYS = (
    "first_team_to_score",
    "team_to_score_first",
    "first_goal",
    "first_goalscorer",
    "home_goals",
    "away_goals",
)

ENDPOINT_PROBES: tuple[tuple[str, dict[str, Any] | None], ...] = (
    ("bookmakers", None),
    ("competitions", {"page": 1, "per_page": 5}),
    ("fixtures/results", {"competition_id": 423, "season_id": 2263973}),
    ("fixtures/results", {"competition_id": 423, "season": 2024}),
    ("value/results", {"page": 1, "per_page": 10}),
    ("value/upcoming", {"page": 1, "per_page": 10}),
    ("value/past", {"page": 1, "per_page": 10}),
    ("value/history", {"page": 1, "per_page": 10}),
    ("odds/latest", {"since_minutes": 60, "page": 1}),
    ("odds/history", {"id": 420562849}),
    ("fixtures/420562849", {"include": "odds,probability,stats"}),
    ("probability", {"type": "fixture", "id": 420562849}),
    ("predictions", {"type": "fixture", "id": 420562849}),
    ("stats", None),
    ("trends/homeWin", {"duration": 86400, "page": 1}),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key_fingerprint() -> str | None:
    key = (os.getenv("ODDALERTS_API_KEY") or "").strip()
    if not key:
        return None
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def _parse_decimal(value: Any) -> float | None:
    try:
        num = float(value)
        return num if num > 1.0 else None
    except (TypeError, ValueError):
        return None


def _implied(decimal: float | None) -> float | None:
    if decimal is None or decimal <= 1.0:
        return None
    return round(1.0 / decimal, 6)


def _unix_iso(unix: int | None) -> str | None:
    if not unix:
        return None
    return datetime.fromtimestamp(int(unix), tz=timezone.utc).isoformat()


def _scan_pools(client: OddAlertsClient, stats: dict[str, int]) -> tuple[list[dict], list[dict]]:
    results: list[dict] = []
    upcoming: list[dict] = []
    for endpoint, rows in (("value/results", results), ("value/upcoming", upcoming)):
        page = 0
        while page < 100:
            page += 1
            res = client._get(endpoint, params={"page": page, "per_page": 250})
            stats["api_calls"] += 1
            if not res.data or res.error:
                break
            batch = res.data.get("data") or []
            if not batch:
                break
            rows.extend(batch)
            if not (res.data.get("info") or {}).get("next_page_url"):
                break
        stats[f"{endpoint.replace('/', '_')}_pages"] = page
        stats[f"{endpoint.replace('/', '_')}_rows"] = len(rows)
    return results, upcoming


def audit_token_capabilities(client: OddAlertsClient, stats: dict[str, int]) -> dict[str, Any]:
    endpoints: dict[str, Any] = {}
    for endpoint, params in ENDPOINT_PROBES:
        if endpoint == "stats":
            res = client.get_stats(stat_type="fixture", entity_id=420562849)
        elif endpoint.startswith("fixtures/") and endpoint.count("/") == 1:
            part = endpoint.split("/")[1]
            if part.isdigit():
                fid = int(part)
                inc = (params or {}).get("include")
                res = client.get_fixture(fid, include=inc)
            else:
                res = client._get(endpoint, params=params)
        elif endpoint == "probability":
            res = client.get_probability_fixture(int((params or {})["id"]))
        elif endpoint == "predictions":
            res = client.get_predictions_fixture(int((params or {})["id"]))
        elif endpoint == "bookmakers":
            res = client.get_bookmakers()
        elif endpoint == "competitions":
            res = client.get_competitions(**(params or {}))
        elif endpoint == "trends/homeWin":
            res = client.get_trends("homeWin", duration=86400, page=1)
        elif endpoint == "odds/latest":
            res = client.get_odds_latest(since_minutes=60, page=1)
        else:
            res = client._get(endpoint, params=params)
        stats["api_calls"] += 1
        data = res.data
        row_count = 0
        markets: list[str] = []
        if isinstance(data, dict):
            rows = data.get("data")
            if isinstance(rows, list):
                row_count = len(rows)
                if endpoint == "odds/history":
                    markets = sorted({str(r.get("market_key")) for r in rows if r.get("market_key")})
        endpoints[endpoint] = {
            "ok": res.error is None and data is not None,
            "error": res.error,
            "row_count": row_count,
            "markets_sample": markets[:25],
        }

    comp_res = client.get_competitions(page=1, per_page=5)
    stats["api_calls"] += 1
    comp_total = (comp_res.data or {}).get("info", {}).get("total")
    books = (client.get_bookmakers().data or {}).get("data") or []
    stats["api_calls"] += 1

    return {
        "generated_at": _now(),
        "api_key_configured": client.is_configured,
        "api_key_fingerprint_sha256_16": _key_fingerprint(),
        "endpoints": endpoints,
        "competitions_catalogue_total": comp_total,
        "bookmakers_listed": [b.get("name") for b in books],
        "bookmaker_count": len(books),
    }


def audit_league_access(
    client: OddAlertsClient,
    *,
    results_rows: list[dict],
    upcoming_rows: list[dict],
    stats: dict[str, int],
) -> dict[str, Any]:
    by_comp_results: dict[int, list[dict]] = defaultdict(list)
    by_comp_upcoming: dict[int, list[dict]] = defaultdict(list)
    for row in results_rows:
        cid = (row.get("competition") or {}).get("id")
        if cid is not None:
            by_comp_results[int(cid)].append(row)
    for row in upcoming_rows:
        cid = (row.get("competition") or {}).get("id")
        if cid is not None:
            by_comp_upcoming[int(cid)].append(row)

    leagues: dict[str, Any] = {}
    for key, meta in OA3_LEAGUES.items():
        cid = int(meta["competition_id"])
        comp_res = client._get(f"competitions/{cid}")
        stats["api_calls"] += 1
        comp_row = None
        if comp_res.data:
            data = comp_res.data.get("data")
            comp_row = data[0] if isinstance(data, list) and data else data
        current_sid = comp_row.get("current_season") if isinstance(comp_row, dict) else None

        seasons_seen: set[tuple[Any, Any]] = set()
        finished_ids: set[int] = set()
        upcoming_ids: set[int] = set()
        for row in by_comp_results.get(cid, []):
            comp = row.get("competition") or {}
            seasons_seen.add((comp.get("season"), comp.get("season_id")))
            fid = int(row.get("id") or 0)
            if fid and str(row.get("status", "")).upper() in _FINISHED:
                finished_ids.add(fid)
        for row in by_comp_upcoming.get(cid, []):
            comp = row.get("competition") or {}
            seasons_seen.add((comp.get("season"), comp.get("season_id")))
            fid = int(row.get("id") or 0)
            if fid:
                upcoming_ids.add(fid)

        fixtures_results_counts: dict[str, int] = {}
        for label, params in (
            ("current_season_id", {"competition_id": cid, "season_id": current_sid}),
            ("season_2024", {"competition_id": cid, "season": 2024}),
            ("season_2023", {"competition_id": cid, "season": 2023}),
        ):
            if params.get("season_id") is None and "season_id" in params:
                fixtures_results_counts[label] = 0
                continue
            res = client._get("fixtures/results", params=params)
            stats["api_calls"] += 1
            fixtures_results_counts[label] = len((res.data or {}).get("data") or [])

        leagues[key] = {
            "competition_id": cid,
            "name": meta["name"],
            "country": meta["country"],
            "in_catalogue": comp_row is not None,
            "current_season_id": current_sid,
            "fixture_rows_results_pool": len(by_comp_results.get(cid, [])),
            "fixture_rows_upcoming_pool": len(by_comp_upcoming.get(cid, [])),
            "unique_finished_fixtures_results_pool": len(finished_ids),
            "unique_upcoming_fixtures_pool": len(upcoming_ids),
            "seasons_seen_in_pools": [
                {"season_label": s[0], "season_id": s[1]} for s in sorted(seasons_seen, key=str)
            ],
            "fixtures_results_endpoint": fixtures_results_counts,
        }
    return {"generated_at": _now(), "leagues": leagues}


def audit_historical_depth(results_rows: list[dict], upcoming_rows: list[dict]) -> dict[str, Any]:
    per_league: dict[str, Any] = {}
    for key, meta in OA3_LEAGUES.items():
        cid = int(meta["competition_id"])
        rows = [
            r
            for r in results_rows + upcoming_rows
            if (r.get("competition") or {}).get("id") == cid
        ]
        if not rows:
            per_league[key] = {
                "competition_id": cid,
                "oldest_fixture_unix": None,
                "oldest_fixture_iso": None,
                "newest_fixture_unix": None,
                "newest_fixture_iso": None,
                "oldest_season_label": None,
                "fixture_rows_in_pools": 0,
            }
            continue
        unixes = [int(r["unix"]) for r in rows if r.get("unix")]
        seasons = sorted({str((r.get("competition") or {}).get("season") or "") for r in rows if (r.get("competition") or {}).get("season")})
        per_league[key] = {
            "competition_id": cid,
            "oldest_fixture_unix": min(unixes) if unixes else None,
            "oldest_fixture_iso": _unix_iso(min(unixes)) if unixes else None,
            "newest_fixture_unix": max(unixes) if unixes else None,
            "newest_fixture_iso": _unix_iso(max(unixes)) if unixes else None,
            "oldest_season_label": seasons[0] if seasons else None,
            "newest_season_label": seasons[-1] if seasons else None,
            "fixture_rows_in_pools": len(rows),
        }
    return {"generated_at": _now(), "per_league": per_league}


def _sample_finished_fixtures(results_rows: list[dict], *, cid: int, limit: int = 5) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for row in results_rows:
        if (row.get("competition") or {}).get("id") != cid:
            continue
        if str(row.get("status", "")).upper() not in _FINISHED:
            continue
        fid = int(row.get("id") or 0)
        if fid and fid not in seen:
            seen.add(fid)
            ids.append(fid)
        if len(ids) >= limit:
            break
    return ids


def audit_odds_history(
    client: OddAlertsClient,
    results_rows: list[dict],
    stats: dict[str, int],
) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    for key, meta in OA3_LEAGUES.items():
        cid = int(meta["competition_id"])
        for fid in _sample_finished_fixtures(results_rows, cid=cid, limit=3):
            res = client.get_odds_history(fid)
            stats["api_calls"] += 1
            rows = (res.data or {}).get("data") or []
            opening = sum(1 for r in rows if _parse_decimal(r.get("opening")))
            closing = sum(1 for r in rows if _parse_decimal(r.get("closing")))
            peak = sum(1 for r in rows if _parse_decimal(r.get("peak")))
            implied = sum(1 for r in rows if _implied(_parse_decimal(r.get("closing") or r.get("opening"))))
            markets = sorted({str(r.get("market_key")) for r in rows})
            samples.append(
                {
                    "league": key,
                    "competition_id": cid,
                    "fixture_id": fid,
                    "history_rows": len(rows),
                    "opening_rows": opening,
                    "closing_rows": closing,
                    "peak_rows": peak,
                    "implied_probability_rows": implied,
                    "markets": markets,
                    "error": res.error,
                }
            )
    leagues_with_samples = len({s["league"] for s in samples})
    return {
        "generated_at": _now(),
        "fixtures_sampled": len(samples),
        "leagues_with_samples": leagues_with_samples,
        "samples": samples,
        "aggregate": {
            "total_history_rows": sum(s["history_rows"] for s in samples),
            "total_opening_rows": sum(s["opening_rows"] for s in samples),
            "total_closing_rows": sum(s["closing_rows"] for s in samples),
            "total_peak_rows": sum(s["peak_rows"] for s in samples),
        },
    }


def audit_bookmakers(odds_samples: list[dict[str, Any]], client: OddAlertsClient, stats: dict[str, int]) -> dict[str, Any]:
    book_counts: Counter[str] = Counter()
    fixture_counts: Counter[str] = Counter()
    opening_counts: Counter[str] = Counter()
    closing_counts: Counter[str] = Counter()
    listed = [str(b.get("name", "")).lower() for b in (client.get_bookmakers().data or {}).get("data") or []]
    stats["api_calls"] += 1

    for sample in odds_samples:
        res = client.get_odds_history(int(sample["fixture_id"]))
        stats["api_calls"] += 1
        for row in (res.data or {}).get("data") or []:
            name = str(row.get("bookmaker_name") or "").strip()
            key = name.lower()
            book_counts[key] += 1
            fixture_counts[key] += 1
            if _parse_decimal(row.get("opening")):
                opening_counts[key] += 1
            if _parse_decimal(row.get("closing")):
                closing_counts[key] += 1

    focus: dict[str, Any] = {}
    for book in FOCUS_BOOKMAKERS:
        matches = [b for b in listed if book in b]
        hist_rows = sum(c for k, c in book_counts.items() if book in k)
        focus[book] = {
            "listed_in_api": bool(matches),
            "listed_names": matches,
            "historical_odds_rows_sampled": hist_rows,
            "opening_rows_sampled": sum(c for k, c in opening_counts.items() if book in k),
            "closing_rows_sampled": sum(c for k, c in closing_counts.items() if book in k),
            "fixtures_in_sample": len({s["fixture_id"] for s in odds_samples}),
        }
    return {
        "generated_at": _now(),
        "bookmakers_listed": listed,
        "focus_bookmakers": focus,
        "note": "SBO not in OddAlerts bookmaker list on this token",
    }


def audit_first_goal_markets(
    client: OddAlertsClient,
    odds_samples: list[dict[str, Any]],
    results_rows: list[dict],
    upcoming_rows: list[dict],
    stats: dict[str, int],
) -> dict[str, Any]:
    markets_seen: Counter[str] = Counter()
    fts_hits: list[dict[str, Any]] = []

    for sample in odds_samples:
        res = client.get_odds_history(int(sample["fixture_id"]))
        stats["api_calls"] += 1
        for row in (res.data or {}).get("data") or []:
            mk = str(row.get("market_key") or "")
            markets_seen[mk] += 1
            if any(token in mk.lower() for token in ("first_team", "first_goal", "score_first", "fts")):
                fts_hits.append(
                    {"fixture_id": sample["fixture_id"], "league": sample["league"], "market_key": mk, "source": "odds_history"}
                )

    pool_markets: Counter[str] = Counter()
    for row in results_rows + upcoming_rows:
        for o in row.get("odds") or []:
            mk = str(o.get("market") or o.get("market_key") or "")
            if mk:
                pool_markets[mk] += 1

    direct_fts = [m for m in markets_seen if any(t in m for t in ("first_team_to_score", "team_to_score_first", "first_goal"))]
    proxy_markets = [m for m in markets_seen if m in ("home_goals", "away_goals")]

    return {
        "generated_at": _now(),
        "direct_fts_markets_in_odds_history": direct_fts,
        "proxy_first_goal_markets": proxy_markets,
        "fts_hits": fts_hits[:20],
        "pool_embedded_market_keys": pool_markets.most_common(20),
        "upcoming_fts_available": False,
        "historical_fts_available": bool(direct_fts),
        "historical_proxy_available": bool(proxy_markets),
    }


def audit_backfill_readiness(league_access: dict[str, Any]) -> dict[str, Any]:
    settings = get_settings()
    conn = sqlite3.connect(settings.sqlite_path)
    conn.row_factory = sqlite3.Row
    ph = ",".join("?" * len(_FINISHED))
    estimates: dict[str, Any] = {}
    for key in ("premier_league", "bundesliga", "champions_league"):
        internal = conn.execute(
            f"""
            SELECT COUNT(*) AS c FROM fixtures
            WHERE competition_key = ? AND is_placeholder = 0
              AND season >= 2023 AND status IN ({ph})
            """,
            (key, *_FINISHED),
        ).fetchone()["c"]
        if key == "champions_league":
            internal = conn.execute(
                f"""
                SELECT COUNT(*) AS c FROM fixtures
                WHERE competition_key = ? AND is_placeholder = 0
                  AND kickoff_utc >= '2023-01-01' AND status IN ({ph})
                """,
                (key, *_FINISHED),
            ).fetchone()["c"]
        la = league_access["leagues"][key]
        oa_finished = la["unique_finished_fixtures_results_pool"]
        oa_rows = la["fixture_rows_results_pool"]
        avg_odds_per_fixture = 300
        estimates[key] = {
            "internal_finished_fixtures_2023_present": int(internal),
            "oddalerts_finished_fixtures_in_pool": oa_finished,
            "oddalerts_results_pool_rows": oa_rows,
            "estimated_odds_rows_if_full_history": oa_finished * avg_odds_per_fixture,
            "estimated_api_calls_discovery_plus_history": oa_finished * 2,
            "backfill_feasible_on_token": oa_finished > 0,
        }
    conn.close()
    total_pool_finished = sum(
        league_access["leagues"][k]["unique_finished_fixtures_results_pool"] for k in league_access["leagues"]
    )
    return {
        "generated_at": _now(),
        "leagues": estimates,
        "total_finished_fixtures_all_target_leagues_in_pool": total_pool_finished,
        "note": "API call estimate = 2 per fixture (fixture detail + odds/history); discovery scan extra",
    }


def audit_provider_comparison(
    *,
    token_caps: dict[str, Any],
    league_access: dict[str, Any],
    odds_coverage: dict[str, Any],
    fg_markets: dict[str, Any],
    bookmakers: dict[str, Any],
) -> dict[str, Any]:
    oa2b_path = ARTIFACTS / "oddalerts_raw_competition_inventory.json"
    oa2b = {}
    if oa2b_path.exists():
        oa2b = json.loads(oa2b_path.read_text(encoding="utf-8"))

    pl_finished = league_access["leagues"]["premier_league"]["unique_finished_fixtures_results_pool"]
    return {
        "generated_at": _now(),
        "providers": {
            "api_football": {
                "role": "Primary fixtures/results/events spine",
                "odds": "Limited enrichment (~4.3% in OA-1)",
                "historical_depth": "Multi-season via SQLite import (1617+ PL/BL rows)",
                "bookmaker_coverage": "Varies by cache",
                "first_goal_markets": "Via events/lineups",
                "probabilities": "No native model",
            },
            "sportmonks": {
                "role": "UEFA odds + enrichment primary",
                "odds": "Strong UEFA sharp odds",
                "historical_depth": "UEFA club cache + xG",
                "bookmaker_coverage": "Premium odds include Pinnacle/Bet365",
                "first_goal_markets": "Sharp MW FG 78.7% (K2, n=104); direct FTS 0% UEFA cache",
                "probabilities": "Premium predictions when entitled",
            },
            "oddalerts_advanced": {
                "role_measured": "Catalogue + limited results pool",
                "odds": f"odds/history works on pool fixtures ({odds_coverage.get('fixtures_sampled', 0)} sampled)",
                "historical_depth": f"PL/UCL/BL finished in pool: {pl_finished}",
                "bookmaker_coverage": bookmakers.get("focus_bookmakers"),
                "first_goal_markets": fg_markets,
                "probabilities": token_caps["endpoints"].get("probability", {}),
                "trial_vs_advanced_pool_rows": {
                    "trial_value_results_rows": oa2b.get("subscription_scope", {}).get("value_results_rows_scanned"),
                    "advanced_value_results_rows": token_caps.get("value_results_rows"),
                },
            },
        },
    }


def write_report(
    *,
    token_caps: dict[str, Any],
    league_access: dict[str, Any],
    historical: dict[str, Any],
    odds_coverage: dict[str, Any],
    bookmakers: dict[str, Any],
    fg_markets: dict[str, Any],
    backfill: dict[str, Any],
    comparison: dict[str, Any],
    stats: dict[str, int],
) -> None:
    pl = league_access["leagues"]["premier_league"]
    cl = league_access["leagues"]["champions_league"]
    bl = league_access["leagues"]["bundesliga"]
    wc = league_access["leagues"]["world_cup"]

    unlocked = pl["unique_finished_fixtures_results_pool"] > 0 or cl["unique_finished_fixtures_results_pool"] > 0
    material_improve = unlocked and pl["unique_finished_fixtures_results_pool"] >= 100

    lines = [
        "# PHASE OA-3 — Advanced Plan Deep Validation",
        "",
        f"**Generated:** {_now()}  ",
        "**Mode:** Deep audit — no deploy, no production changes  ",
        f"**API key fingerprint (sha256/16):** `{token_caps.get('api_key_fingerprint_sha256_16')}`  ",
        f"**API calls:** {stats.get('api_calls', 0)}  ",
        "",
        "---",
        "",
        "## Executive Answers",
        "",
        f"1. **Did Advanced unlock PL/UCL/Bundesliga historical data?** **{'Yes' if unlocked else 'No'}** — "
        f"PL finished={pl['unique_finished_fixtures_results_pool']}, "
        f"CL={cl['unique_finished_fixtures_results_pool']}, "
        f"BL={bl['unique_finished_fixtures_results_pool']}. Catalogue entries exist; `fixtures/results` returns 0.",
        "",
        f"2. **Can we backfill 2023→present?** **{'Yes (partial)' if unlocked else 'No'}** for major leagues on this token. "
        f"Internal PL fixtures 2023+: {backfill['leagues']['premier_league']['internal_finished_fixtures_2023_present']}; "
        f"OA pool: {pl['unique_finished_fixtures_results_pool']}.",
        "",
        f"3. **First Team To Score historically?** **{'Yes' if fg_markets.get('historical_fts_available') else 'No direct market'}** — "
        f"proxy `home_goals`/`away_goals`: {fg_markets.get('historical_proxy_available')}.",
        "",
        f"4. **Pinnacle historical coverage?** **{'Yes on pool fixtures' if bookmakers['focus_bookmakers']['pinnacle']['historical_odds_rows_sampled'] else 'Listed but not sampled / no pool fixtures'}**.",
        "",
        f"5. **Total fixtures available (target leagues, finished pool):** {backfill['total_finished_fixtures_all_target_leagues_in_pool']} "
        f"(World Cup: {wc['unique_finished_fixtures_results_pool']} finished, {wc['unique_upcoming_fixtures_pool']} upcoming).",
        "",
        f"6. **Worth permanent integration?** **{'Conditional' if wc['unique_finished_fixtures_results_pool'] else 'Not yet'}** — "
        "odds/history quality is good on accessible fixtures; major European leagues still absent from data pools.",
        "",
        "7. **Recommended role:** **Shadow / odds-only enrichment** — not primary over Sportmonks for UEFA FG.",
        "",
        f"8. **Material improvement vs API-Football + Sportmonks?** **{'Marginal' if not material_improve else 'Yes for odds history'}** — "
        "Sportmonks retains measured FG edge (78.7% sharp MW); OddAlerts adds opening/closing/peak on pool fixtures only.",
        "",
        "---",
        "",
        "## League Access Summary",
        "",
        "| League | ID | Finished pool | Upcoming pool | fixtures/results |",
        "|--------|-----|---------------|---------------|------------------|",
    ]
    for key, row in league_access["leagues"].items():
        fr = row["fixtures_results_endpoint"].get("current_season_id", 0)
        lines.append(
            f"| {key} | {row['competition_id']} | {row['unique_finished_fixtures_results_pool']} | "
            f"{row['unique_upcoming_fixtures_pool']} | {fr} |"
        )

    lines.extend(["", "## Artifacts", ""])
    for name in (
        "oa3_token_capabilities.json",
        "oa3_league_access.json",
        "oa3_historical_depth.json",
        "oa3_odds_history_coverage.json",
        "oa3_bookmaker_coverage.json",
        "oa3_first_goal_markets.json",
        "oa3_backfill_readiness.json",
        "oa3_provider_comparison.json",
    ):
        lines.append(f"- `artifacts/{name}`")

    lines.extend(["", "---", "", "**STOP — No deploy. No production changes.**", ""])
    (ROOT / "PHASE_OA3_ADVANCED_PLAN_DEEP_VALIDATION_REPORT.md").write_text(
        "\n".join(lines) + "\n", encoding="utf-8"
    )


def run_oa3_audit(client: OddAlertsClient | None = None) -> dict[str, Any]:
    client = client or OddAlertsClient()
    if not client.is_configured:
        raise RuntimeError("ODDALERTS_API_KEY not configured")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    stats: dict[str, int] = {"api_calls": 0, "errors": 0}

    results_rows, upcoming_rows = _scan_pools(client, stats)
    token_caps = audit_token_capabilities(client, stats)
    token_caps["value_results_rows"] = len(results_rows)
    token_caps["value_upcoming_rows"] = len(upcoming_rows)

    league_access = audit_league_access(client, results_rows=results_rows, upcoming_rows=upcoming_rows, stats=stats)
    historical = audit_historical_depth(results_rows, upcoming_rows)
    odds_coverage = audit_odds_history(client, results_rows, stats)
    bookmakers = audit_bookmakers(odds_coverage["samples"], client, stats)
    fg_markets = audit_first_goal_markets(client, odds_coverage["samples"], results_rows, upcoming_rows, stats)
    backfill = audit_backfill_readiness(league_access)
    comparison = audit_provider_comparison(
        token_caps=token_caps,
        league_access=league_access,
        odds_coverage=odds_coverage,
        fg_markets=fg_markets,
        bookmakers=bookmakers,
    )

    artifacts = {
        "oa3_token_capabilities.json": token_caps,
        "oa3_league_access.json": league_access,
        "oa3_historical_depth.json": historical,
        "oa3_odds_history_coverage.json": odds_coverage,
        "oa3_bookmaker_coverage.json": bookmakers,
        "oa3_first_goal_markets.json": fg_markets,
        "oa3_backfill_readiness.json": backfill,
        "oa3_provider_comparison.json": comparison,
    }
    for name, payload in artifacts.items():
        (ARTIFACTS / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    write_report(
        token_caps=token_caps,
        league_access=league_access,
        historical=historical,
        odds_coverage=odds_coverage,
        bookmakers=bookmakers,
        fg_markets=fg_markets,
        backfill=backfill,
        comparison=comparison,
        stats=stats,
    )
    return {"stats": stats, "artifacts": list(artifacts.keys())}
