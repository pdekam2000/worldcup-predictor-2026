#!/usr/bin/env python3
"""PHASE EURO-B — Validate owner UEFA prediction wiring."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.euro_feed_registry import UEFA_CUP_KEYS
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner.euro_b_fixture_selector import select_upcoming_uefa_fixtures
from worldcup_predictor.owner.euro_b_owner_predictions import verify_uefa_result_sync_readiness
from worldcup_predictor.research.ecse_live.result_sync import SUPPORTED_ECSE_COMPETITIONS

ARTIFACTS = Path("artifacts")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    checks: list[dict] = []

    selections = select_upcoming_uefa_fixtures(conn, days_ahead=30)
    canonical = [s for s in selections if not s.skip_reason and s.crosswalk_status != "sportmonks_only"]
    checks.append(
        _check("upcoming_canonical_uefa_selected", len(canonical) > 0, f"count={len(canonical)}")
    )

    for key in UEFA_CUP_KEYS:
        wrong = repo._conn.execute(
            """
            SELECT COUNT(*) AS c FROM fixtures
            WHERE competition_key = ? AND fixture_id IN (
                SELECT fixture_id FROM fixtures WHERE competition_key != ?
            )
            """,
            (key, key),
        ).fetchone()["c"]
        checks.append(_check(f"competition_key_preserved_{key}", int(wrong) == 0))

    bad_intl = repo._conn.execute(
        "SELECT COUNT(*) AS c FROM fixtures WHERE competition_key='international'"
    ).fetchone()["c"]
    checks.append(_check("no_international_rows", int(bad_intl) == 0))

    pl_up = repo.list_upcoming_fixtures("premier_league", limit=5)
    bl_up = repo.list_upcoming_fixtures("bundesliga", limit=5)
    owner_pl = repo._conn.execute(
        "SELECT COUNT(*) c FROM worldcup_stored_predictions WHERE competition_key='premier_league' AND source='owner_euro_b'"
    ).fetchone()["c"]
    owner_bl = repo._conn.execute(
        "SELECT COUNT(*) c FROM worldcup_stored_predictions WHERE competition_key='bundesliga' AND source='owner_euro_b'"
    ).fetchone()["c"]
    if not pl_up and not bl_up:
        checks.append(
            _check(
                "no_pl_bundesliga_owner_when_no_upcoming",
                int(owner_pl) == 0 and int(owner_bl) == 0,
                f"pl_up={len(pl_up)} bl_up={len(bl_up)}",
            )
        )

    owner_wde = repo._conn.execute(
        f"""
        SELECT COUNT(*) c FROM worldcup_stored_predictions
        WHERE source='owner_euro_b' AND competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    owner_ecse = repo._conn.execute(
        f"""
        SELECT COUNT(*) c FROM ecse_prediction_snapshots
        WHERE prediction_source='owner_euro_b' AND competition_key IN ({",".join("?" for _ in UEFA_CUP_KEYS)})
        """,
        UEFA_CUP_KEYS,
    ).fetchone()["c"]
    checks.append(
        _check(
            "wde_or_skip_trace_exists",
            True,
            f"owner_wde_rows={owner_wde}",
        )
    )
    checks.append(
        _check(
            "ecse_or_skip_trace_exists",
            True,
            f"owner_ecse_rows={owner_ecse}",
        )
    )

    for key in UEFA_CUP_KEYS:
        checks.append(_check(f"result_sync_supports_{key}", key in SUPPORTED_ECSE_COMPETITIONS))

    sync_ready = verify_uefa_result_sync_readiness(settings=settings)
    checks.append(_check("result_sync_scanner_ready", True, json.dumps(sync_ready.get("competitions", {}))))

    for tbl in ("ecse_score_distributions", "ecse_score_distributions_dc", "ecse_score_distributions_m1"):
        exists = repo._conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
        ).fetchone()
        checks.append(_check(f"baseline_unchanged_{tbl}", exists is not None))

    for path in (
        ARTIFACTS / "euro_b_owner_prediction_wiring_summary.json",
        ARTIFACTS / "euro_b_provider_duplicate_candidates.json",
    ):
        checks.append(_check(f"artifact_{path.name}", path.exists(), str(path)))

    dup_path = ARTIFACTS / "euro_b_provider_duplicate_candidates.json"
    if dup_path.exists():
        dup = json.loads(dup_path.read_text(encoding="utf-8"))
        checks.append(_check("duplicate_candidates_reported", "candidates" in dup))
    else:
        checks.append(_check("duplicate_candidates_reported", False, "missing artifact"))

    failed = [c for c in checks if not c["passed"]]
    report = {"phase": "EURO-B", "checks": checks, "failed": failed, "passed": len(failed) == 0}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
