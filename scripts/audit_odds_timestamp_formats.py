#!/usr/bin/env python3
"""ODDS-TIMESTAMP-NORMALIZATION-1 Part A — Audit odds_snapshots timestamp formats."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

if not os.environ.get("APP_ENV") and (ROOT / ".env.production").is_file():
    os.environ.setdefault("APP_ENV", "production")

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.odds.freshness_policy import classify_odds_freshness, parse_timestamp
from worldcup_predictor.odds.timestamp_normalization import (
    classify_timestamp_format,
    explain_timestamp_parse,
    parse_timestamp_utc,
)
from worldcup_predictor.research.wde_shadow_historical.helpers import connect_readonly, table_exists

OUTPUT_MD = ROOT / "ODDS_TIMESTAMP_NORMALIZATION_1_AUDIT.md"
OUTPUT_JSON = ROOT / "artifacts" / "odds_timestamp" / "odds_timestamp_normalization_1_audit.json"
TARGET_FIXTURE = 1567310
RECENT_LIMIT = 5000


def _infer_source(payload_json: str | None) -> str:
    if not payload_json:
        return "unknown"
    try:
        p = json.loads(payload_json)
        return str(p.get("source_provider") or p.get("source") or "unknown")
    except (json.JSONDecodeError, TypeError):
        return "unknown"


def run_audit(*, db_path: str, recent_limit: int = RECENT_LIMIT) -> dict:
    conn = connect_readonly(db_path)
    if not table_exists(conn, "odds_snapshots"):
        conn.close()
        return {"error": "odds_snapshots table missing"}

    cols = {r[1]: r[2] for r in conn.execute("PRAGMA table_info(odds_snapshots)")}
    rows = conn.execute(
        """
        SELECT id, fixture_id, competition_key, snapshot_at, payload_json
        FROM odds_snapshots
        ORDER BY id DESC
        LIMIT ?
        """,
        (recent_limit,),
    ).fetchall()

    families: Counter[str] = Counter()
    legacy_ok = 0
    legacy_fail = 0
    new_ok = 0
    new_fail = 0
    examples: dict[str, list[str]] = {}
    source_by_family: Counter[str] = Counter()
    target_row = None

    for row in rows:
        raw = row["snapshot_at"]
        family = classify_timestamp_format(raw)
        families[family] += 1
        src = _infer_source(row["payload_json"])
        source_by_family[f"{family}|{src}"] += 1

        if family not in examples or len(examples[family]) < 3:
            examples.setdefault(family, []).append(str(raw))

        # Legacy parser (pre-fix fromisoformat-only behavior)
        legacy_parsed = None
        if raw:
            try:
                from datetime import datetime, timezone

                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                legacy_parsed = dt
            except ValueError:
                legacy_parsed = None
        if legacy_parsed is None:
            legacy_fail += 1
        else:
            legacy_ok += 1

        if parse_timestamp_utc(raw) is None:
            new_fail += 1
        else:
            new_ok += 1

        if int(row["fixture_id"]) == TARGET_FIXTURE and target_row is None:
            target_row = {
                "id": row["id"],
                "fixture_id": row["fixture_id"],
                "snapshot_at_raw": raw,
                "sqlite_type": cols.get("snapshot_at", "unknown"),
                "source": src,
                "format_family": family,
                "legacy_parse_ok": legacy_parsed is not None,
                "new_parse_ok": parse_timestamp_utc(raw) is not None,
                "explain": explain_timestamp_parse(raw),
            }

    if target_row is None:
        t = conn.execute(
            "SELECT id, fixture_id, snapshot_at, payload_json FROM odds_snapshots WHERE fixture_id=? ORDER BY id DESC LIMIT 1",
            (TARGET_FIXTURE,),
        ).fetchone()
        if t:
            raw = t["snapshot_at"]
            target_row = {
                "id": t["id"],
                "fixture_id": t["fixture_id"],
                "snapshot_at_raw": raw,
                "sqlite_type": cols.get("snapshot_at", "unknown"),
                "source": _infer_source(t["payload_json"]),
                "format_family": classify_timestamp_format(raw),
                "legacy_parse_ok": parse_timestamp(raw) is not None,
                "new_parse_ok": parse_timestamp_utc(raw) is not None,
                "explain": explain_timestamp_parse(raw),
            }

    conn.close()

    return {
        "recent_rows_scanned": len(rows),
        "table_columns": cols,
        "format_families": dict(families),
        "legacy_parse_success": legacy_ok,
        "legacy_parse_fail": legacy_fail,
        "new_parse_success": new_ok,
        "new_parse_fail": new_fail,
        "examples_by_family": examples,
        "source_family_counts": dict(source_by_family),
        "fixture_1567310": target_row,
    }


def render_markdown(audit: dict) -> str:
    lines = [
        "# ODDS-TIMESTAMP-NORMALIZATION-1 — Timestamp Format Audit",
        "",
        f"- Rows scanned (recent): **{audit.get('recent_rows_scanned', 0)}**",
        f"- Legacy parser success: **{audit.get('legacy_parse_success', 0)}**",
        f"- Legacy parser fail → UNKNOWN risk: **{audit.get('legacy_parse_fail', 0)}**",
        f"- New parser success: **{audit.get('new_parse_success', 0)}**",
        f"- New parser fail: **{audit.get('new_parse_fail', 0)}**",
        "",
        "## Format families",
        "",
        "| family | count |",
        "|--------|------:|",
    ]
    for family, count in sorted((audit.get("format_families") or {}).items(), key=lambda x: -x[1]):
        lines.append(f"| {family} | {count} |")

    lines.extend(["", "## Example raw values", ""])
    for family, vals in sorted((audit.get("examples_by_family") or {}).items()):
        lines.append(f"### {family}")
        for v in vals:
            lines.append(f"- `{v}`")

    fx = audit.get("fixture_1567310") or {}
    lines.extend(
        [
            "",
            "## Fixture 1567310 (Colombia vs Ghana)",
            "",
            f"- snapshot_at raw: `{fx.get('snapshot_at_raw')}`",
            f"- SQLite column type: `{fx.get('sqlite_type')}`",
            f"- source: `{fx.get('source')}`",
            f"- format family: `{fx.get('format_family')}`",
            f"- legacy parse ok: **{fx.get('legacy_parse_ok')}**",
            f"- new parse ok: **{fx.get('new_parse_ok')}**",
            f"- explain: {fx.get('explain')}",
            "",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db-path", default=None)
    parser.add_argument("--recent-limit", type=int, default=RECENT_LIMIT)
    args = parser.parse_args()

    settings = get_settings()
    audit = run_audit(db_path=args.db_path or settings.sqlite_path, recent_limit=args.recent_limit)
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    OUTPUT_MD.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps({"audit_md": str(OUTPUT_MD), "audit_json": str(OUTPUT_JSON), **audit}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
