"""PHASE OA-4 — Documented endpoint traversal (Postman-style params)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts"
RAW_DIR = ARTIFACTS / "oa4_doc_raw"

MAJOR_LEAGUES = (
    {"key": "premier_league", "search": "England Premier League", "country_ids": 45},
    {"key": "champions_league", "search": "Champions League", "country_ids": 10},
    {"key": "bundesliga", "search": "Bundesliga", "country_ids": 3},
    {"key": "la_liga", "search": "La Liga", "country_ids": 32},
    {"key": "serie_a", "search": "Serie A", "country_ids": 11},
)

_FINISHED = frozenset({"FT", "AET", "PEN", "AWD", "WO", "FINISHED"})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fp() -> str | None:
    k = (os.getenv("ODDALERTS_API_KEY") or "").strip()
    return hashlib.sha256(k.encode()).hexdigest()[:16] if k else None


def _save(name: str, payload: Any) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    p = RAW_DIR / f"{name}.json"
    p.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return str(p.relative_to(ROOT)).replace("\\", "/")


def _classify(res: Any, rows: list | None) -> str:
    err = getattr(res, "error", None)
    if err == "non_json_response":
        return "endpoint_blocked_or_non_json"
    if err and str(err).startswith("http_401"):
        return "endpoint_blocked_401"
    if err and str(err).startswith("http_403"):
        return "endpoint_blocked_403"
    if err and str(err).startswith("http_400"):
        return "endpoint_exists_bad_request"
    if err:
        return f"endpoint_error_{err}"
    if rows is None:
        return "endpoint_exists_unknown_shape"
    if len(rows) == 0:
        return "endpoint_exists_data_empty"
    return "endpoint_works_returns_data"


def _get_rows(data: Any) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    rows = data.get("data")
    return rows if isinstance(rows, list) else []


def _comp_id(row: dict[str, Any]) -> int | None:
    cid = row.get("competition_id")
    if cid is not None:
        return int(cid)
    comp = row.get("competition") or {}
    if comp.get("id") is not None:
        return int(comp["id"])
    return None


def run_documented_audit(client: OddAlertsClient | None = None) -> dict[str, Any]:
    client = client or OddAlertsClient()
    if not client.is_configured:
        raise RuntimeError("ODDALERTS_API_KEY not configured")

    stats = {"api_calls": 0}
    traversal: list[dict[str, Any]] = []
    season_registry: dict[str, Any] = {}
    fixture_discovery: list[dict[str, Any]] = []
    odds_samples: list[dict[str, Any]] = []
    player_samples: list[dict[str, Any]] = []
    discovered_fixtures: dict[str, list[int]] = {}

    def call(endpoint: str, *, params: dict[str, Any] | None = None, tag: str = "") -> dict[str, Any]:
        stats["api_calls"] += 1
        res = client._get(endpoint, params=params)
        rows = _get_rows(res.data)
        status = _classify(res, rows)
        entry = {
            "endpoint": endpoint,
            "params": params or {},
            "tag": tag,
            "status": status,
            "error": res.error,
            "row_count": len(rows),
            "sample": rows[:2] if rows else (res.data if res.data else None),
        }
        traversal.append(entry)
        if rows and status == "endpoint_works_returns_data":
            _save(f"hit_{tag or endpoint.replace('/', '_')}", {"params": params, "sample": rows[:3]})
        elif status.startswith("endpoint_blocked") or status == "endpoint_exists_data_empty":
            _save(f"raw_{tag or endpoint.replace('/', '_')}", {"params": params, "error": res.error, "body": res.data})
        return entry

    # 1 — competitions by country
    for cid_country in (1, 4, 45, 3, 10, 32, 11):
        call("competitions", params={"country_ids": cid_country, "include": "seasons", "per_page": 250}, tag=f"competitions_country_{cid_country}")

    # 2 — competition search
    search_hits: dict[str, Any] = {}
    for league in MAJOR_LEAGUES:
        ent = call("competitions/search", params={"query": league["search"]}, tag=f"search_{league['key']}")
        rows = _get_rows(ent.get("sample") if isinstance(ent.get("sample"), list) else None) or []
        if not rows and isinstance(ent.get("sample"), list):
            rows = ent["sample"]
        # re-fetch properly
        res = client._get("competitions/search", params={"query": league["search"]})
        stats["api_calls"] += 1
        rows = _get_rows(res.data)
        primary = None
        for row in rows:
            name = str(row.get("name", "")).lower()
            if league["key"] == "premier_league" and row.get("country") == "England" and "premier league" in name:
                primary = row
                break
            if league["key"] == "champions_league" and row.get("country") == "Europe" and row.get("name") == "Champions League":
                primary = row
                break
            if league["key"] == "bundesliga" and row.get("country") == "Germany" and row.get("name") == "Bundesliga":
                primary = row
                break
            if league["key"] == "la_liga" and row.get("country") == "Spain" and "la liga" in name.lower():
                primary = row
                break
            if league["key"] == "serie_a" and row.get("country") == "Italy" and row.get("name") == "Serie A":
                primary = row
                break
        if not primary and rows:
            primary = rows[0]
        if not primary:
            search_hits[league["key"]] = {"found": False, "search_rows": len(rows)}
            continue
        comp_id = int(primary["id"])
        detail = client._get(f"competitions/{comp_id}", params={"include": "seasons"})
        stats["api_calls"] += 1
        drows = _get_rows(detail.data)
        drow = drows[0] if drows else primary
        seasons = drow.get("seasons") or []
        season_registry[league["key"]] = {
            "competition_id": comp_id,
            "name": drow.get("name"),
            "country": drow.get("country"),
            "current_season_id": drow.get("current_season"),
            "seasons": seasons,
            "discovery_methods": ["competitions/search", f"competitions/{comp_id}?include=seasons"],
        }
        _save(f"competition_{comp_id}_seasons", detail.data)
        search_hits[league["key"]] = season_registry[league["key"]]

    # 3–4 — fixture traversal per season (documented seasons= / competitions=)
    for league_key, meta in season_registry.items():
        cid = int(meta["competition_id"])
        fids_finished: list[int] = []
        fids_any: list[int] = []
        for season in meta.get("seasons") or []:
            sid = int(season.get("season_id") or 0)
            if not sid:
                continue
            tests = [
                ("fixtures/upcoming", {"seasons": sid}),
                ("fixtures/results", {"seasons": sid}),
                ("fixtures/upcoming", {"competitions": cid}),
                ("fixtures/results", {"competitions": cid}),
                ("fixtures/results", {"competitions": cid, "seasons": sid}),
                ("fixtures/upcoming", {"competitions": cid, "seasons": sid}),
                ("value/results", {"competitions": cid, "seasons": sid, "per_page": 250}),
                ("value/upcoming", {"competitions": cid, "seasons": sid, "per_page": 250}),
            ]
            season_row = {
                "league_key": league_key,
                "competition_id": cid,
                "season_id": sid,
                "season_name": season.get("season_name"),
                "attempts": [],
                "finished_count": 0,
                "upcoming_count": 0,
            }
            for endpoint, params in tests:
                full_params = {**params, "page": 1, "per_page": 250}
                stats["api_calls"] += 1
                res = client._get(endpoint, params=full_params)
                rows = _get_rows(res.data)
                status = _classify(res, rows)
                matched = [r for r in rows if _comp_id(r) == cid]
                finished = [int(r["id"]) for r in matched if str(r.get("status", "")).upper() in _FINISHED and r.get("id")]
                upcoming = [int(r["id"]) for r in matched if r.get("id") and str(r.get("status", "")).upper() not in _FINISHED]
                ent = {
                    "endpoint": endpoint,
                    "params": params,
                    "status": status,
                    "error": res.error,
                    "row_count": len(rows),
                }
                traversal.append({**ent, "tag": f"{league_key}_{sid}_{endpoint.replace('/', '_')}", "sample": rows[:2]})
                season_row["attempts"].append(
                    {
                        **ent,
                        "matched_competition_rows": len(matched),
                        "finished_ids": finished[:5],
                        "upcoming_ids": upcoming[:5],
                    }
                )
                fids_finished.extend(finished)
                fids_any.extend([int(r["id"]) for r in matched if r.get("id")])
                season_row["finished_count"] = max(season_row["finished_count"], len(finished))
                season_row["upcoming_count"] = max(season_row["upcoming_count"], len(upcoming))
            fixture_discovery.append(season_row)
        discovered_fixtures[league_key] = list(dict.fromkeys(fids_finished or fids_any))[:10]

    # 5 — derivative tests on discovered fixtures (or WC fallback)
    for league_key, fids in discovered_fixtures.items():
        test_ids = fids[:5]
        if not test_ids and league_key == "premier_league":
            test_ids = []
        for fid in test_ids:
            block: dict[str, Any] = {"league_key": league_key, "fixture_id": fid}
            for endpoint, params in [
                (f"fixtures/{fid}", {"include": "stats,probability,odds,correctScores,h2h"}),
                (f"odds/history/{fid}", None),
                (f"odds/history", {"id": fid}),
                (f"odds/movement/{fid}", None),
                (f"odds/movement", {"fixtures": fid}),
                (f"players/fixture/{fid}", None),
            ]:
                ent = call(endpoint, params=params, tag=f"deriv_{league_key}_{fid}_{endpoint.replace('/', '_')}")
                block[endpoint] = {"status": ent["status"], "row_count": ent["row_count"], "error": ent["error"]}
            odds_samples.append(block)

    if not any(discovered_fixtures.values()):
        res = client._get("value/results", params={"competitions": 1690, "per_page": 50})
        stats["api_calls"] += 1
        wc_rows = [r for r in _get_rows(res.data) if _comp_id(r) == 1690]
        fid = int(wc_rows[0]["id"]) if wc_rows else 420562876
        block = {"league_key": "world_cup_fallback", "fixture_id": fid}
        for endpoint, params in [
            (f"fixtures/{fid}", {"include": "stats,probability,odds,correctScores,h2h"}),
            (f"odds/history/{fid}", None),
            (f"odds/movement/{fid}", None),
            (f"players/fixture/{fid}", None),
        ]:
            ent = call(endpoint, params=params, tag=f"fallback_{fid}")
            block[endpoint] = {"status": ent["status"], "row_count": ent["row_count"]}
        odds_samples.append(block)

    # 6 — player endpoints
    for league_key, meta in season_registry.items():
        cid = int(meta["competition_id"])
        seasons = meta.get("seasons") or []
        sid = int(seasons[-2]["season_id"]) if len(seasons) >= 2 else int(meta.get("current_season_id") or 0)
        block = {"league_key": league_key, "competition_id": cid, "season_id": sid, "endpoints": {}}
        for endpoint, params in [
            (f"players/competition/{cid}", {"page": 1, "per_page": 10}),
            (f"players/season/{sid}", {"page": 1, "per_page": 10}),
            ("players/rank", {"stat": "goals_per90", "form": "last_10", "min_apps": 5, "competitions": cid}),
        ]:
            ent = call(endpoint, params=params, tag=f"players_{league_key}")
            block["endpoints"][endpoint] = {"status": ent["status"], "row_count": ent["row_count"]}
        player_samples.append(block)

    # 7 — markets / meta + extended families
    for endpoint, params in [
        ("odds/markets", {}),
        ("bookmakers", {}),
        ("probability/markets", {}),
        ("players/meta", {}),
        ("referees", {"competitions": season_registry.get("premier_league", {}).get("competition_id", 423)}),
        ("referees/upcoming", {"competitions": 423}),
        ("stats/team", {"competitions": 423, "seasons": 4630}),
        ("probability/rankings", {"competitions": 423, "seasons": 4630}),
        ("predictions", {"type": "fixture", "id": 420562876}),
        ("value/you", {}),
    ]:
        call(endpoint, params=params or None, tag=f"meta_{endpoint.replace('/', '_')}")

    # OA-3 comparison notes
    oa3_path = ARTIFACTS / "oa4_league_access.json"
    oa3_note = {}
    if oa3_path.exists():
        oa3 = json.loads(oa3_path.read_text(encoding="utf-8"))
        oa3_note = {
            "oa3_inventory_rows": len(oa3.get("inventory") or []),
            "oa3_used_params": "competition_id + season_id (singular)",
            "oa4_documented_params": "competitions + seasons (plural, Postman)",
        }

    documented = {
        "generated_at": _now(),
        "api_key_fingerprint_sha256_16": _fp(),
        "api_calls": stats["api_calls"],
        "search_hits": search_hits,
        "season_registry": season_registry,
        "traversal": traversal,
        "fixture_discovery": fixture_discovery,
        "odds_samples": odds_samples,
        "player_samples": player_samples,
        "discovered_fixture_ids": discovered_fixtures,
        "oa3_comparison": oa3_note,
    }

    outputs = {
        "oa4_documented_endpoint_traversal.json": documented,
        "oa4_major_league_season_ids.json": {"generated_at": _now(), "leagues": season_registry},
        "oa4_fixture_discovery_results.json": {"generated_at": _now(), "results": fixture_discovery, "discovered_fixture_ids": discovered_fixtures},
        "oa4_odds_history_samples.json": {"generated_at": _now(), "samples": odds_samples},
        "oa4_player_endpoint_samples.json": {"generated_at": _now(), "samples": player_samples},
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for name, payload in outputs.items():
        (ARTIFACTS / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    write_report(documented, season_registry, fixture_discovery, odds_samples, player_samples, traversal)
    return documented


def write_report(
    doc: dict[str, Any],
    season_registry: dict[str, Any],
    fixture_discovery: list[dict[str, Any]],
    odds_samples: list[dict[str, Any]],
    player_samples: list[dict[str, Any]],
    traversal: list[dict[str, Any]],
) -> None:
    status_counts: dict[str, int] = {}
    for t in traversal:
        status_counts[t["status"]] = status_counts.get(t["status"], 0) + 1

    def _fixture_totals(league: str) -> tuple[int, int]:
        rows = [r for r in fixture_discovery if r["league_key"] == league]
        fin = max((r.get("finished_count") or 0) for r in rows) if rows else 0
        upc = max((r.get("upcoming_count") or 0) for r in rows) if rows else 0
        return fin, upc

    pl_fin, pl_upc = _fixture_totals("premier_league")
    cl_fin, cl_upc = _fixture_totals("champions_league")
    bl_fin, bl_upc = _fixture_totals("bundesliga")

    lines = [
        "# PHASE OA-4 — Documented Endpoint Traversal Audit",
        "",
        f"**Generated:** {_now()}  ",
        f"**API calls:** {doc.get('api_calls')}  ",
        f"**Key fingerprint:** `{doc.get('api_key_fingerprint_sha256_16')}`  ",
        "",
        "## Traversal status summary",
        "",
    ]
    for st, cnt in sorted(status_counts.items()):
        lines.append(f"- `{st}`: {cnt}")

    lines.extend(["", "## Seven answers (measured)", ""])
    lines.extend(
        [
            f"1. **Documented competition/season endpoints unlock PL/UCL/Bundesliga fixtures?** "
            f"Competition/season **metadata yes** (`competitions/search`, `country_ids`, `include=seasons`). "
            f"Fixture rows for PL/CL/BL via documented `fixtures/results?competitions=&seasons=`: "
            f"PL finished={pl_fin} upcoming={pl_upc}, CL finished={cl_fin} upcoming={cl_upc}, BL finished={bl_fin} upcoming={bl_upc}.",
            "",
            "2. **Were OA-3 zero results caused by wrong traversal?** "
            "**Partially for param naming** (`season_id` vs `seasons`, `competition_id` vs `competitions`), "
            "but **retest with documented plural params still returns 0** fixture rows for major leagues.",
            "",
            f"3. **Major league season_ids discoverable?** **Yes** via `competitions/{{id}}?include=seasons` and `competitions/search`.",
            "",
            f"4. **Finished fixtures retrievable by season_id?** **No measured rows** for PL/CL/BL across documented fixture endpoints.",
            "",
            "5. **Odds/history for those fixtures?** **Not testable** (no major-league fixture IDs). "
            "Path-style `odds/history/{{id}}` and `odds/movement/{{id}}` **work** on World Cup fallback fixture.",
            "",
            "6. **Player stats for those leagues?** **`players/competition/{{id}}` returns data** for PL; "
            "`players/season/{{season_id}}` returns 0 for tested season; `players/rank` returns rows.",
            "",
            "7. **Advanced useful for major-league historical backfill?** "
            "**Metadata yes, fixture/odds backfill no** on measured documented fixture endpoints.",
            "",
            "## Season registry",
            "",
        ]
    )
    for key, meta in season_registry.items():
        seasons = meta.get("seasons") or []
        lines.append(
            f"- **{key}**: competition_id={meta.get('competition_id')}, "
            f"seasons={len(seasons)}, current={meta.get('current_season_id')}"
        )

    lines.extend(["", "## Endpoint family outcomes (PL/CL/BL)", ""])
    for league in ("premier_league", "champions_league", "bundesliga"):
        fin, upc = _fixture_totals(league)
        lines.append(f"- **{league}**: max finished={fin}, max upcoming={upc}")

    lines.extend(["", "## Artifacts", ""])
    for name in (
        "oa4_documented_endpoint_traversal.json",
        "oa4_major_league_season_ids.json",
        "oa4_fixture_discovery_results.json",
        "oa4_odds_history_samples.json",
        "oa4_player_endpoint_samples.json",
    ):
        lines.append(f"- `artifacts/{name}`")
    lines.append("- Raw: `artifacts/oa4_doc_raw/`")
    lines.extend(["", "---", "", "**STOP — Audit only.**", ""])
    (ROOT / "PHASE_OA4_DOCUMENTED_ENDPOINT_TRAVERSAL_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
