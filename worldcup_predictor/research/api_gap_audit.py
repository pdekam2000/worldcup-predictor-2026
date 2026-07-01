"""PHASE API-GAP-1 — Read-only ECSE data gap audit (no API calls)."""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PHASE = "API-GAP-1"
ECSE_FIXTURE_SQL = "SELECT DISTINCT registry_fixture_id FROM ecse_training_dataset"

SPORTMONKS_XG_CACHE_DIRS = (
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/egie/uefa_club/raw"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?", (name,)
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...] = ()) -> int:
    return int(conn.execute(sql, params).fetchone()[0])


def _sportmonks_cache_file_count() -> dict[str, int]:
    out: dict[str, int] = {}
    for root in SPORTMONKS_XG_CACHE_DIRS:
        if root.is_dir():
            out[str(root)] = len(list(root.glob("*.json")))
        else:
            out[str(root)] = 0
    out["total_unique_files"] = sum(out.values())
    return out


def _ecse_odds_gaps(conn: sqlite3.Connection) -> dict[str, Any]:
    ecse_n = _count(conn, "SELECT COUNT(1) FROM ecse_training_dataset")
    missing_draw = _count(
        conn,
        """
        SELECT COUNT(1) FROM ecse_training_dataset
        WHERE ft_draw_closing IS NULL OR ft_draw_closing <= 1.0
        """,
    )
    by_league = [
        dict(r)
        for r in conn.execute(
            """
            SELECT league, season, COUNT(1) AS fixtures,
                   SUM(CASE WHEN ft_draw_closing IS NULL OR ft_draw_closing <= 1.0 THEN 1 ELSE 0 END) AS missing_draw
            FROM ecse_training_dataset
            GROUP BY league, season
            ORDER BY fixtures DESC
            LIMIT 25
            """
        )
    ]
    prematch_draw = _count(
        conn,
        "SELECT COUNT(1) FROM historical_csv_odds_prematch_clean WHERE market='ft_result' AND selection='draw'",
    )
    prematch_home = _count(
        conn,
        "SELECT COUNT(1) FROM historical_csv_odds_prematch_clean WHERE market='ft_result' AND selection='home'",
    )
    prematch_away = _count(
        conn,
        "SELECT COUNT(1) FROM historical_csv_odds_prematch_clean WHERE market='ft_result' AND selection='away'",
    )
    bookmakers = [
        dict(r)
        for r in conn.execute(
            """
            SELECT bookmaker, COUNT(1) AS rows
            FROM historical_csv_odds_prematch_clean
            GROUP BY bookmaker ORDER BY rows DESC
            """
        )
    ]
    correct_score = [
        dict(r)
        for r in conn.execute(
            """
            SELECT market, COUNT(1) AS rows
            FROM historical_csv_odds_prematch_clean
            WHERE market LIKE '%correct%' OR market LIKE '%scoreline%'
            GROUP BY market
            """
        )
    ]
    return {
        "ecse_fixtures": ecse_n,
        "missing_ft_draw_closing": missing_draw,
        "missing_ft_draw_pct": round(100.0 * missing_draw / max(ecse_n, 1), 4),
        "prematch_ft_draw_rows": prematch_draw,
        "prematch_ft_home_rows": prematch_home,
        "prematch_ft_away_rows": prematch_away,
        "bookmakers": bookmakers,
        "correct_score_markets": correct_score,
        "by_league_season_top25": by_league,
        "draw_gap_root_cause": "SOURCE_EXPORT_GAP" if prematch_draw == 0 else "partial",
    }


def _xg_gaps(conn: sqlite3.Connection) -> dict[str, Any]:
    xg_rows = _count(conn, "SELECT COUNT(1) FROM xg_snapshots")
    cache = _sportmonks_cache_file_count()
    sm_enrich = _count(conn, "SELECT COUNT(1) FROM sportmonks_fixture_enrichment")
    ecse_with_xg = 0
    if _table_exists(conn, "api_gap_raw_payload"):
        ecse_with_xg = _count(
            conn,
            """
            SELECT COUNT(DISTINCT e.registry_fixture_id)
            FROM ecse_training_dataset e
            INNER JOIN api_gap_raw_payload p ON p.registry_fixture_id = e.registry_fixture_id
            WHERE p.data_type = 'xg'
            """,
        )
    return {
        "xg_snapshots_rows": xg_rows,
        "sportmonks_cache_files": cache,
        "sportmonks_fixture_enrichment_rows": sm_enrich,
        "ecse_registry_with_xg_staging": ecse_with_xg,
        "gap": "xg_snapshots empty but disk cache populated" if xg_rows == 0 and cache.get("total_unique_files", 0) > 0 else None,
    }


def _fixture_intel_gaps(conn: sqlite3.Connection) -> dict[str, Any]:
    enrichment_n = _count(conn, "SELECT COUNT(1) FROM fixture_enrichment")
    cols = {
        col: _count(
            conn,
            f"""
            SELECT COUNT(1) FROM fixture_enrichment
            WHERE {col} IS NOT NULL AND TRIM({col}) NOT IN ('', '{{}}', '[]', 'null')
            """,
        )
        for col in ("lineups_json", "statistics_json", "events_json", "odds_json")
    }
    goal_events = _count(conn, "SELECT COUNT(1) FROM fixture_goal_events") if _table_exists(conn, "fixture_goal_events") else 0
    odds_snapshots = _count(conn, "SELECT COUNT(1) FROM odds_snapshots")
    api_cache = [
        dict(r)
        for r in conn.execute(
            """
            SELECT endpoint, COUNT(1) AS rows
            FROM api_response_cache
            GROUP BY endpoint ORDER BY rows DESC
            """
        )
    ]
    shots_cache = _count(
        conn,
        "SELECT COUNT(1) FROM api_response_cache WHERE endpoint LIKE '%statistic%'",
    )
    registry_mapped = _count(
        conn,
        "SELECT COUNT(1) FROM historical_fixture_registry WHERE internal_fixture_id IS NOT NULL",
    )
    registry_total = _count(conn, "SELECT COUNT(1) FROM historical_fixture_registry")
    ecse_mapped = _count(
        conn,
        """
        SELECT COUNT(DISTINCT e.registry_fixture_id)
        FROM ecse_training_dataset e
        INNER JOIN historical_fixture_registry r ON r.registry_fixture_id = e.registry_fixture_id
        WHERE r.internal_fixture_id IS NOT NULL
        """,
    )
    return {
        "fixture_enrichment_rows": enrichment_n,
        "fixture_enrichment_coverage": cols,
        "fixture_goal_events_rows": goal_events,
        "odds_snapshots_rows": odds_snapshots,
        "api_response_cache_by_endpoint": api_cache,
        "api_cache_statistics_rows": shots_cache,
        "registry_production_mapped": registry_mapped,
        "registry_total": registry_total,
        "ecse_fixtures_production_mapped": ecse_mapped,
        "ecse_fixtures_unmapped": _count(conn, f"SELECT COUNT(1) FROM ({ECSE_FIXTURE_SQL})") - ecse_mapped,
    }


def _oddalerts_gaps(conn: sqlite3.Connection) -> dict[str, Any]:
    if not _table_exists(conn, "oddalerts_odds_history"):
        return {"table_exists": False}
    total = _count(conn, "SELECT COUNT(1) FROM oddalerts_odds_history")
    by_market = [
        dict(r)
        for r in conn.execute(
            """
            SELECT market, selection, COUNT(1) AS rows
            FROM oddalerts_odds_history
            GROUP BY market, selection ORDER BY rows DESC LIMIT 20
            """
        )
    ]
    draw_rows = _count(
        conn,
        "SELECT COUNT(1) FROM oddalerts_odds_history WHERE market IN ('ft_result','1x2','match_winner') AND selection='draw'",
    )
    cs_rows = _count(
        conn,
        "SELECT COUNT(1) FROM oddalerts_odds_history WHERE market LIKE '%correct%'",
    )
    bookmakers = [
        dict(r)
        for r in conn.execute(
            "SELECT bookmaker, COUNT(1) AS rows FROM oddalerts_odds_history GROUP BY bookmaker ORDER BY rows DESC"
        )
    ]
    return {
        "table_exists": True,
        "total_rows": total,
        "draw_rows": draw_rows,
        "correct_score_rows": cs_rows,
        "by_market_top20": by_market,
        "bookmakers": bookmakers,
        "fixture_map_rows": _count(conn, "SELECT COUNT(1) FROM oddalerts_fixture_map"),
    }


def _ecse_table_fingerprints(conn: sqlite3.Connection) -> dict[str, int]:
    tables = (
        "ecse_training_dataset",
        "ecse_lambda_features",
        "ecse_score_distributions",
        "ecse_score_distributions_dc",
    )
    return {t: _count(conn, f"SELECT COUNT(1) FROM {t}") if _table_exists(conn, t) else -1 for t in tables}


def _harvest_targets(conn: sqlite3.Connection) -> dict[str, Any]:
    """Fixtures needing targeted fetch (no API calls here)."""
    sm_missing_xg = []
    for row in conn.execute(
        """
        SELECT sportmonks_fixture_id, fixture_id_api_football
        FROM sportmonks_fixture_enrichment
        WHERE fixture_id_api_football IS NOT NULL
        """
    ):
        fid = int(row["fixture_id_api_football"])
        if not conn.execute("SELECT 1 FROM xg_snapshots WHERE fixture_id = ? LIMIT 1", (fid,)).fetchone():
            sm_missing_xg.append({"sportmonks_fixture_id": int(row["sportmonks_fixture_id"]), "fixture_id": fid})

    oa_candidates = []
    if _table_exists(conn, "oddalerts_odds_history"):
        for row in conn.execute(
            """
            SELECT DISTINCT oddalerts_fixture_id
            FROM oddalerts_odds_history
            WHERE market IN ('ft_result','1x2') AND selection IN ('home','away')
            LIMIT 500
            """
        ):
            oa_id = int(row["oddalerts_fixture_id"])
            has_draw = conn.execute(
                """
                SELECT 1 FROM oddalerts_odds_history
                WHERE oddalerts_fixture_id = ? AND selection = 'draw' LIMIT 1
                """,
                (oa_id,),
            ).fetchone()
            if not has_draw:
                oa_candidates.append(oa_id)

    af_fixtures_missing_stats = []
    for row in conn.execute(
        """
        SELECT f.fixture_id, f.competition_key
        FROM fixtures f
        LEFT JOIN fixture_enrichment e ON e.fixture_id = f.fixture_id
        WHERE f.is_placeholder = 0
          AND (e.statistics_json IS NULL OR TRIM(e.statistics_json) IN ('', '{}', '[]'))
        LIMIT 500
        """
    ):
        af_fixtures_missing_stats.append(dict(row))

    return {
        "sportmonks_xg_import_candidates": len(sm_missing_xg),
        "sportmonks_xg_sample": sm_missing_xg[:10],
        "oddalerts_draw_refetch_candidates": len(oa_candidates),
        "oddalerts_draw_sample": oa_candidates[:10],
        "api_football_stats_gap_candidates": len(af_fixtures_missing_stats),
        "api_football_stats_sample": af_fixtures_missing_stats[:10],
    }


def run_api_gap_audit(conn: sqlite3.Connection) -> dict[str, Any]:
    """Full read-only gap audit — must complete before any API harvest."""
    known_gaps = [
        "ft_draw odds missing (OddAlerts CSV export gap)",
        "correct_score market odds missing in prematch clean",
        "single bookmaker (Bet365) in CSV odds",
        "xg_snapshots empty vs Sportmonks disk cache",
        "ECSE registry mostly unmapped to production fixture_id",
        "lineups/injuries/events not in dedicated ECSE tables",
    ]
    return {
        "phase": PHASE,
        "generated_at_utc": _utc_now(),
        "audit_mode": "read_only_no_api",
        "known_ecse_gaps": known_gaps,
        "ecse_table_fingerprints": _ecse_table_fingerprints(conn),
        "odds_gaps": _ecse_odds_gaps(conn),
        "xg_gaps": _xg_gaps(conn),
        "fixture_intel_gaps": _fixture_intel_gaps(conn),
        "oddalerts_gaps": _oddalerts_gaps(conn),
        "harvest_targets": _harvest_targets(conn),
    }


def audit_markdown(audit: dict[str, Any]) -> str:
    odds = audit["odds_gaps"]
    xg = audit["xg_gaps"]
    intel = audit["fixture_intel_gaps"]
    oa = audit["oddalerts_gaps"]
    targets = audit["harvest_targets"]
    lines = [
        "# API-GAP-1 — ECSE Data Gap Audit Report",
        "",
        f"**Generated:** {audit['generated_at_utc']}  ",
        "**Mode:** Read-only (no API calls during audit)",
        "",
        "## Executive summary",
        "",
        "ECSE historical odds are dominated by **Bet365 CSV exports**. **FT draw** and **correct score** markets are absent at source. "
        f"**xg_snapshots** has **{xg['xg_snapshots_rows']}** rows while Sportmonks disk cache has "
        f"**{xg['sportmonks_cache_files'].get('total_unique_files', 0)}** JSON files. "
        f"Only **{intel['ecse_fixtures_production_mapped']:,}** of "
        f"**{odds['ecse_fixtures']:,}** ECSE fixtures map to production `fixture_id`.",
        "",
        "## ECSE table fingerprints (unchanged baseline)",
        "",
        "| Table | Rows |",
        "|-------|------|",
    ]
    for t, n in audit["ecse_table_fingerprints"].items():
        lines.append(f"| `{t}` | {n:,} |")
    lines.extend(
        [
            "",
            "## Odds gaps",
            "",
            f"- ECSE fixtures missing `ft_draw_closing`: **{odds['missing_ft_draw_closing']:,}** ({odds['missing_ft_draw_pct']}%)",
            f"- Prematch clean `ft_result` draw rows: **{odds['prematch_ft_draw_rows']}**",
            f"- Prematch `ft_result` home/away: **{odds['prematch_ft_home_rows']:,}** / **{odds['prematch_ft_away_rows']:,}**",
            f"- Correct score markets in prematch clean: **{len(odds['correct_score_markets'])}**",
            f"- Root cause tag: **{odds['draw_gap_root_cause']}**",
            "",
            "### Bookmakers (prematch clean)",
            "",
        ]
    )
    for b in odds["bookmakers"]:
        lines.append(f"- {b.get('bookmaker', 'unknown')}: {b.get('rows', 0):,} rows")
    lines.extend(
        [
            "",
            "## xG gaps",
            "",
            f"- `xg_snapshots`: **{xg['xg_snapshots_rows']}** rows",
            f"- Sportmonks cache files: **{json.dumps(xg['sportmonks_cache_files'])}**",
            f"- `sportmonks_fixture_enrichment`: **{xg['sportmonks_fixture_enrichment_rows']}** rows",
            "",
            "## Fixture intelligence gaps",
            "",
            f"- `fixture_enrichment` coverage: {json.dumps(intel['fixture_enrichment_coverage'])}",
            f"- `fixture_goal_events`: **{intel['fixture_goal_events_rows']:,}**",
            f"- `odds_snapshots`: **{intel['odds_snapshots_rows']:,}**",
            f"- API cache statistics rows: **{intel['api_cache_statistics_rows']}**",
            f"- Registry → production mapped: **{intel['registry_production_mapped']:,}** / **{intel['registry_total']:,}**",
            f"- ECSE fixtures production-mapped: **{intel['ecse_fixtures_production_mapped']:,}** "
            f"(unmapped **{intel['ecse_fixtures_unmapped']:,}**)",
            "",
            "## OddAlerts staging",
            "",
        ]
    )
    if oa.get("table_exists"):
        lines.append(f"- `oddalerts_odds_history`: **{oa['total_rows']}** rows, draw **{oa['draw_rows']}**, correct score **{oa['correct_score_rows']}**")
    else:
        lines.append("- `oddalerts_odds_history`: not present")
    lines.extend(
        [
            "",
            "## Targeted harvest queue (post-audit)",
            "",
            f"- Sportmonks xG import candidates: **{targets['sportmonks_xg_import_candidates']}**",
            f"- OddAlerts draw refetch candidates: **{targets['oddalerts_draw_refetch_candidates']}**",
            f"- API-Football stats gap candidates (production fixtures): **{targets['api_football_stats_gap_candidates']}**",
            "",
            "---",
            "",
            "*Audit only. No API calls. ECSE tables not modified.*",
        ]
    )
    return "\n".join(lines)
