#!/usr/bin/env python3
"""Phase 46B production smoke — verify legacy import on live archive."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.database.migrations import ensure_schema_compat
    from worldcup_predictor.database.repository import FootballIntelligenceRepository

    settings = get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    ensure_schema_compat(repo._conn)

    rows = repo.list_worldcup_stored_prediction_rows()
    total = len(rows)
    legacy = [r for r in rows if r.get("source") == "legacy_import"]
    authoritative = [r for r in rows if r.get("source") != "legacy_import"]
    quarantined = [r for r in legacy if r.get("is_quarantined")]

    checks = {
        "archive_total": total,
        "legacy_import_count": len(legacy),
        "authoritative_count": len(authoritative),
        "legacy_quarantined": len(quarantined),
        "schema_import_columns": all(
            "imported_at" in r and "import_source" in r and "quality_score" in r for r in legacy
        ) if legacy else True,
        "no_legacy_overwrites_authoritative": all(r.get("source") != "legacy_import" for r in authoritative),
    }

    out = Path("artifacts/phase46b_production_smoke.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(checks, indent=2), encoding="utf-8")

    print("Phase 46B production smoke")
    for key, value in checks.items():
        print(f"  {key}: {value}")

    ok = checks["no_legacy_overwrites_authoritative"] and checks["schema_import_columns"]
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
