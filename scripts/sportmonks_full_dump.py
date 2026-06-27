"""
Sportmonks Full Data Dump — extract all odds, lineups, stats before cancelling plan.
Saves everything to local JSON files for offline backtest use.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SEASONS = [
    # (season_id, league, season_label)
    (26618, "world_cup",         "2026"),
    (18017, "world_cup",         "2022"),
    (892,   "world_cup",         "2018"),
    (23619, "champions_league",  "2024_2025"),
    (25580, "champions_league",  "2025_2026"),
    (23620, "europa_league",     "2024_2025"),
    (25582, "europa_league",     "2025_2026"),
    (23616, "conference_league", "2024_2025"),
    (25581, "conference_league", "2025_2026"),
]

INCLUDES = "odds;lineups;statistics;scores;participants;events"
PER_PAGE = 25
SLEEP_BETWEEN_PAGES = 0.5
SLEEP_BETWEEN_SEASONS = 2.0
OUTPUT_BASE = Path("data/sportmonks_dump")


def get_all_fixtures(provider, season_id: int) -> list[dict]:
    fixtures = []
    page = 1
    while True:
        status, payload, err = provider.safe_get("/fixtures", params={
            "filters": f"fixtureSeasons:{season_id}",
            "include": INCLUDES,
            "per_page": PER_PAGE,
            "page": page,
        })
        if status != 200 or not payload:
            logger.warning(f"  Page {page} failed (status={status}): {err}")
            break
        data = payload.get("data", [])
        if not data:
            break
        fixtures.extend(data)
        logger.info(f"  Page {page}: {len(data)} fixtures (total: {len(fixtures)})")
        has_more = payload.get("pagination", {}).get("has_more", False)
        if not has_more:
            break
        page += 1
        time.sleep(SLEEP_BETWEEN_PAGES)
    return fixtures


def save_season(fixtures: list[dict], league: str, season: str) -> dict:
    out_dir = OUTPUT_BASE / league / season
    out_dir.mkdir(parents=True, exist_ok=True)

    saved = 0
    skipped = 0
    failed = 0
    total_odds = 0
    total_lineups = 0
    total_stats = 0

    for fixture in fixtures:
        fid = fixture.get("id")
        if not fid:
            failed += 1
            continue

        out_file = out_dir / f"{fid}.json"
        if out_file.exists():
            skipped += 1
            continue

        try:
            out_file.write_text(
                json.dumps({"data": fixture}, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )
            saved += 1
            total_odds += len(fixture.get("odds", []))
            total_lineups += len(fixture.get("lineups", []))
            total_stats += len(fixture.get("statistics", []))
        except Exception as exc:
            logger.error(f"  Failed to save fixture {fid}: {exc}")
            failed += 1

    # manifest
    manifest = {
        "league": league,
        "season": season,
        "total_fixtures": len(fixtures),
        "saved": saved,
        "skipped": skipped,
        "failed": failed,
        "total_odds_rows": total_odds,
        "total_lineup_rows": total_lineups,
        "total_stat_rows": total_stats,
        "dumped_at": datetime.now(timezone.utc).isoformat(),
    }
    (out_dir / "_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return manifest


def run_dump():
    import sys
    sys.path.insert(0, ".")
    from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider
    from worldcup_predictor.config.settings import get_settings

    provider = SportmonksProvider(get_settings())
    summary = {}

    for season_id, league, season in SEASONS:
        logger.info(f"\n{'='*50}")
        logger.info(f"League: {league} | Season: {season} | season_id={season_id}")
        logger.info(f"{'='*50}")

        fixtures = get_all_fixtures(provider, season_id)
        if not fixtures:
            logger.warning(f"No fixtures found for season {season_id}")
            summary[f"{league}/{season}"] = {"error": "no fixtures"}
            continue

        logger.info(f"Total fixtures fetched: {len(fixtures)}")
        manifest = save_season(fixtures, league, season)
        summary[f"{league}/{season}"] = manifest

        logger.info(
            f"Saved: {manifest['saved']} fixtures | "
            f"odds={manifest['total_odds_rows']} | "
            f"lineups={manifest['total_lineup_rows']} | "
            f"stats={manifest['total_stat_rows']}"
        )
        time.sleep(SLEEP_BETWEEN_SEASONS)

    logger.info(f"\n{'='*50}")
    logger.info("DUMP COMPLETE — Summary:")
    for key, val in summary.items():
        if "error" in val:
            logger.info(f"  {key}: ERROR — {val['error']}")
        else:
            logger.info(
                f"  {key}: {val['saved']} saved | "
                f"odds={val['total_odds_rows']} | "
                f"lineups={val['total_lineup_rows']}"
            )

    print("\nFinal summary:")
    print(json.dumps(
        {k: {kk: vv for kk, vv in v.items() if kk in ("saved","skipped","failed","total_odds_rows","total_lineup_rows","total_stat_rows")} for k, v in summary.items() if "error" not in v},
        indent=2
    ))


if __name__ == "__main__":
    run_dump()
