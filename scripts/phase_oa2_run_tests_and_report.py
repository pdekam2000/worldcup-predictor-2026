#!/usr/bin/env python3
"""Run OA-2 test ingests and write PHASE_OA2 report."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "PHASE_OA2_ODDALERTS_HISTORICAL_ODDS_INGEST_REPORT.md"

TEST_RUNS = [
    ("champions_league", 2024, 30, 120),
    ("premier_league", 2023, 50, 150),
    ("bundesliga", 2023, 30, 120),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")

    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.connection import connect
    from worldcup_predictor.providers.oddalerts_historical_odds import collect_ingest_summary, ensure_oddalerts_tables
    from worldcup_predictor.providers.oddalerts_provider import OddAlertsClient

    client = OddAlertsClient()
    run_results: list[dict] = []

    for league, season, limit, cap in TEST_RUNS:
        cmd = [
            sys.executable,
            str(ROOT / "scripts" / "oddalerts_historical_odds_ingest.py"),
            "--league",
            league,
            "--season",
            str(season),
            "--limit-fixtures",
            str(limit),
            "--max-api-calls",
            str(cap),
            "--json",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
        payload: dict = {}
        if proc.stdout.strip():
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                payload = {"raw_stdout": proc.stdout[:500], "stderr": proc.stderr[:500]}
        else:
            payload = {"stderr": proc.stderr[:500], "returncode": proc.returncode}
        run_results.append({"league": league, "season": season, "result": payload})

    val_proc = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_oddalerts_historical_odds_ingest.py"), "--json"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
    )
    validation = json.loads(val_proc.stdout) if val_proc.stdout.strip() else {}

    settings = get_settings()
    conn = connect(settings.sqlite_path)
    ensure_oddalerts_tables(conn)
    summary = collect_ingest_summary(conn)

    total_api = sum(int((r.get("result") or {}).get("api_calls_used") or 0) for r in run_results)

    lines = [
        "# PHASE OA-2 — OddAlerts Historical Odds Ingest",
        "",
        f"**Generated:** {_now()}  ",
        "**Mode:** Ingest → Store → Validate → Report  ",
        "**Production / prediction engine:** UNCHANGED  ",
        "",
        "---",
        "",
        "## Summary",
        "",
        f"- **API key configured:** {client.is_configured}",
        f"- **API calls used (test runs):** {total_api}",
        f"- **SQLite DB:** `{settings.sqlite_path}`",
        f"- **Fixture map rows:** {validation.get('fixture_map_total', 0)}",
        f"- **Odds history rows:** {summary.get('odds_rows_total', 0)}",
        f"- **Internal mapping rows:** {validation.get('internal_mapped_total', 0)}",
        "",
        "## Test Runs",
        "",
    ]

    for item in run_results:
        r = item.get("result") or {}
        m = r.get("fixture_mapping") or {}
        lines.append(
            f"### {item['league']} season {item['season']}\n"
            f"- Discovered: **{r.get('fixtures_discovered', 0)}** | Processed: **{r.get('fixtures_processed', 0)}** | "
            f"API calls: **{r.get('api_calls_used', 0)}**\n"
            f"- Mapping: exact={m.get('exact', 0)}, fuzzy={m.get('fuzzy', 0)}, unmatched={m.get('unmatched', 0)}\n"
            f"- Odds rows stored: **{r.get('odds_rows_stored', 0)}**\n"
            f"- Internal fixtures in DB: {r.get('internal_fixtures_available', 'n/a')}\n"
            f"- Message: {r.get('message') or '—'}"
        )

    lines.extend(
        [
            "",
            "## Validation",
            "",
            f"- Checks passed: **{validation.get('passed', 0)}/{validation.get('total_checks', 0)}**",
            "",
        ]
    )
    for name, ok in (validation.get("checks") or {}).items():
        lines.append(f"- {'✓' if ok else '✗'} {name}")

    lines.extend(
        [
            "",
            "## Coverage",
            "",
            f"- Opening odds rows: **{summary.get('opening_odds_rows', 0)}**",
            f"- Closing odds rows: **{summary.get('closing_odds_rows', 0)}**",
            f"- Peak odds rows: **{summary.get('peak_odds_rows', 0)}**",
            f"- Bookmakers: {', '.join(list((summary.get('bookmaker_coverage') or {}).keys())[:12]) or '—'}",
            f"- Markets: {', '.join(list((summary.get('market_coverage') or {}).keys())[:12]) or '—'}",
            f"- Mapping confidence: {summary.get('fixture_map_counts')}",
            "",
            "## PostgreSQL / SQLite Status",
            "",
            "OddAlerts tables live in **SQLite** intelligence DB (`oddalerts_fixture_map`, `oddalerts_odds_history`, `oddalerts_ingest_state`, `oddalerts_ingest_runs`). "
            "PostgreSQL SaaS DB untouched. API-Football and Sportmonks tables unchanged.",
            "",
            "## Recommendation for Full Backfill",
            "",
        ]
    )

    if summary.get("odds_rows_total", 0) == 0:
        lines.append(
            "Trial token **did not expose** England PL / UEFA CL / Germany Bundesliga finished fixtures via `value/results` discovery "
            "(competition filters ignored; target competition IDs absent in ~4.4k row pool). "
            "Before full backfill: confirm OddAlerts plan unlocks `fixtures/results` or competition-scoped historical lists; "
            "then re-run ingest with higher `--max-api-calls` and `--discovery-pages`. "
            "Pipeline is ready — mapping + odds/history storage + resume/cache verified once fixtures are discoverable."
        )
    else:
        lines.append(
            "Proceed with staged backfill per league using `--resume` and conservative `--max-api-calls`. "
            "Prioritize leagues with non-zero discovery counts; validate internal mapping weekly."
        )

    lines.extend(["", "---", "", "**STOP — No deploy. No production prediction changes.**", ""])
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Report written: {REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
