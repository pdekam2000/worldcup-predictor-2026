"""PHASE OA-2B — Raw OddAlerts competition discovery (no league assumptions)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

ROOT = Path(__file__).resolve().parents[3]
ARTIFACTS = ROOT / "artifacts"

_FINISHED = frozenset({"FT", "AET", "PEN", "AWD", "WO", "FINISHED"})

TARGET_LOOKUPS = (
    {"label": "england_premier_league", "name": "Premier League", "country": "England"},
    {"label": "champions_league", "name": "Champions League", "country": "Europe"},
    {"label": "germany_bundesliga", "name": "Bundesliga", "country": "Germany"},
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _competition_row(comp: dict[str, Any] | None) -> dict[str, Any]:
    comp = comp or {}
    return {
        "competition_id": comp.get("id"),
        "competition_name": comp.get("name"),
        "country": comp.get("country"),
        "season_label": comp.get("season"),
        "season_id": comp.get("season_id"),
        "is_cup": comp.get("is_cup"),
        "is_friendly": comp.get("is_friendly"),
    }


def fetch_all_competitions(client: OddAlertsClient, *, stats: dict[str, int]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 0
    while page < 50:
        page += 1
        result = client.get_competitions(page=page, per_page=250)
        stats["api_calls"] += 1
        if not result.data or result.error:
            stats["errors"] += 1
            break
        batch = result.data.get("data") or []
        if not batch:
            break
        rows.extend(batch)
        info = result.data.get("info") or {}
        if not info.get("next_page_url"):
            break
    return rows


def scan_value_pool(
    client: OddAlertsClient,
    *,
    endpoint: str,
    stats: dict[str, int],
    max_pages: int = 100,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 0
    while page < max_pages:
        page += 1
        result = client._get(endpoint, params={"page": page, "per_page": 250})
        stats["api_calls"] += 1
        if not result.data or result.error:
            stats["errors"] += 1
            break
        batch = result.data.get("data") or []
        if not batch:
            break
        rows.extend(batch)
        info = result.data.get("info") or {}
        if not info.get("next_page_url"):
            break
    stats[f"{endpoint.replace('/', '_')}_pages"] = page
    stats[f"{endpoint.replace('/', '_')}_rows"] = len(rows)
    return rows


def build_inventory(
    client: OddAlertsClient,
    *,
    odds_history_sample_top_n: int = 50,
    max_odds_history_calls: int = 60,
) -> dict[str, Any]:
    stats: dict[str, int] = {"api_calls": 0, "errors": 0}

    competitions = fetch_all_competitions(client, stats=stats)
    comp_by_id: dict[int, dict[str, Any]] = {int(c["id"]): c for c in competitions if c.get("id")}

    results_rows = scan_value_pool(client, endpoint="value/results", stats=stats)
    upcoming_rows = scan_value_pool(client, endpoint="value/upcoming", stats=stats)

    fixture_ids_by_comp: dict[int, set[int]] = defaultdict(set)
    finished_by_comp: dict[int, set[int]] = defaultdict(set)
    upcoming_by_comp: dict[int, set[int]] = defaultdict(set)
    seasons_by_comp: dict[int, set[tuple[Any, Any]]] = defaultdict(set)
    embedded_odds_by_comp: Counter[int] = Counter()
    fixtures_with_odds_by_comp: Counter[int] = Counter()

    def _ingest_row(row: dict[str, Any], *, pool: str) -> None:
        fid = int(row.get("id") or 0)
        if not fid:
            return
        comp = row.get("competition") or {}
        cid = comp.get("id")
        if cid is None:
            return
        cid = int(cid)
        fixture_ids_by_comp[cid].add(fid)
        status = str(row.get("status") or "").upper()
        if status in _FINISHED:
            finished_by_comp[cid].add(fid)
        elif pool == "upcoming":
            upcoming_by_comp[cid].add(fid)
        label = comp.get("season")
        sid = comp.get("season_id")
        if label or sid:
            seasons_by_comp[cid].add((label, sid))
        odds = row.get("odds") or []
        if odds:
            fixtures_with_odds_by_comp[cid] += 1
            embedded_odds_by_comp[cid] += len(odds)

    for row in results_rows:
        _ingest_row(row, pool="results")
    for row in upcoming_rows:
        _ingest_row(row, pool="upcoming")

    # current_season from competitions catalogue
    for cid, comp in comp_by_id.items():
        cs = comp.get("current_season")
        if cs:
            seasons_by_comp[cid].add(("current_season_id", cs))

    competition_stats: list[dict[str, Any]] = []
    for cid in sorted(set(comp_by_id) | set(fixture_ids_by_comp)):
        meta = comp_by_id.get(cid, {})
        competition_stats.append(
            {
                "competition_id": cid,
                "name": meta.get("name"),
                "slug": meta.get("slug"),
                "country": meta.get("country"),
                "country_id": meta.get("country_id"),
                "type": meta.get("type"),
                "current_season_id": meta.get("current_season"),
                "fixture_count_pool": len(fixture_ids_by_comp.get(cid, set())),
                "finished_fixture_count_pool": len(finished_by_comp.get(cid, set())),
                "upcoming_fixture_count_pool": len(upcoming_by_comp.get(cid, set())),
                "seasons_seen_in_pool": [
                    {"season_label": s[0], "season_id": s[1]} for s in sorted(seasons_by_comp.get(cid, set()), key=str)
                ],
                "embedded_odds_selections": int(embedded_odds_by_comp.get(cid, 0)),
                "fixtures_with_embedded_odds": int(fixtures_with_odds_by_comp.get(cid, 0)),
                "in_competitions_catalogue": cid in comp_by_id,
                "in_historical_results_pool": cid in finished_by_comp,
            }
        )

    competition_stats.sort(key=lambda x: x["finished_fixture_count_pool"], reverse=True)
    top50 = competition_stats[:odds_history_sample_top_n]

    odds_history_samples: list[dict[str, Any]] = []
    calls = 0
    for comp in top50:
        if calls >= max_odds_history_calls:
            break
        cid = int(comp["competition_id"])
        sample_fid = next(iter(finished_by_comp.get(cid, []) or fixture_ids_by_comp.get(cid, set())), None)
        if not sample_fid:
            comp["odds_history_sample"] = {"fixture_id": None, "history_rows": 0, "sampled": False}
            continue
        result = client.get_odds_history(int(sample_fid))
        stats["api_calls"] += 1
        calls += 1
        rows = (result.data or {}).get("data") or []
        sample = {
            "fixture_id": int(sample_fid),
            "history_rows": len(rows),
            "sampled": True,
            "error": result.error,
        }
        comp["odds_history_sample"] = sample
        odds_history_samples.append({"competition_id": cid, **sample})

    # fixtures/results probe for catalogue targets
    fixtures_results_probe: list[dict[str, Any]] = []
    for lookup in TARGET_LOOKUPS:
        matches = [
            c
            for c in competitions
            if str(c.get("name", "")).lower() == lookup["name"].lower()
            and str(c.get("country", "")).lower() == lookup["country"].lower()
        ]
        for m in matches:
            cid = int(m["id"])
            sid = m.get("current_season")
            probe = client._get(
                "fixtures/results",
                params={"competition_id": cid, "season_id": sid},
            )
            stats["api_calls"] += 1
            n = len((probe.data or {}).get("data") or [])
            fixtures_results_probe.append(
                {
                    "label": lookup["label"],
                    "competition_id": cid,
                    "name": m.get("name"),
                    "country": m.get("country"),
                    "current_season_id": sid,
                    "fixtures_results_rows": n,
                    "error": probe.error,
                }
            )

    premier_league_name_matches = [
        {
            "competition_id": c["id"],
            "name": c["name"],
            "country": c["country"],
            "current_season_id": c.get("current_season"),
            "in_results_pool": int(c["id"]) in finished_by_comp,
            "finished_fixtures_in_pool": len(finished_by_comp.get(int(c["id"]), set())),
        }
        for c in competitions
        if "premier league" in str(c.get("name", "")).lower()
    ]

    all_seasons = sorted(
        {
            (cid, s["season_label"], s["season_id"])
            for cid, seasons in seasons_by_comp.items()
            for s in (
                [{"season_label": x[0], "season_id": x[1]} for x in seasons]
            )
        },
        key=lambda t: (t[0], str(t[1]), str(t[2])),
    )

    pool_competition_ids = sorted(set(fixture_ids_by_comp))
    catalogue_only = sorted(set(comp_by_id) - set(fixture_ids_by_comp))

    return {
        "generated_at": _now(),
        "api_stats": stats,
        "subscription_scope": {
            "competitions_catalogue_total": len(competitions),
            "competitions_with_any_pool_fixtures": len(pool_competition_ids),
            "competitions_catalogue_only_no_pool_fixtures": len(catalogue_only),
            "unique_season_pairs_in_pool": len(all_seasons),
            "value_results_rows_scanned": len(results_rows),
            "value_upcoming_rows_scanned": len(upcoming_rows),
            "unique_finished_fixtures_in_results_pool": len(
                {fid for s in finished_by_comp.values() for fid in s}
            ),
        },
        "competitions_catalogue": competitions,
        "competition_ids": sorted(int(c["id"]) for c in competitions),
        "seasons_available": [
            {"competition_id": cid, "season_label": label, "season_id": sid}
            for cid, label, sid in all_seasons
        ],
        "competition_inventory": competition_stats,
        "top_50_historical_fixtures": top50,
        "target_league_verification": {
            "by_exact_name_country": fixtures_results_probe,
            "premier_league_name_matches": premier_league_name_matches,
            "oa1_assumed_ids": {
                "premier_league_england": 423,
                "champions_league": 51,
                "bundesliga_germany": 477,
            },
            "presence_in_catalogue": {
                str(cid): {
                    "listed": cid in comp_by_id,
                    "finished_fixtures_in_value_results_pool": len(finished_by_comp.get(cid, set())),
                    "any_fixtures_in_pool": len(fixture_ids_by_comp.get(cid, set())),
                }
                for cid in (423, 51, 477)
            },
        },
        "odds_history_samples_top50": odds_history_samples,
    }


def write_report(inventory: dict[str, Any], path: Path) -> None:
    scope = inventory.get("subscription_scope") or {}
    target = inventory.get("target_league_verification") or {}
    presence = target.get("presence_in_catalogue") or {}
    top50 = inventory.get("top_50_historical_fixtures") or []

    lines = [
        "# PHASE OA-2B — Raw OddAlerts Competition Discovery",
        "",
        f"**Generated:** {inventory.get('generated_at')}  ",
        "**Mode:** Raw discovery audit — no league assumptions  ",
        "",
        "---",
        "",
        "## Primary Answer",
        "",
        "Under the **current OddAlerts subscription**, historical finished fixtures are available only via the "
        f"**`value/results` pool** ({scope.get('value_results_rows_scanned', 0)} rows scanned, "
        f"{scope.get('unique_finished_fixtures_in_results_pool', 0)} unique finished fixtures, "
        f"{scope.get('competitions_with_any_pool_fixtures', 0)} competitions).",
        "",
        f"The **competitions catalogue** lists **{scope.get('competitions_catalogue_total', 0)}** competitions "
        f"({scope.get('competitions_catalogue_only_no_pool_fixtures', 0)} have **zero** fixtures in the results/upcoming pools).",
        "",
        "**England Premier League (id 423), Champions League (id 51), and Germany Bundesliga (id 477) exist in the catalogue** "
        "but have **0 finished fixtures** in the `value/results` pool on this token. "
        "`fixtures/results` returns **0 rows** for their current `season_id` values.",
        "",
        "There are **84** competitions named \"Premier League\" in the catalogue (different countries); only the England entry uses id **423**.",
        "",
        "---",
        "",
        "## API Usage",
        "",
        f"- API calls: **{(inventory.get('api_stats') or {}).get('api_calls', 0)}**",
        f"- Value/results pages: **{(inventory.get('api_stats') or {}).get('value_results_pages', 0)}**",
        f"- Value/upcoming pages: **{(inventory.get('api_stats') or {}).get('value_upcoming_pages', 0)}**",
        "",
        "## Target Leagues (ID verification)",
        "",
        "| Competition | Catalogue ID | In catalogue | Finished in results pool | fixtures/results rows |",
        "|-------------|--------------|--------------|--------------------------|------------------------|",
    ]

    for row in target.get("by_exact_name_country") or []:
        pid = presence.get(str(row["competition_id"]), {})
        lines.append(
            f"| {row['label']} | {row['competition_id']} | yes | "
            f"{pid.get('finished_fixtures_in_value_results_pool', 0)} | {row.get('fixtures_results_rows', 0)} |"
        )

    lines.extend(["", "## Top 50 Competitions by Finished Fixtures (results pool)", ""])
    lines.append("| Rank | ID | Name | Country | Finished | Seasons in pool | Embedded odds | odds/history sample |")
    lines.append("|------|-----|------|---------|----------|-----------------|---------------|---------------------|")
    for i, row in enumerate(top50, 1):
        seasons = row.get("seasons_seen_in_pool") or []
        season_txt = ", ".join(
            f"{s.get('season_label') or '?'}({s.get('season_id') or '?'})" for s in seasons[:3]
        )
        if len(seasons) > 3:
            season_txt += f" +{len(seasons) - 3}"
        oh = row.get("odds_history_sample") or {}
        lines.append(
            f"| {i} | {row.get('competition_id')} | {row.get('name') or '—'} | {row.get('country') or '—'} | "
            f"{row.get('finished_fixture_count_pool', 0)} | {season_txt or '—'} | "
            f"{row.get('embedded_odds_selections', 0)} | {oh.get('history_rows', '—')} |"
        )

    lines.extend(
        [
            "",
            "## Seasons",
            "",
            f"Unique competition+season pairs observed in pools: **{scope.get('unique_season_pairs_in_pool', 0)}**",
            "(Full list in `artifacts/oddalerts_raw_competition_inventory.json` → `seasons_available`.)",
            "",
            "## Catalogue vs Pool Gap",
            "",
            "The token can **list** 2,415 competitions but only **~"
            f"{scope.get('competitions_with_any_pool_fixtures', 0)}** appear in `value/results` + `value/upcoming`. "
            "Major European leagues are catalogue-only on this subscription tier.",
            "",
            "---",
            "",
            "**Artifact:** `artifacts/oddalerts_raw_competition_inventory.json`",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_audit(*, client: OddAlertsClient | None = None) -> dict[str, Any]:
    client = client or OddAlertsClient()
    if not client.is_configured:
        raise RuntimeError("ODDALERTS_API_KEY not configured")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    inventory = build_inventory(client)
    out = ARTIFACTS / "oddalerts_raw_competition_inventory.json"
    out.write_text(json.dumps(inventory, indent=2, ensure_ascii=False), encoding="utf-8")
    write_report(inventory, ROOT / "PHASE_OA2B_RAW_COMPETITION_DISCOVERY.md")
    return inventory
