"""Phase 46B — recover historical predictions into worldcup_stored_predictions."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.accuracy.history_store import DEFAULT_HISTORY_PATH, PredictionHistoryStore
from worldcup_predictor.accuracy.models import PredictionHistoryRecord
from worldcup_predictor.automation.worldcup_background.prediction_store_guard import (
    is_provider_env_placeholder_payload,
    payload_has_placeholder_data_reason,
)
from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.database.repository import FootballIntelligenceRepository

ImportSource = Literal["cache", "legacy_sqlite", "jsonl"]

SOURCE_PRIORITY: dict[ImportSource, int] = {"cache": 3, "legacy_sqlite": 2, "jsonl": 1}

KNOWN_TEST_FIXTURE_IDS = frozenset({99, 123, 1489393, 1539007})
MIN_IMPORT_QUALITY = 0.40
QUARANTINE_QUALITY_THRESHOLD = 0.55


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _main_prediction(payload: dict[str, Any]) -> str | None:
    pred = payload.get("prediction") or payload.get("one_x_two")
    if pred:
        return str(pred)
    mw = (payload.get("detailed_markets") or {}).get("match_winner") or {}
    if isinstance(mw, dict) and mw.get("selection"):
        return str(mw["selection"])
    return None


def _normalize_predicted_at(raw: Any) -> str:
    if raw is None:
        return _utc_now_iso()
    if isinstance(raw, (int, float)):
        try:
            return datetime.fromtimestamp(float(raw), tz=timezone.utc).replace(tzinfo=None).isoformat()
        except (OSError, OverflowError, ValueError):
            return _utc_now_iso()
    text = str(raw).strip()
    if not text:
        return _utc_now_iso()
    return text.replace("Z", "+00:00")[:26] if "T" in text else text


def _is_placeholder_teams(home: str | None, away: str | None) -> bool:
    h = str(home or "").strip().lower()
    a = str(away or "").strip().lower()
    return h in {"home", "away", ""} or a in {"home", "away", ""} or (h == "home" and a == "away")


@dataclass
class LegacyImportCandidate:
    fixture_id: int
    payload: dict[str, Any]
    import_source: ImportSource
    predicted_at: str
    kickoff_utc: str | None
    quality_score: float
    quarantine: bool
    quarantine_reason: str | None = None
    skip_reason: str | None = None


@dataclass
class LegacyImportResult:
    archive_total_before: int = 0
    archive_total_after: int = 0
    imported: int = 0
    quarantined: int = 0
    duplicates_skipped: int = 0
    not_recoverable_skipped: int = 0
    dry_run: bool = False
    errors: list[str] = field(default_factory=list)
    imported_fixture_ids: list[int] = field(default_factory=list)
    quarantined_fixture_ids: list[int] = field(default_factory=list)


def compute_quality_score(payload: dict[str, Any], import_source: ImportSource) -> float:
    score = 0.0
    if _main_prediction(payload):
        score += 0.25
    home = payload.get("home_team")
    away = payload.get("away_team")
    if home and away and not _is_placeholder_teams(str(home), str(away)):
        score += 0.15
    if _float(payload.get("confidence")) > 0:
        score += 0.15
    probs = payload.get("probabilities") or {}
    if isinstance(probs, dict) and probs.get("over_under_2_5"):
        score += 0.10
    if isinstance(probs, dict) and (probs.get("btts") or probs.get("both_teams_score")):
        score += 0.05
    dm = payload.get("detailed_markets")
    if isinstance(dm, dict) and dm:
        score += min(0.20, 0.04 * len([k for k, v in dm.items() if isinstance(v, dict)]))
    if payload.get("audit_trace") or payload.get("specialist_summary"):
        score += 0.05
    if import_source == "cache":
        score += 0.10
    elif import_source == "legacy_sqlite":
        score += 0.05
    elif import_source == "jsonl":
        score -= 0.10
    if payload.get("status") == "ok":
        score += 0.05
    if is_provider_env_placeholder_payload(payload) or payload_has_placeholder_data_reason(payload):
        score -= 0.25
    return round(min(1.0, max(0.0, score)), 4)


def _quarantine_decision(
    *,
    fixture_id: int,
    payload: dict[str, Any],
    import_source: ImportSource,
    quality_score: float,
) -> tuple[bool, str | None]:
    if fixture_id in KNOWN_TEST_FIXTURE_IDS:
        return True, "known_test_fixture"
    home = str(payload.get("home_team") or "")
    away = str(payload.get("away_team") or "")
    if _is_placeholder_teams(home, away):
        return True, "placeholder_teams"
    if quality_score < QUARANTINE_QUALITY_THRESHOLD:
        return True, "low_quality_score"
    if is_provider_env_placeholder_payload(payload):
        return True, "provider_env_placeholder"
    if import_source == "jsonl" and not payload.get("detailed_markets"):
        return True, "partial_jsonl_payload"
    return False, None


def payload_from_jsonl_record(record: PredictionHistoryRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "fixture_id": record.fixture_id,
        "home_team": record.home_team,
        "away_team": record.away_team,
        "prediction": record.predicted_1x2,
        "confidence": record.confidence_score,
        "status": "ok",
        "predicted_at": record.created_at,
        "probabilities": {
            "over_under_2_5": {"selection": record.predicted_over_under_2_5},
        },
        "generated_by": "legacy_import_jsonl",
    }
    if record.predicted_halftime_goals:
        payload.setdefault("detailed_markets", {})["halftime"] = {
            "selection": str(record.predicted_halftime_goals),
        }
    if record.predicted_first_goal_team:
        payload.setdefault("detailed_markets", {})["first_goal"] = {
            "selection": record.predicted_first_goal_team,
        }
    if record.predicted_scoreline:
        payload.setdefault("detailed_markets", {})["correct_scores"] = {
            "selection": record.predicted_scoreline,
        }
    if record.extended_markets_json:
        try:
            extended = json.loads(record.extended_markets_json)
            if isinstance(extended, dict):
                payload["detailed_markets"] = {**(payload.get("detailed_markets") or {}), **extended}
        except (json.JSONDecodeError, TypeError):
            pass
    return payload


def payload_from_legacy_sqlite(row: dict[str, Any], markets: dict[str, str]) -> dict[str, Any]:
    fixture_id = int(row["fixture_id"])
    p1x2 = markets.get("1x2") or markets.get("1X2") or ""
    payload: dict[str, Any] = {
        "fixture_id": fixture_id,
        "home_team": row.get("home_team"),
        "away_team": row.get("away_team"),
        "prediction": p1x2,
        "confidence": row.get("confidence"),
        "status": "ok",
        "predicted_at": row.get("created_at"),
        "probabilities": {},
        "generated_by": "legacy_import_sqlite",
    }
    ou = markets.get("over_under_2_5")
    if ou:
        payload["probabilities"]["over_under_2_5"] = {"selection": ou}
    btts = markets.get("btts") or markets.get("both_teams_score")
    if btts:
        payload["probabilities"]["btts"] = {"selection": btts}
    dm: dict[str, Any] = {}
    if markets.get("halftime_goals"):
        dm["halftime"] = {"selection": markets["halftime_goals"]}
    if markets.get("first_goal_team"):
        dm["first_goal"] = {"selection": markets["first_goal_team"]}
    if markets.get("scoreline_exact"):
        dm["correct_scores"] = {"selection": markets["scoreline_exact"]}
    if dm:
        payload["detailed_markets"] = dm
    return payload


def is_recoverable_jsonl(record: PredictionHistoryRecord) -> tuple[bool, str]:
    if not record.predicted_1x2 or not record.home_team or not record.away_team or not record.created_at:
        return False, "insufficient_jsonl_fields"
    if not record.predicted_over_under_2_5 and record.confidence_score <= 0:
        return False, "insufficient_jsonl_markets"
    return True, "ok"


def is_recoverable_cache_payload(payload: dict[str, Any]) -> tuple[bool, str]:
    if not payload.get("fixture_id"):
        return False, "missing_fixture_id"
    if not _main_prediction(payload):
        return False, "missing_1x2"
    return True, "ok"


def iter_cache_candidates(cache_dir: Path) -> list[LegacyImportCandidate]:
    out: list[LegacyImportCandidate] = []
    if not cache_dir.is_dir():
        return out
    for path in sorted(cache_dir.glob("*.json")):
        try:
            envelope = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        params = envelope.get("params") or {}
        payload = envelope.get("payload")
        if not isinstance(payload, dict):
            continue
        fixture_id = params.get("fixture_id") or payload.get("fixture_id")
        if fixture_id is None:
            continue
        fid = int(fixture_id)
        ok, reason = is_recoverable_cache_payload(payload)
        if not ok:
            continue
        body = dict(payload)
        body["fixture_id"] = fid
        predicted_at = _normalize_predicted_at(
            body.get("predicted_at") or body.get("generated_at") or envelope.get("cached_at")
        )
        kickoff = body.get("kickoff_utc")
        score = compute_quality_score(body, "cache")
        if score < MIN_IMPORT_QUALITY:
            continue
        quarantine, q_reason = _quarantine_decision(
            fixture_id=fid, payload=body, import_source="cache", quality_score=score
        )
        out.append(
            LegacyImportCandidate(
                fixture_id=fid,
                payload=body,
                import_source="cache",
                predicted_at=predicted_at,
                kickoff_utc=str(kickoff) if kickoff else None,
                quality_score=score,
                quarantine=quarantine,
                quarantine_reason=q_reason,
            )
        )
    return out


def iter_legacy_sqlite_candidates(repo: FootballIntelligenceRepository) -> list[LegacyImportCandidate]:
    out: list[LegacyImportCandidate] = []
    for fixture_id in repo.list_legacy_prediction_fixture_ids():
        bundle = repo.latest_prediction_for_fixture(fixture_id)
        if not bundle:
            continue
        row = bundle["prediction"]
        markets = bundle.get("markets") or {}
        body = payload_from_legacy_sqlite(row, markets)
        if not _main_prediction(body):
            continue
        score = compute_quality_score(body, "legacy_sqlite")
        if score < MIN_IMPORT_QUALITY:
            continue
        quarantine, q_reason = _quarantine_decision(
            fixture_id=fixture_id,
            payload=body,
            import_source="legacy_sqlite",
            quality_score=score,
        )
        out.append(
            LegacyImportCandidate(
                fixture_id=fixture_id,
                payload=body,
                import_source="legacy_sqlite",
                predicted_at=_normalize_predicted_at(row.get("created_at")),
                kickoff_utc=None,
                quality_score=score,
                quarantine=quarantine,
                quarantine_reason=q_reason,
            )
        )
    return out


def iter_jsonl_candidates(history_path: Path) -> list[LegacyImportCandidate]:
    out: list[LegacyImportCandidate] = []
    store = PredictionHistoryStore(history_path)
    for fixture_id, record in store.latest_by_fixture().items():
        ok, _ = is_recoverable_jsonl(record)
        if not ok:
            continue
        body = payload_from_jsonl_record(record)
        score = compute_quality_score(body, "jsonl")
        if score < MIN_IMPORT_QUALITY:
            continue
        quarantine, q_reason = _quarantine_decision(
            fixture_id=fixture_id,
            payload=body,
            import_source="jsonl",
            quality_score=score,
        )
        out.append(
            LegacyImportCandidate(
                fixture_id=int(fixture_id),
                payload=body,
                import_source="jsonl",
                predicted_at=_normalize_predicted_at(record.created_at),
                kickoff_utc=None,
                quality_score=score,
                quarantine=quarantine,
                quarantine_reason=q_reason,
            )
        )
    return out


def merge_candidates(*groups: list[LegacyImportCandidate]) -> list[LegacyImportCandidate]:
    """Pick best candidate per fixture — cache > legacy_sqlite > jsonl, then higher quality."""
    merged: dict[int, LegacyImportCandidate] = {}
    for group in groups:
        for candidate in group:
            existing = merged.get(candidate.fixture_id)
            if existing is None:
                merged[candidate.fixture_id] = candidate
                continue
            cand_rank = (SOURCE_PRIORITY[candidate.import_source], candidate.quality_score)
            exist_rank = (SOURCE_PRIORITY[existing.import_source], existing.quality_score)
            if cand_rank > exist_rank:
                merged[candidate.fixture_id] = candidate
    return sorted(merged.values(), key=lambda c: c.fixture_id)


def _enrich_payload_for_import(candidate: LegacyImportCandidate, *, imported_at: str) -> dict[str, Any]:
    body = dict(candidate.payload)
    body["legacy_import"] = {
        "imported_at": imported_at,
        "import_source": candidate.import_source,
        "quality_score": candidate.quality_score,
        "quarantine": candidate.quarantine,
        "quarantine_reason": candidate.quarantine_reason,
    }
    body["predicted_at"] = candidate.predicted_at
    return body


def run_legacy_prediction_import(
    *,
    settings: Settings | None = None,
    competition_key: str = "world_cup_2026",
    dry_run: bool = False,
    history_path: Path | str | None = None,
    cache_dir: Path | str | None = None,
) -> LegacyImportResult:
    settings = settings or get_settings()
    repo = FootballIntelligenceRepository(settings.sqlite_path or None)
    ensure_schema_compat(repo._conn)

    result = LegacyImportResult(dry_run=dry_run)
    result.archive_total_before = repo.count_worldcup_stored_predictions(
        competition_key=competition_key, include_quarantined=True
    )

    cache_path = Path(cache_dir or settings.prediction_cache_dir)
    hist_path = Path(history_path or DEFAULT_HISTORY_PATH)

    candidates = merge_candidates(
        iter_cache_candidates(cache_path),
        iter_legacy_sqlite_candidates(repo),
        iter_jsonl_candidates(hist_path),
    )

    existing_ids = {
        int(r["fixture_id"])
        for r in repo.list_worldcup_stored_prediction_rows(competition_key=competition_key)
    }
    imported_at = _utc_now_iso()

    for candidate in candidates:
        if candidate.fixture_id in existing_ids:
            result.duplicates_skipped += 1
            continue

        if dry_run:
            result.imported += 1
            if candidate.quarantine:
                result.quarantined += 1
                result.quarantined_fixture_ids.append(candidate.fixture_id)
            result.imported_fixture_ids.append(candidate.fixture_id)
            existing_ids.add(candidate.fixture_id)
            continue

        payload = _enrich_payload_for_import(candidate, imported_at=imported_at)
        try:
            inserted = repo.insert_worldcup_stored_prediction_legacy_import(
                fixture_id=candidate.fixture_id,
                payload=payload,
                kickoff_utc=candidate.kickoff_utc,
                predicted_at=candidate.predicted_at,
                imported_at=imported_at,
                import_source=candidate.import_source,
                quality_score=candidate.quality_score,
                is_quarantined=candidate.quarantine,
                quarantine_reason=candidate.quarantine_reason,
                competition_key=competition_key,
            )
        except Exception as exc:  # noqa: BLE001
            result.errors.append(f"fixture {candidate.fixture_id}: {exc}")
            continue

        if not inserted:
            result.duplicates_skipped += 1
            continue

        result.imported += 1
        result.imported_fixture_ids.append(candidate.fixture_id)
        existing_ids.add(candidate.fixture_id)
        if candidate.quarantine:
            result.quarantined += 1
            result.quarantined_fixture_ids.append(candidate.fixture_id)

    result.archive_total_after = repo.count_worldcup_stored_predictions(
        competition_key=competition_key, include_quarantined=True
    )
    return result
