"""PHASE OA-4 — Deep endpoint traversal audit (no conclusions in code)."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts"
RAW_DIR = ARTIFACTS / "oa4_raw"

TARGET_COMPETITIONS: dict[str, dict[str, str]] = {
    "premier_league": {"name": "Premier League", "country": "England"},
    "bundesliga": {"name": "Bundesliga", "country": "Germany"},
    "champions_league": {"name": "Champions League", "country": "Europe"},
    "la_liga": {"name": "La Liga", "country": "Spain"},
    "serie_a": {"name": "Serie A", "country": "Italy"},
}

_FINISHED = frozenset({"FT", "AET", "PEN", "AWD", "WO", "FINISHED"})

FIXTURE_ENDPOINTS = (
    "fixtures/results",
    "fixtures/upcoming",
    "fixtures/finished",
)

FIXTURE_PARAM_TEMPLATES: tuple[dict[str, Any], ...] = (
    {},
    {"competition_id": None},
    {"season_id": None},
    {"competition_id": None, "season_id": None},
    {"competition_id": None, "season_id": None, "page": 1, "per_page": 250},
    {"competition_id": None, "season_id": None, "status": "FT"},
    {"season_id": None, "status": "FT"},
    {"competition_id": None, "status": "FT"},
    {"season": None},
    {"competition_id": None, "season": None},
)

POOL_ENDPOINTS = (
    "value/results",
    "value/upcoming",
    "correctScores",
)

BOOKMAKER_FOCUS = ("pinnacle", "sbo", "bet365", "1xbet", "betfair", "williamhill", "kambi")
FTS_MARKET_TOKENS = ("first_team_to_score", "team_to_score_first", "first_goal", "fts")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _key_fp() -> str | None:
    key = (os.getenv("ODDALERTS_API_KEY") or "").strip()
    return hashlib.sha256(key.encode()).hexdigest()[:16] if key else None


def _save_raw(name: str, payload: Any) -> str:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    return str(path.relative_to(ROOT)).replace("\\", "/")


def _fixture_comp_id(row: dict[str, Any]) -> int | None:
    cid = row.get("competition_id")
    if cid is not None:
        return int(cid)
    comp = row.get("competition") or {}
    if comp.get("id") is not None:
        return int(comp["id"])
    return None


def _row_status(row: dict[str, Any]) -> str:
    return str(row.get("status") or "").upper()


def fetch_competitions_catalogue(client: OddAlertsClient, stats: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 0
    while page < 50:
        page += 1
        res = client.get_competitions(page=page, per_page=250)
        stats["api_calls"] += 1
        if not res.data:
            break
        batch = res.data.get("data") or []
        if not batch:
            break
        rows.extend(batch)
        if not (res.data.get("info") or {}).get("next_page_url"):
            break
    return rows


def resolve_target_competitions(
    client: OddAlertsClient,
    catalogue: list[dict[str, Any]],
    stats: dict[str, int],
) -> dict[str, dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for key, spec in TARGET_COMPETITIONS.items():
        match = next(
            (
                c
                for c in catalogue
                if str(c.get("name", "")).lower() == spec["name"].lower()
                and str(c.get("country", "")).lower() == spec["country"].lower()
            ),
            None,
        )
        if not match:
            by_key[key] = {"found": False, "spec": spec}
            continue
        cid = int(match["id"])
        detail = client._get(f"competitions/{cid}", params={"include": "seasons"})
        stats["api_calls"] += 1
        data = (detail.data or {}).get("data")
        row = data[0] if isinstance(data, list) and data else (data if isinstance(data, dict) else match)
        seasons = row.get("seasons") or []
        _save_raw(f"competition_{cid}_with_seasons", detail.data)
        by_key[key] = {
            "found": True,
            "league_key": key,
            "competition_id": cid,
            "name": row.get("name"),
            "country": row.get("country"),
            "current_season_id": row.get("current_season"),
            "seasons": seasons,
            "season_ids": [int(s["season_id"]) for s in seasons if s.get("season_id")],
            "season_labels": [s.get("season_name") for s in seasons],
        }
    return by_key


def _count_rows_for_comp(rows: list[dict[str, Any]], competition_id: int) -> dict[str, Any]:
    finished: set[int] = set()
    upcoming: set[int] = set()
    seasons: Counter[int] = Counter()
    samples: list[dict[str, Any]] = []
    for row in rows:
        if _fixture_comp_id(row) != competition_id:
            continue
        fid = int(row.get("id") or 0)
        sid = row.get("season_id") or (row.get("competition") or {}).get("season_id")
        if sid is not None:
            seasons[int(sid)] += 1
        st = _row_status(row)
        if fid and st in _FINISHED:
            finished.add(fid)
        elif fid:
            upcoming.add(fid)
        if len(samples) < 2:
            samples.append(
                {
                    "fixture_id": fid,
                    "home_name": row.get("home_name"),
                    "away_name": row.get("away_name"),
                    "status": row.get("status"),
                    "season_id": sid,
                    "season": row.get("season") or (row.get("competition") or {}).get("season"),
                }
            )
    return {
        "row_count_matching_competition": len(finished) + len(upcoming),
        "finished_fixture_count": len(finished),
        "upcoming_fixture_count": len(upcoming),
        "season_ids_seen": dict(seasons),
        "sample_rows": samples,
    }


def traverse_fixture_endpoints(
    client: OddAlertsClient,
    *,
    competition_id: int,
    season_id: int,
    season_label: str,
    stats: dict[str, int],
) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for endpoint in FIXTURE_ENDPOINTS:
        for template in FIXTURE_PARAM_TEMPLATES:
            params = dict(template)
            if "competition_id" in params:
                params["competition_id"] = competition_id
            if "season_id" in params:
                params["season_id"] = season_id
            if "season" in params:
                params["season"] = season_label
            res = client._get(endpoint, params=params or None)
            stats["api_calls"] += 1
            rows = (res.data or {}).get("data") or []
            counts = _count_rows_for_comp(rows, competition_id)
            entry = {
                "endpoint": endpoint,
                "params": params,
                "error": res.error,
                "http_ok": res.error is None,
                "total_rows_returned": len(rows),
                **counts,
            }
            attempts.append(entry)
            if rows and counts["row_count_matching_competition"] > 0:
                _save_raw(
                    f"fixtures_hit_{competition_id}_{season_id}_{endpoint.replace('/', '_')}",
                    {"params": params, "sample": rows[:3]},
                )
    return attempts


def scan_pool_endpoints(
    client: OddAlertsClient,
    *,
    competition_id: int,
    stats: dict[str, int],
    max_pages: int = 100,
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for endpoint in POOL_ENDPOINTS:
        all_rows: list[dict] = []
        page = 0
        while page < max_pages:
            page += 1
            params: dict[str, Any] = {"page": page, "per_page": 250}
            if endpoint == "correctScores":
                params["competition_id"] = competition_id
            res = client._get(endpoint, params=params)
            stats["api_calls"] += 1
            rows = (res.data or {}).get("data") or []
            if not rows:
                break
            all_rows.extend(rows)
            info = (res.data or {}).get("info") or {}
            has_more = info.get("next_page_url") or info.get("has_more")
            if not has_more:
                break
        counts = _count_rows_for_comp(all_rows, competition_id)
        out[endpoint] = {
            "pages_scanned": page,
            "total_rows_scanned": len(all_rows),
            **counts,
        }
    return out


def scan_global_pools(client: OddAlertsClient, stats: dict[str, int]) -> dict[str, Any]:
    pools: dict[str, Any] = {}
    for endpoint in ("fixtures/upcoming", "value/results", "value/upcoming"):
        rows: list[dict] = []
        page = 0
        while page < 100:
            page += 1
            res = client._get(endpoint, params={"page": page, "per_page": 250})
            stats["api_calls"] += 1
            batch = (res.data or {}).get("data") or []
            if not batch:
                break
            rows.extend(batch)
            if not ((res.data or {}).get("info") or {}).get("next_page_url"):
                break
        per_comp: dict[str, dict[str, int]] = {}
        for key, meta in TARGET_COMPETITIONS.items():
            cid = None
            # resolved later in inventory; count by scanning catalogue ids in rows
            per_comp[key] = {"placeholder": 0}
        comp_finished: dict[int, set[int]] = defaultdict(set)
        comp_upcoming: dict[int, set[int]] = defaultdict(set)
        for row in rows:
            cid = _fixture_comp_id(row)
            if cid is None:
                continue
            fid = int(row.get("id") or 0)
            if not fid:
                continue
            if _row_status(row) in _FINISHED:
                comp_finished[cid].add(fid)
            else:
                comp_upcoming[cid].add(fid)
        pools[endpoint] = {
            "pages_scanned": page,
            "total_rows": len(rows),
            "unique_competitions": len(set(_fixture_comp_id(r) for r in rows if _fixture_comp_id(r))),
            "competition_finished_counts": {str(k): len(v) for k, v in comp_finished.items()},
            "competition_upcoming_counts": {str(k): len(v) for k, v in comp_upcoming.items()},
        }
    return pools


def probe_fixture_derivatives(
    client: OddAlertsClient,
    fixture_id: int,
    stats: dict[str, int],
) -> dict[str, Any]:
    probes: dict[str, Any] = {"fixture_id": fixture_id}
    oh = client.get_odds_history(fixture_id)
    stats["api_calls"] += 1
    oh_rows = (oh.data or {}).get("data") or []
    probes["odds_history"] = {
        "error": oh.error,
        "row_count": len(oh_rows),
        "opening_rows": sum(1 for r in oh_rows if r.get("opening")),
        "closing_rows": sum(1 for r in oh_rows if r.get("closing")),
        "peak_rows": sum(1 for r in oh_rows if r.get("peak")),
        "markets": sorted({str(r.get("market_key")) for r in oh_rows}),
        "sample": oh_rows[:2],
    }
    om = client._get("odds/movement", params={"fixtures": fixture_id, "page": 1, "per_page": 50})
    stats["api_calls"] += 1
    om_rows = (om.data or {}).get("data") or []
    probes["odds_movement"] = {"error": om.error, "row_count": len(om_rows), "sample": om_rows[:2]}
    pr = client.get_probability_fixture(fixture_id)
    stats["api_calls"] += 1
    probes["probability"] = {
        "error": pr.error,
        "payload_keys": list((pr.data or {}).keys())[:10] if isinstance(pr.data, dict) else None,
        "sample": pr.data,
    }
    cs = client._get("correctScores", params={"fixture_id": fixture_id, "page": 1, "per_page": 20})
    stats["api_calls"] += 1
    cs_rows = (cs.data or {}).get("data") or []
    match = [r for r in cs_rows if int(r.get("id") or 0) == fixture_id]
    probes["correct_scores"] = {
        "error": cs.error,
        "row_count": len(cs_rows),
        "matching_fixture_rows": len(match),
        "sample": (match or cs_rows)[:2],
    }
    fx = client.get_fixture(fixture_id, include="odds,probability,stats")
    stats["api_calls"] += 1
    probes["fixture_detail"] = {"error": fx.error, "sample": fx.data}
    _save_raw(f"fixture_derivatives_{fixture_id}", probes)
    return probes


def audit_first_goal_markets(
    client: OddAlertsClient,
    fixture_ids: list[int],
    stats: dict[str, int],
) -> dict[str, Any]:
    markets: Counter[str] = Counter()
    fts_rows: list[dict[str, Any]] = []
    for fid in fixture_ids[:10]:
        res = client.get_odds_history(fid)
        stats["api_calls"] += 1
        for row in (res.data or {}).get("data") or []:
            mk = str(row.get("market_key") or "")
            markets[mk] += 1
            if any(tok in mk.lower() for tok in FTS_MARKET_TOKENS):
                fts_rows.append({"fixture_id": fid, "market_key": mk, "bookmaker": row.get("bookmaker_name")})
    direct = [m for m in markets if any(t in m for t in ("first_team_to_score", "team_to_score_first", "first_goal"))]
    return {
        "fixtures_scanned": len(fixture_ids[:10]),
        "markets_seen": dict(markets.most_common(30)),
        "direct_fts_markets": direct,
        "fts_rows": fts_rows[:30],
        "proxy_markets_present": [m for m in markets if m in ("home_goals", "away_goals")],
    }


def run_oa4_traversal(client: OddAlertsClient | None = None) -> dict[str, Any]:
    client = client or OddAlertsClient()
    if not client.is_configured:
        raise RuntimeError("ODDALERTS_API_KEY not configured")

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    stats: dict[str, int] = {"api_calls": 0, "endpoint_attempts": 0}

    catalogue = fetch_competitions_catalogue(client, stats)
    _save_raw("competitions_catalogue_page1", {"count": len(catalogue), "sample": catalogue[:5]})

    targets = resolve_target_competitions(client, catalogue, stats)

    inventory: list[dict[str, Any]] = []
    traversal_log: list[dict[str, Any]] = []
    proof_fixtures: dict[str, Any] = {}

    for league_key, meta in targets.items():
        if not meta.get("found"):
            inventory.append(
                {
                    "league_key": league_key,
                    "competition_id": None,
                    "season_id": None,
                    "season_label": None,
                    "finished_fixture_count": 0,
                    "upcoming_fixture_count": 0,
                    "note": "competition_not_found_in_catalogue",
                }
            )
            continue

        cid = int(meta["competition_id"])
        pool_scan = scan_pool_endpoints(client, competition_id=cid, stats=stats)
        traversal_log.append({"league_key": league_key, "competition_id": cid, "pool_scan": pool_scan})

        seasons = meta.get("seasons") or []
        if not seasons:
            seasons = [{"season_id": meta.get("current_season_id"), "season_name": "current_season"}]

        for season in seasons:
            sid = int(season.get("season_id") or 0)
            label = str(season.get("season_name") or "")
            attempts = traverse_fixture_endpoints(
                client,
                competition_id=cid,
                season_id=sid,
                season_label=label,
                stats=stats,
            )
            stats["endpoint_attempts"] += len(attempts)
            traversal_log.append(
                {
                    "league_key": league_key,
                    "competition_id": cid,
                    "season_id": sid,
                    "season_label": label,
                    "fixture_endpoint_attempts": attempts,
                }
            )

            best_finished = 0
            best_upcoming = 0
            sample_fid: int | None = None
            for att in attempts:
                best_finished = max(best_finished, att.get("finished_fixture_count", 0))
                best_upcoming = max(best_upcoming, att.get("upcoming_fixture_count", 0))
                for sample in att.get("sample_rows") or []:
                    if sample.get("fixture_id"):
                        sample_fid = int(sample["fixture_id"])
            for pool_name, pool_data in pool_scan.items():
                best_finished = max(best_finished, pool_data.get("finished_fixture_count", 0))
                best_upcoming = max(best_upcoming, pool_data.get("upcoming_fixture_count", 0))
                for sample in pool_data.get("sample_rows") or []:
                    if sample.get("fixture_id"):
                        sample_fid = int(sample["fixture_id"])

            inventory.append(
                {
                    "league_key": league_key,
                    "competition_id": cid,
                    "competition_name": meta.get("name"),
                    "country": meta.get("country"),
                    "season_id": sid,
                    "season_label": label,
                    "season_played": season.get("played"),
                    "season_progress": season.get("progress"),
                    "finished_fixture_count": best_finished,
                    "upcoming_fixture_count": best_upcoming,
                    "fixture_endpoint_attempts": len(attempts),
                    "pool_scan": pool_scan,
                }
            )

            if sample_fid and league_key not in proof_fixtures:
                proof_fixtures[league_key] = probe_fixture_derivatives(client, sample_fid, stats)

    global_pools = scan_global_pools(client, stats)

    # Token capabilities
    books = (client.get_bookmakers().data or {}).get("data") or []
    stats["api_calls"] += 1

    token_caps = {
        "generated_at": _now(),
        "api_key_fingerprint_sha256_16": _key_fp(),
        "competitions_catalogue_count": len(catalogue),
        "bookmakers": [b.get("name") for b in books],
        "global_pool_scan": global_pools,
        "season_discovery_method": "GET competitions/{id}?include=seasons",
        "targets_resolved": targets,
    }

    # Pick proof fixtures: target leagues first, else any finished from global pools
    all_proof_ids: list[int] = []
    for row in proof_fixtures.values():
        fid = row.get("fixture_id")
        if fid:
            all_proof_ids.append(int(fid))

    # WC fallback proof from value/results if no target proof
    if not all_proof_ids:
        res = client._get("value/results", params={"page": 1, "per_page": 250})
        stats["api_calls"] += 1
        for row in (res.data or {}).get("data") or []:
            if _row_status(row) in _FINISHED and (row.get("competition") or {}).get("id") == 1690:
                fid = int(row["id"])
                proof_fixtures["world_cup_proof"] = probe_fixture_derivatives(client, fid, stats)
                all_proof_ids.append(fid)
                break

    fg_markets = audit_first_goal_markets(client, all_proof_ids, stats)

  # Bookmaker coverage from proof fixtures
    book_cov: dict[str, Any] = {"focus": {}, "listed": [str(b.get("name", "")).lower() for b in books]}
    for book in BOOKMAKER_FOCUS:
        book_cov["focus"][book] = {
            "listed": any(book in name for name in book_cov["listed"]),
            "historical_rows": 0,
            "opening_rows": 0,
            "closing_rows": 0,
        }
    for fid in all_proof_ids[:5]:
        res = client.get_odds_history(fid)
        stats["api_calls"] += 1
        for row in (res.data or {}).get("data") or []:
            name = str(row.get("bookmaker_name") or "").lower()
            for book in BOOKMAKER_FOCUS:
                if book in name:
                    book_cov["focus"][book]["historical_rows"] += 1
                    if row.get("opening"):
                        book_cov["focus"][book]["opening_rows"] += 1
                    if row.get("closing"):
                        book_cov["focus"][book]["closing_rows"] += 1

    historical_depth = {
        "generated_at": _now(),
        "per_inventory_row": [
            {
                "league_key": r["league_key"],
                "competition_id": r["competition_id"],
                "season_id": r["season_id"],
                "season_label": r["season_label"],
                "finished_fixture_count": r["finished_fixture_count"],
                "upcoming_fixture_count": r["upcoming_fixture_count"],
            }
            for r in inventory
        ],
    }

    backfill = {
        "generated_at": _now(),
        "inventory_summary": {
            "total_inventory_rows": len(inventory),
            "rows_with_finished_gt_0": sum(1 for r in inventory if r.get("finished_fixture_count", 0) > 0),
            "rows_with_upcoming_gt_0": sum(1 for r in inventory if r.get("upcoming_fixture_count", 0) > 0),
        },
        "per_league_totals": {},
    }
    for league_key in TARGET_COMPETITIONS:
        rows = [r for r in inventory if r["league_key"] == league_key]
        backfill["per_league_totals"][league_key] = {
            "finished_fixtures_max_per_season": max((r.get("finished_fixture_count") or 0) for r in rows) if rows else 0,
            "upcoming_fixtures_max_per_season": max((r.get("upcoming_fixture_count") or 0) for r in rows) if rows else 0,
            "seasons_tested": len(rows),
            "estimated_api_calls_if_history_per_fixture": "2 * finished_fixture_count",
        }

    comparison = {
        "generated_at": _now(),
        "measured_oddalerts": {
            "endpoint_attempts": stats["endpoint_attempts"],
            "inventory_rows": len(inventory),
            "proof_fixtures_tested": list(proof_fixtures.keys()),
        },
        "reference_api_football": "Primary fixtures/results spine in SQLite",
        "reference_sportmonks": "UEFA odds primary; K2 sharp MW FG 78.7%",
    }

    proof = {
        "generated_at": _now(),
        "api_stats": stats,
        "traversal_log_excerpt": traversal_log[:5],
        "traversal_log_full_path": _save_raw("oa4_full_traversal_log", traversal_log),
        "inventory": inventory,
        "proof_fixtures": proof_fixtures,
        "targets_resolved": targets,
    }
    _save_raw("oa4_proof", proof)

    outputs = {
        "oa4_token_capabilities.json": token_caps,
        "oa4_league_access.json": {"generated_at": _now(), "targets": targets, "inventory": inventory, "global_pools": global_pools},
        "oa4_historical_depth.json": historical_depth,
        "oa4_odds_history_coverage.json": {"generated_at": _now(), "proof_fixtures": proof_fixtures},
        "oa4_bookmaker_coverage.json": {"generated_at": _now(), **book_cov},
        "oa4_first_goal_markets.json": fg_markets,
        "oa4_backfill_readiness.json": backfill,
        "oa4_provider_comparison.json": comparison,
        "oa4_endpoint_traversal_proof.json": proof,
    }
    for name, payload in outputs.items():
        (ARTIFACTS / name).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    write_report(proof, token_caps, inventory, proof_fixtures, stats)
    return proof


def write_report(
    proof: dict[str, Any],
    token_caps: dict[str, Any],
    inventory: list[dict[str, Any]],
    proof_fixtures: dict[str, Any],
    stats: dict[str, int],
) -> None:
    lines = [
        "# PHASE OA-4 — Deep Endpoint Traversal Audit",
        "",
        f"**Generated:** {_now()}  ",
        f"**API key fingerprint (sha256/16):** `{token_caps.get('api_key_fingerprint_sha256_16')}`  ",
        f"**API calls:** {stats.get('api_calls', 0)}  ",
        f"**Fixture endpoint attempts:** {stats.get('endpoint_attempts', 0)}  ",
        "",
        "> This report records measured traversal results only. No early-stop on zero rows.",
        "",
        "## Season discovery",
        "",
        "Seasons retrieved via `GET competitions/{id}?include=seasons` for each target competition.",
        "Raw samples: `artifacts/oa4_raw/competition_*_with_seasons.json`",
        "",
        "## Inventory (competition_id × season_id)",
        "",
        "| League | Comp ID | Season | Season ID | Finished | Upcoming |",
        "|--------|---------|--------|-----------|----------|----------|",
    ]
    for row in inventory:
        lines.append(
            f"| {row.get('league_key')} | {row.get('competition_id')} | {row.get('season_label')} | "
            f"{row.get('season_id')} | {row.get('finished_fixture_count', 0)} | {row.get('upcoming_fixture_count', 0)} |"
        )

    lines.extend(["", "## Endpoint traversal", ""])
    lines.append(f"- Full traversal log: `{proof.get('traversal_log_full_path')}`")
    lines.append(f"- Proof bundle: `artifacts/oa4_endpoint_traversal_proof.json`")
    lines.append(f"- Raw samples: `artifacts/oa4_raw/`")

    lines.extend(["", "## Derivative tests (when fixture_id available)", ""])
    if proof_fixtures:
        for key, block in proof_fixtures.items():
            oh = (block.get("odds_history") or {})
            lines.append(
                f"- **{key}** fixture `{block.get('fixture_id')}`: "
                f"odds/history rows={oh.get('row_count')}, movement={block.get('odds_movement', {}).get('row_count')}, "
                f"probability error={block.get('probability', {}).get('error')}"
            )
    else:
        lines.append("- No target-league fixture_id obtained from traversal; see proof JSON for fallback tests.")

    lines.extend(
        [
            "",
            "## Artifacts",
            "",
            "- `artifacts/oa4_token_capabilities.json`",
            "- `artifacts/oa4_league_access.json`",
            "- `artifacts/oa4_historical_depth.json`",
            "- `artifacts/oa4_odds_history_coverage.json`",
            "- `artifacts/oa4_bookmaker_coverage.json`",
            "- `artifacts/oa4_first_goal_markets.json`",
            "- `artifacts/oa4_backfill_readiness.json`",
            "- `artifacts/oa4_provider_comparison.json`",
            "- `artifacts/oa4_endpoint_traversal_proof.json`",
            "",
            "---",
            "",
            "**STOP — Audit only. Facts in JSON artifacts.**",
        ]
    )
    (ROOT / "PHASE_OA4_ENDPOINT_TRAVERSAL_AUDIT_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
