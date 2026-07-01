"""Part D — Prediction data / training usage audit."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.connection import connect
from worldcup_predictor.owner_predict_eval.constants import ARTIFACTS_DIR, PHASE, with_safety_labels
from worldcup_predictor.owner_predict_eval.dates import date_tag, resolve_process_date
from worldcup_predictor.owner_predict_eval.db_helpers import latest_odds_snapshot, odds_source_label, table_exists


@dataclass
class DataUsageAuditResult:
    phase: str = PHASE
    audit_date: str = ""
    wde_retrained_with_historical_csv: bool = False
    historical_csv_promoted_from_staging: bool = False
    oddalerts_csv_odds_snapshots_used: bool = False
    oddalerts_csv_snapshot_count: int = 0
    ecse_oddalerts_mode: str = "shadow"
    fixtures_with_oddalerts_csv: list[int] = field(default_factory=list)
    fixtures_with_old_or_no_odds: list[dict[str, Any]] = field(default_factory=list)
    prerequisites_before_model_trained_claim: list[str] = field(default_factory=list)
    artifact_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return with_safety_labels(
            {
                "phase": self.phase,
                "audit_date": self.audit_date,
                "wde_retrained_with_historical_csv": self.wde_retrained_with_historical_csv,
                "historical_csv_promoted_from_staging": self.historical_csv_promoted_from_staging,
                "oddalerts_csv_odds_snapshots_used": self.oddalerts_csv_odds_snapshots_used,
                "oddalerts_csv_snapshot_count": self.oddalerts_csv_snapshot_count,
                "ecse_oddalerts_mode": self.ecse_oddalerts_mode,
                "fixtures_with_oddalerts_csv": self.fixtures_with_oddalerts_csv,
                "fixtures_with_old_or_no_odds": self.fixtures_with_old_or_no_odds,
                "prerequisites_before_model_trained_claim": self.prerequisites_before_model_trained_claim,
                "artifact_path": self.artifact_path,
            }
        )


def artifact_path_for(target: date) -> Path:
    return ARTIFACTS_DIR / f"prediction_data_usage_audit_{date_tag(target)}.json"


def _count_staging_historical(conn) -> int:
    total = 0
    for table in (
        "external_historical_csv_files",
        "external_match_history_staging",
        "external_match_odds_staging",
        "historical_csv_odds_imports",
    ):
        if table_exists(conn, table):
            total += int(conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"])
    return total


def _count_promoted_historical_fixtures(conn) -> int:
    if not table_exists(conn, "fixtures"):
        return 0
    row = conn.execute(
        """
        SELECT COUNT(*) c FROM fixtures
        WHERE source IN ('historical_csv', 'csv_registry', 'oddalerts_csv')
        """
    ).fetchone()
    return int(row["c"])


def _wde_retrained_with_historical_csv(conn) -> bool:
    """No production evidence of WDE retrain on historical CSV staging."""
    if table_exists(conn, "worldcup_stored_predictions"):
        row = conn.execute(
            """
            SELECT 1 FROM worldcup_stored_predictions
            WHERE import_source LIKE '%historical_csv%'
               OR invalidated_reason LIKE '%historical_csv_retrain%'
            LIMIT 1
            """
        ).fetchone()
        if row:
            return True
    retrain_artifact = Path("artifacts/wde_historical_csv_retrain.json")
    if retrain_artifact.exists():
        try:
            payload = json.loads(retrain_artifact.read_text(encoding="utf-8"))
            return bool(payload.get("completed"))
        except (json.JSONDecodeError, OSError):
            pass
    return False


def _ecse_oddalerts_mode(conn) -> str:
    shadow_tables = (
        "ecse_oddalerts_shadow_predictions",
        "ecse_oddalerts_shadow_monitor",
    )
    has_shadow = any(table_exists(conn, t) for t in shadow_tables)
    if not has_shadow:
        return "none"
    prod_from_oddalerts = 0
    if table_exists(conn, "ecse_prediction_snapshots"):
        rows = conn.execute(
            "SELECT prediction_source FROM ecse_prediction_snapshots WHERE prediction_source LIKE '%oddalerts%' LIMIT 5"
        ).fetchall()
        prod_from_oddalerts = len(rows)
    return "production" if prod_from_oddalerts > 0 else "shadow"


def audit_prediction_data_usage(
    *,
    date_arg: str = "today",
    timezone: str = "Europe/Vienna",
    fixture_ids: list[int] | None = None,
    settings: Settings | None = None,
) -> DataUsageAuditResult:
    settings = settings or get_settings()
    conn = connect(settings.sqlite_path)
    audit_date = resolve_process_date(date_arg, timezone)

    staging_count = _count_staging_historical(conn)
    promoted_count = _count_promoted_historical_fixtures(conn)
    historical_promoted = promoted_count > 0 and staging_count > 0

    wde_retrained = _wde_retrained_with_historical_csv(conn)
    mode = _ecse_oddalerts_mode(conn)

    oa_fixture_ids: list[int] = []
    old_or_none: list[dict[str, Any]] = []

    if fixture_ids:
        ids = [int(x) for x in fixture_ids]
    else:
        from worldcup_predictor.owner_predict_eval.fixture_discovery import artifact_path_for as fx_path

        path = fx_path(audit_date)
        if path.exists():
            payload = json.loads(path.read_text(encoding="utf-8"))
            ids = [int(f["fixture_id"]) for f in payload.get("fixtures") or []]
        else:
            ids = []

    oddalerts_count = 0
    if ids:
        for fid in ids:
            snap = latest_odds_snapshot(conn, fid)
            src = odds_source_label((snap or {}).get("payload"))
            if src == "oddalerts_csv_policy":
                oddalerts_count += 1
                oa_fixture_ids.append(fid)
            else:
                old_or_none.append({"fixture_id": fid, "odds_source": src})

    prerequisites = [
        "Promote historical CSV staging into production fixture/odds tables with validated crosswalk",
        "Run controlled WDE retrain/backtest using historical_csv_odds_imports labels",
        "Record retrain artifact (artifacts/wde_historical_csv_retrain.json) with completed=true",
        "Validate offline ROI and calibration before claiming production model uses new database",
        "Keep ECSE OddAlerts in shadow until owner promotion gate passes",
    ]

    result = DataUsageAuditResult(
        audit_date=audit_date.isoformat(),
        wde_retrained_with_historical_csv=wde_retrained,
        historical_csv_promoted_from_staging=historical_promoted,
        oddalerts_csv_odds_snapshots_used=oddalerts_count > 0,
        oddalerts_csv_snapshot_count=oddalerts_count,
        ecse_oddalerts_mode=mode,
        fixtures_with_oddalerts_csv=oa_fixture_ids,
        fixtures_with_old_or_no_odds=old_or_none,
        prerequisites_before_model_trained_claim=prerequisites,
    )

    path = artifact_path_for(audit_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    result.artifact_path = str(path)
    return result
