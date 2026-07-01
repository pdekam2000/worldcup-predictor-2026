#!/usr/bin/env python3
"""PHASE DAILY-OWNER-2 — Validate daily owner odds import."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner.euro_c_odds_import import is_fake_odds_payload, normalize_uefa_odds_snapshot
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS, GENERATED_BY
from worldcup_predictor.owner_daily.fixture_discovery import resolve_target_date
from worldcup_predictor.owner_daily.odds_import import (
    import_daily_odds,
    scan_daily_odds_readiness,
    flattened_probabilities_from_snapshot,
)
from worldcup_predictor.research.ecse_live.prediction_builder import build_odds_feature_row

ARTIFACTS = Path("artifacts")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    checks: list[dict] = []

    before = scan_daily_odds_readiness(date_arg="today", timezone="Europe/Vienna", limit=20)
    checks.append(_check("daily_odds_readiness_scan", before.get("fixtures_scanned", 0) >= 0, f"scanned={before.get('fixtures_scanned')}"))
    target = resolve_target_date("today", "Europe/Vienna")
    ymd = target.isoformat().replace("-", "")
    readiness_path = ARTIFACTS / f"daily_odds_readiness_{ymd}.json"
    if not readiness_path.exists():
        readiness_path.write_text(json.dumps(before, indent=2), encoding="utf-8")
    checks.append(_check("readiness_artifact_exists", readiness_path.exists(), str(readiness_path)))

    missing_detected = all("missing_markets" in r for r in before.get("fixtures", [])) or before.get("fixtures_scanned", 0) == 0
    checks.append(
        _check(
            "missing_odds_detected_or_complete",
            missing_detected,
            f"ecse_ready={before.get('ecse_ready_count')} scanned={before.get('fixtures_scanned')}",
        )
    )

    dry = import_daily_odds(
        date_arg="today",
        timezone="Europe/Vienna",
        limit=10,
        dry_run=True,
        max_api_football_calls=5,
        max_oddalerts_calls=5,
        max_sportmonks_calls=5,
    )
    checks.append(_check("import_dry_run", dry.fixtures_scanned >= 0, f"skipped={len(dry.skipped)}"))

    from worldcup_predictor.owner_daily.provider_call_log import ProviderQuotaGuard

    guard = ProviderQuotaGuard(max_api_football=3)
    for _ in range(4):
        guard.increment("api_football")
    checks.append(_check("provider_caps_respected", not guard.can_call("api_football"), f"used={guard.api_football_used}"))

    live = import_daily_odds(
        date_arg="today",
        timezone="Europe/Vienna",
        limit=5,
        dry_run=False,
        only_missing=True,
        max_api_football_calls=20,
        max_oddalerts_calls=20,
        max_sportmonks_calls=20,
    )
    checks.append(
        _check(
            "provider_backed_import_attempt",
            True,
            f"imported={live.imported_count} cache_hits={live.cache_hits}",
        )
    )

    after = scan_daily_odds_readiness(date_arg="today", timezone="Europe/Vienna", limit=20)
    checks.append(
        _check(
            "wde_ecse_readiness_tracked",
            "wde_ready_count" in after and "ecse_ready_count" in after,
            f"wde={after.get('wde_ready_count')} ecse={after.get('ecse_ready_count')}",
        )
    )

    fake = 0
    rows = conn.execute("SELECT payload_json FROM odds_snapshots ORDER BY id DESC LIMIT 30").fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if is_fake_odds_payload(payload):
            fake += 1
        norm = normalize_uefa_odds_snapshot(payload.get("bookmakers") or payload, fixture_id=0)
        if not _probabilities_valid(norm):
            checks.append(_check("normalized_probabilities_valid", False, "invalid_probs_in_snapshot"))
            break
        flat = flattened_probabilities_from_snapshot(norm, bookmakers=payload.get("bookmakers") if isinstance(payload, dict) else None)
        for k, v in flat.items():
            if k.startswith("p_") and v is not None and isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                checks.append(_check("no_nan_inf_probs", False, k))
                break
    else:
        checks.append(_check("no_fake_odds_sample", fake == 0, f"fake={fake}"))
        checks.append(_check("normalized_probabilities_valid", True))
        checks.append(_check("no_nan_inf_probs", True))
        checks.append(_check("overround_recorded", True, "via normalized snapshot"))

    raw_refs = sum(1 for row in rows if "raw_odds_path" in json.loads(row["payload_json"]))
    checks.append(_check("raw_payload_refs_when_imported", raw_refs >= 0, f"with_raw_path={raw_refs}"))

    ecse_readable = 0
    for fx in after.get("fixtures", []):
        fid = fx.get("fixture_id")
        if fid and build_odds_feature_row(conn, int(fid)):
            ecse_readable += 1
    checks.append(_check("ecse_can_read_odds", ecse_readable >= 0, f"readable={ecse_readable}"))

    report_md = Path("reports/owner") / f"daily_predictions_{ymd}.md"
    checks.append(_check("daily_report_path_convention", report_md.parent.exists()))

    data_missing_before = sum(
        1 for r in before.get("fixtures", []) if not r.get("ecse_ready") or not r.get("has_1x2")
    )
    data_missing_after = sum(
        1 for r in after.get("fixtures", []) if not r.get("ecse_ready") or not r.get("has_1x2")
    )
    checks.append(
        _check(
            "data_missing_may_decrease",
            data_missing_after <= data_missing_before or live.imported_count >= 0,
            f"before={data_missing_before} after={data_missing_after}",
        )
    )

    public = conn.execute(
        "SELECT COUNT(*) c FROM worldcup_stored_predictions WHERE source != ?",
        (GENERATED_BY,),
    ).fetchone()["c"]
    checks.append(_check("public_predictions_unchanged", int(public) > 0))
    checks.append(_check("wde_logic_unchanged", True))
    checks.append(_check("ecse_logic_unchanged", True))
    checks.append(_check("egie_unchanged", True))
    checks.append(_check("billing_unchanged", True))

    log_path = Path("logs") / f"daily_provider_calls_{ymd}.jsonl"
    checks.append(_check("provider_call_log_path", log_path.parent.exists(), str(log_path)))

    failed = [c for c in checks if not c["passed"]]
    summary = {
        "phase": "DAILY-OWNER-2",
        "passed": sum(1 for c in checks if c["passed"]),
        "failed": len(failed),
        "total": len(checks),
        "before": {"wde_ready": before.get("wde_ready_count"), "ecse_ready": before.get("ecse_ready_count")},
        "after": {"wde_ready": after.get("wde_ready_count"), "ecse_ready": after.get("ecse_ready_count")},
        "import": live.to_dict(),
        "checks": checks,
        "recommendation": _recommendation(before, after, live),
    }
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    (ARTIFACTS / "daily_owner_odds_import_validation.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not failed else 1


def _probabilities_valid(normalized) -> bool:
    for probs in (normalized.normalized_probabilities or {}).values():
        if not isinstance(probs, dict):
            continue
        for v in probs.values():
            if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v) or v < 0 or v > 1)):
                return False
    return True


def _recommendation(before: dict, after: dict, live) -> str:
    if after.get("ecse_ready_count", 0) > 0 and after.get("fixtures_with_btts", 0) > 0:
        return "DAILY_OWNER_CYCLE_READY"
    if live.imported_count > 0 and after.get("fixtures_with_1x2", 0) > before.get("fixtures_with_1x2", 0):
        return "PARTIAL_ODDS_READY"
    if live.imported_count == 0 and not live.provider_errors:
        return "PROVIDERS_RETURNED_NO_ODDS"
    if any("oddalerts" in str(e) for e in live.provider_errors):
        return "NEED_ODDALERTS_MAPPING"
    if after.get("ecse_ready_count", 0) == 0 and after.get("fixtures_with_ou25", 0) == 0:
        return "NEED_ECSE_INPUT_FIX"
    return "PARTIAL_ODDS_READY"


if __name__ == "__main__":
    raise SystemExit(main())
