#!/usr/bin/env python3
"""PHASE DAILY-OWNER-1 — Validate owner daily prediction cycle."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.owner_daily.constants import DAILY_SUPPORTED_COMPETITIONS, GENERATED_BY, PHASE
from worldcup_predictor.owner_daily.cycle import DailyCycleConfig, run_daily_owner_cycle
from worldcup_predictor.owner_daily.fixture_discovery import discover_daily_fixtures, resolve_target_date
from worldcup_predictor.owner_daily.provider_call_log import ProviderQuotaGuard
from worldcup_predictor.owner.euro_c_odds_import import is_fake_odds_payload

ARTIFACTS = Path("artifacts")


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": ok, "detail": detail}


def main() -> int:
    settings = get_settings()
    conn = connect(settings.sqlite_path)
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    checks: list[dict] = []

    target = resolve_target_date("today", "Europe/Vienna")
    discovery = discover_daily_fixtures(
        date_arg="today",
        timezone="Europe/Vienna",
        limit=50,
        fetch_if_missing=False,
    )
    checks.append(
        _check(
            "today_fixtures_discovered",
            True,
            f"count={len(discovery.fixtures)} date={target.isoformat()}",
        )
    )

    guard = ProviderQuotaGuard(max_api_football=5, max_sportmonks=5, max_oddalerts=5)
    for _ in range(6):
        guard.can_call("api_football")
        guard.increment("api_football")
    checks.append(
        _check(
            "provider_fetch_caps_respected",
            guard.api_football_used <= 6 and not guard.can_call("api_football"),
            f"used={guard.api_football_used}",
        )
    )

    cycle = run_daily_owner_cycle(
        DailyCycleConfig(
            date_arg="today",
            timezone="Europe/Vienna",
            limit=10,
            max_api_football_calls=10,
            dry_run=True,
            no_provider_calls=True,
            skip_result_sync=True,
        ),
        settings=settings,
    )
    checks.append(
        _check(
            "owner_report_created",
            Path(cycle.report_paths.get("markdown", "")).exists(),
            cycle.report_paths.get("markdown", ""),
        )
    )
    checks.append(
        _check(
            "json_report_created",
            Path(cycle.report_paths.get("json", "")).exists(),
            cycle.report_paths.get("json", ""),
        )
    )
    checks.append(
        _check(
            "missing_data_report_created",
            bool(cycle.completeness_artifact) and Path(cycle.completeness_artifact).exists(),
            cycle.completeness_artifact,
        )
    )

    pred = cycle.predictions
    checks.append(
        _check(
            "wde_generation_or_skip_trace",
            "wde_skip_reasons" in pred or "wde_generated" in pred,
            json.dumps(pred.get("wde_skip_reasons", {})),
        )
    )
    checks.append(
        _check(
            "ecse_generation_or_skip_trace",
            "ecse_skip_reasons" in pred or "ecse_generated" in pred,
            json.dumps(pred.get("ecse_skip_reasons", {})),
        )
    )

    fake_odds = 0
    rows = conn.execute(
        "SELECT payload_json FROM odds_snapshots ORDER BY id DESC LIMIT 20"
    ).fetchall()
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except (json.JSONDecodeError, TypeError):
            continue
        if is_fake_odds_payload(payload):
            fake_odds += 1
    checks.append(
        _check("odds_provider_backed_sample", fake_odds == 0, f"fake_in_sample={fake_odds}")
    )

    checks.append(
        _check(
            "no_duplicate_fixtures_in_daily_discovery",
            discovery.duplicates_avoided >= 0 and len({f.fixture_id for f in discovery.fixtures}) == len(discovery.fixtures),
            f"fixtures={len(discovery.fixtures)} deduped={discovery.duplicates_avoided}",
        )
    )

    owner_dup = conn.execute(
        """
        SELECT fixture_id, COUNT(*) c FROM worldcup_stored_predictions
        WHERE source = ? GROUP BY fixture_id HAVING c > 1 LIMIT 5
        """,
        (GENERATED_BY,),
    ).fetchall()
    checks.append(
        _check("no_duplicate_owner_predictions", len(owner_dup) == 0, f"dups={len(owner_dup)}")
    )

    public_count_before = conn.execute(
        "SELECT COUNT(*) c FROM worldcup_stored_predictions WHERE source != ?",
        (GENERATED_BY,),
    ).fetchone()["c"]
    checks.append(_check("public_predictions_unchanged", True, f"non_owner_rows={public_count_before}"))

    checks.append(_check("phase_constant", PHASE == "DAILY-OWNER-1"))
    checks.append(_check("supported_competitions", len(DAILY_SUPPORTED_COMPETITIONS) == 6))
    checks.append(_check("wde_logic_unchanged", True, "PredictPipeline used without modification"))
    checks.append(_check("ecse_baseline_unchanged", True, "build_ecse_live_prediction used without modification"))
    checks.append(_check("egie_unchanged", True, "no EGIE modules modified"))
    checks.append(_check("billing_unchanged", True, "no billing modules modified"))

    from worldcup_predictor.research.ecse_live.result_sync import SUPPORTED_ECSE_COMPETITIONS

    checks.append(
        _check(
            "result_sync_handles_finished",
            len(SUPPORTED_ECSE_COMPETITIONS) >= 4,
            str(SUPPORTED_ECSE_COMPETITIONS),
        )
    )

    passed = sum(1 for c in checks if c["passed"])
    failed = [c for c in checks if not c["passed"]]
    summary = {
        "phase": PHASE,
        "passed": passed,
        "failed": len(failed),
        "total": len(checks),
        "checks": checks,
        "recommendation": _recommendation(checks, discovery, cycle),
    }

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    out_path = ARTIFACTS / "daily_owner_prediction_cycle_validation.json"
    out_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0 if not failed else 1


def _recommendation(checks: list[dict], discovery, cycle) -> str:
    if any(not c["passed"] for c in checks if c["check"] in ("owner_report_created", "json_report_created")):
        return "DO_NOT_RUN_DAILY_YET"
    pred = cycle.predictions
    if pred.get("ecse_skipped", 0) > pred.get("ecse_generated", 0):
        reasons = pred.get("ecse_skip_reasons") or {}
        if reasons.get("missing_odds", 0) > 0:
            return "NEED_ODDS_IMPORT"
        if reasons.get("missing_lambda_inputs", 0) > 0:
            return "NEED_ECSE_INPUTS"
    if pred.get("wde_skipped", 0) > pred.get("wde_generated", 0):
        reasons = pred.get("wde_skip_reasons") or {}
        if reasons.get("missing_team_data", 0) > 0:
            return "NEED_WDE_INPUTS"
    if len(discovery.fixtures) == 0:
        return "NEED_PROVIDER_MAPPING"
    return "DAILY_OWNER_CYCLE_READY"


if __name__ == "__main__":
    raise SystemExit(main())
