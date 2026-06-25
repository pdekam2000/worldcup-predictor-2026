"""Phase 59D — Populate production predictions for Elite Shadow fixture set."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.admin.elite_shadow_comparison import EliteShadowComparisonService
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository

ROOT = Path(__file__).resolve().parents[2]
SHADOW_PREDICTIONS_PATH = ROOT / "data" / "shadow" / "elite_orchestrator_predictions.jsonl"
GENERATED_BY = "phase59d_shadow_comparison_population"
CACHE_SOURCE = "admin_shadow_comparison_population"
STORE_SOURCE = "phase59d_shadow_comparison_population"


@dataclass
class FixtureProductionStatus:
    fixture_id: int
    has_sqlite_store: bool = False
    has_file_cache: bool = False
    has_comparable_production: bool = False
    store_source: str | None = None
    action: Literal["existing", "missing", "skipped"] = "missing"


@dataclass
class PopulationResult:
    shadow_fixture_ids: list[int] = field(default_factory=list)
    shadow_market_rows: int = 0
    existing: list[FixtureProductionStatus] = field(default_factory=list)
    missing: list[FixtureProductionStatus] = field(default_factory=list)
    generated: list[dict[str, Any]] = field(default_factory=list)
    failed: list[dict[str, Any]] = field(default_factory=list)
    skipped_duplicates: list[int] = field(default_factory=list)
    api_calls_estimate: int = 0
    comparison_before: dict[str, Any] = field(default_factory=dict)
    comparison_after: dict[str, Any] = field(default_factory=dict)
    dry_run: bool = False


def load_shadow_fixture_ids(path: Path | None = None) -> tuple[list[int], int]:
    """Load deduplicated fixture IDs and market row count from shadow JSONL."""
    src = path or SHADOW_PREDICTIONS_PATH
    if not src.is_file():
        return [], 0
    fixture_ids: set[int] = set()
    market_rows = 0
    for line in src.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        market_rows += 1
        fid = int(row.get("fixture_id") or 0)
        if fid:
            fixture_ids.add(fid)
    return sorted(fixture_ids), market_rows


def _payload_has_comparable_production(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    dm = payload.get("detailed_markets")
    if isinstance(dm, dict) and dm:
        mw = dm.get("match_winner") if isinstance(dm.get("match_winner"), dict) else {}
        if mw.get("selection") or mw.get("probabilities"):
            return True
        fg = dm.get("first_goal") if isinstance(dm.get("first_goal"), dict) else {}
        if fg.get("team") or fg.get("minute_range") or fg.get("expected_minute"):
            return True
    return bool(payload.get("prediction"))


def audit_fixture_production(
    fixture_ids: list[int],
    *,
    settings: Settings | None = None,
) -> tuple[list[FixtureProductionStatus], list[FixtureProductionStatus]]:
    """Check SQLite store and file cache for each shadow fixture."""
    settings = settings or get_settings()
    from worldcup_predictor.admin.elite_shadow_comparison import _load_production_payload
    from worldcup_predictor.quota.prediction_cache import get_cached_prediction

    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    existing: list[FixtureProductionStatus] = []
    missing: list[FixtureProductionStatus] = []

    for fid in fixture_ids:
        row = repo.get_worldcup_stored_prediction(fid)
        payload, _ = _load_production_payload(fid)
        cached = get_cached_prediction(
            fid,
            competition_key="world_cup_2026",
            season=2026,
            locale="en",
            settings=settings,
        )
        status = FixtureProductionStatus(
            fixture_id=fid,
            has_sqlite_store=bool(row and row.get("payload_json")),
            has_file_cache=cached is not None,
            has_comparable_production=_payload_has_comparable_production(payload),
            store_source=(row or {}).get("source"),
        )
        if status.has_comparable_production:
            status.action = "existing"
            existing.append(status)
        else:
            missing.append(status)

    repo.close()
    return existing, missing


def populate_missing_production_predictions(
    *,
    dry_run: bool = False,
    settings: Settings | None = None,
    fixture_ids: list[int] | None = None,
) -> PopulationResult:
    """Generate production predictions for shadow fixtures missing stored picks."""
    settings = settings or get_settings()
    result = PopulationResult(dry_run=dry_run)

    ids, market_rows = load_shadow_fixture_ids()
    if fixture_ids:
        allowed = {int(x) for x in fixture_ids}
        ids = [fid for fid in ids if fid in allowed]
    result.shadow_fixture_ids = ids
    result.shadow_market_rows = market_rows

    comparison = EliteShadowComparisonService()
    result.comparison_before = comparison.build_comparison(limit=500).get("summary") or {}

    existing, missing = audit_fixture_production(ids, settings=settings)
    result.existing = existing
    result.missing = missing

    if dry_run:
        return result

    from worldcup_predictor.automation.worldcup_background.prediction_runner import build_api_payload
    from worldcup_predictor.automation.worldcup_background.prediction_store import WorldcupPredictionStore
    from worldcup_predictor.orchestration.predict_pipeline import PredictPipeline
    from worldcup_predictor.quota.prediction_cache import kickoff_from_payload, store_prediction
    from worldcup_predictor.config.competitions import get_competition

    store = WorldcupPredictionStore(settings)
    comp = get_competition("world_cup_2026")

    for status in missing:
        fid = status.fixture_id
        if store.get(fixture_id=fid):
            result.skipped_duplicates.append(fid)
            continue

        try:
            pipeline = PredictPipeline(settings, competition_key="world_cup_2026", locale="en")
            pipe_result = pipeline.run(fixture_id=fid, record_history=False)
            result.api_calls_estimate += 1
            if not pipe_result.success:
                result.failed.append({"fixture_id": fid, "reason": "pipeline_failed"})
                continue

            payload = build_api_payload(
                pipe_result,
                intelligence_report=pipe_result.intelligence_report,
                specialist_report=pipe_result.specialist_report,
            )
            payload["generated_by"] = GENERATED_BY
            payload["cache_source"] = CACHE_SOURCE
            payload["phase59d_population"] = {
                "purpose": "elite_shadow_comparison",
                "shadow_fixture_set": True,
            }

            kickoff = kickoff_from_payload(payload)
            if kickoff is None:
                repo = FootballIntelligenceRepository(settings.sqlite_path or None)
                try:
                    row = repo.get_fixture_row(fid)
                    if row and row.get("kickoff_utc"):
                        payload["kickoff_utc"] = str(row["kickoff_utc"])
                        kickoff = kickoff_from_payload(payload)
                finally:
                    repo.close()

            stored, cache_reason = store_prediction(
                fid,
                payload,
                competition_key=comp.key,
                season=comp.season,
                locale="en",
                kickoff_utc=kickoff,
                settings=settings,
                prediction_is_placeholder=bool(getattr(pipe_result.prediction, "is_placeholder", False)),
            )
            if not stored:
                result.failed.append({"fixture_id": fid, "reason": f"cache_blocked:{cache_reason}"})
                continue

            ok, store_reason = store.upsert(
                fid,
                payload,
                kickoff_utc=payload.get("kickoff_utc"),
                source=STORE_SOURCE,
                prediction_is_placeholder=bool(getattr(pipe_result.prediction, "is_placeholder", False)),
            )
            if not ok:
                result.failed.append({"fixture_id": fid, "reason": f"sqlite_blocked:{store_reason}"})
                continue

            result.generated.append(
                {
                    "fixture_id": fid,
                    "generated_by": GENERATED_BY,
                    "cache_source": CACHE_SOURCE,
                    "confidence": payload.get("confidence"),
                    "has_detailed_markets": bool(payload.get("detailed_markets")),
                }
            )
        except Exception as exc:
            result.failed.append({"fixture_id": fid, "reason": str(exc)})

    result.comparison_after = comparison.build_comparison(limit=500).get("summary") or {}
    return result


def population_summary_dict(result: PopulationResult) -> dict[str, Any]:
    return {
        "shadow_fixtures": len(result.shadow_fixture_ids),
        "shadow_market_rows": result.shadow_market_rows,
        "existing_count": len(result.existing),
        "missing_count": len(result.missing),
        "generated_count": len(result.generated),
        "failed_count": len(result.failed),
        "skipped_duplicates": len(result.skipped_duplicates),
        "api_calls_estimate": result.api_calls_estimate,
        "dry_run": result.dry_run,
        "comparison_before": result.comparison_before,
        "comparison_after": result.comparison_after,
        "generated": result.generated,
        "failed": result.failed,
    }
