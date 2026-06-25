"""Phase 54H-3 pressure backfill planning, estimates, and safe live probes."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.feature_store.pressure_store.repository import SportmonksPressureRepository
from worldcup_predictor.feature_store.pressure_store.sportmonks_pressure_store import SportmonksPressureFeatureStore
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider, redact_sportmonks_secrets

ARTIFACT_DIR = Path("artifacts/phase54h3_live_pressure_backfill_plan")

TARGET_LEAGUES: dict[int, str] = {
    2: "champions_league",
    5: "europa_league",
    2286: "conference_league",
    732: "world_cup",
}

_CACHE_ROOTS = (
    Path("data/egie/uefa_club/raw"),
    Path("data/feature_store/sportmonks_xg/raw"),
    Path("data/feature_store/sportmonks_pressure/raw"),
)

_FINISHED_STATE_IDS = {5, 7, 8}
_TOKEN_PATTERN = re.compile(r"(api_token|SPORTMONKS_API_TOKEN)=[^&\s\"']+", re.I)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _redact_obj(obj: Any, token: str = "") -> Any:
    if isinstance(obj, str):
        text = _TOKEN_PATTERN.sub("api_token=***REDACTED***", obj)
        return redact_sportmonks_secrets(text, token) if token else text
    if isinstance(obj, dict):
        return {k: _redact_obj(v, token) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact_obj(v, token) for v in obj]
    return obj


@dataclass
class TokenReadiness:
    scope: str
    token_present: bool
    token_length: int
    configured: bool
    pressure_probe_status: int | None
    pressure_probe_ok: bool
    pressure_rows: int
    error_redacted: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def check_token_readiness(settings: Settings | None = None, *, scope: str = "local") -> TokenReadiness:
    settings = settings or get_settings()
    token = settings.sportmonks_effective_token
    present = bool(token)
    configured = settings.sportmonks_configured
    status: int | None = None
    rows = 0
    err: str | None = None
    ok = False

    if configured:
        provider = SportmonksProvider(settings)
        fixture_id = _pick_known_pressure_fixture()
        status, payload, error = provider.safe_get(
            f"/fixtures/{fixture_id}",
            params={"include": "participants;pressure"},
        )
        data = (payload or {}).get("data") if isinstance(payload, dict) else None
        pres = (data or {}).get("pressure") if isinstance(data, dict) else None
        rows = len(pres) if isinstance(pres, list) else 0
        ok = status == 200 and rows > 0
        err = _redact_obj(error, token) if error else None

    return TokenReadiness(
        scope=scope,
        token_present=present,
        token_length=len(token) if present else 0,
        configured=configured,
        pressure_probe_status=status,
        pressure_probe_ok=ok,
        pressure_rows=rows,
        error_redacted=err,
    )


def _pick_known_pressure_fixture() -> int:
    for path in sorted(Path("data/egie/uefa_club/raw").glob("*.json")):
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        data = (blob.get("payload") or {}).get("data")
        if isinstance(data, dict) and data.get("pressure"):
            return int(blob.get("sportmonks_fixture_id") or data.get("id") or path.stem)
    summaries = SportmonksPressureRepository().list_fixture_summaries()
    if summaries:
        return int(summaries[0]["sportmonks_fixture_id"])
    return 19135063


def _load_fixture_index() -> list[dict[str, Any]]:
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    for root in _CACHE_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json"))[:3000]:
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            data = (blob.get("payload") or {}).get("data")
            if not isinstance(data, dict):
                continue
            sm_id = int(blob.get("sportmonks_fixture_id") or data.get("id") or path.stem)
            if sm_id in seen:
                continue
            seen.add(sm_id)
            league_id = int(data.get("league_id") or 0)
            events = data.get("events") or []
            has_events = isinstance(events, list) and len(events) > 0
            has_pressure_cache = bool(data.get("pressure"))
            has_xg = any(
                isinstance(s, dict)
                for s in (data.get("statistics") or [])
                if str(s.get("type_id") or "") in ("5304", "5305")
            ) or any(k in data for k in ("xG", "xg"))
            state_id = int(data.get("state_id") or 0)
            started = data.get("starting_at")
            rows.append(
                {
                    "sportmonks_fixture_id": sm_id,
                    "league_id": league_id,
                    "season_id": data.get("season_id"),
                    "competition_key": TARGET_LEAGUES.get(league_id, "other"),
                    "starting_at": started,
                    "state_id": state_id,
                    "finished": state_id in _FINISHED_STATE_IDS,
                    "has_events": has_events,
                    "has_pressure_cache": has_pressure_cache,
                    "has_xg_hint": has_xg,
                    "cache_path": str(path),
                }
            )
    return rows


def design_backfill_targets(
    *,
    minimum_new: int = 100,
    preferred_new: int = 300,
) -> dict[str, Any]:
    repo = SportmonksPressureRepository()
    imported = {int(s["sportmonks_fixture_id"]) for s in repo.list_fixture_summaries()}
    index = _load_fixture_index()

    by_league: dict[str, list[dict[str, Any]]] = {v: [] for v in TARGET_LEAGUES.values()}
    candidates: list[dict[str, Any]] = []

    for row in index:
        if row["league_id"] not in TARGET_LEAGUES:
            continue
        sm_id = row["sportmonks_fixture_id"]
        if sm_id in imported:
            continue
        row = {
            **row,
            "already_imported": False,
            "priority_score": (
                (3 if row["finished"] else 0)
                + (2 if row["has_events"] else 0)
                + (1 if row["has_xg_hint"] else 0)
                + (1 if not row["has_pressure_cache"] else 0)
            ),
        }
        candidates.append(row)
        comp = row["competition_key"]
        if comp in by_league:
            by_league[comp].append(row)

    def _sort_key(r: dict[str, Any]) -> tuple:
        return (
            -int(r.get("priority_score") or 0),
            str(r.get("starting_at") or ""),
        )

    for comp in by_league:
        by_league[comp] = sorted(by_league[comp], key=_sort_key)

    ranked = sorted(candidates, key=_sort_key)
    target_minimum = ranked[:minimum_new]
    target_preferred = ranked[:preferred_new]

    return {
        "generated_at": _utc_now(),
        "imported_count": len(imported),
        "candidate_total": len(candidates),
        "by_league_candidates": {k: len(v) for k, v in by_league.items()},
        "target_minimum_count": len(target_minimum),
        "target_preferred_count": len(target_preferred),
        "target_minimum_fixture_ids": [r["sportmonks_fixture_id"] for r in target_minimum],
        "target_preferred_fixture_ids": [r["sportmonks_fixture_id"] for r in target_preferred],
        "sample_per_league": {
            comp: (rows[0]["sportmonks_fixture_id"] if rows else None) for comp, rows in by_league.items()
        },
    }


def estimate_api_calls(target_design: dict[str, Any] | None = None) -> dict[str, Any]:
    target_design = target_design or design_backfill_targets()
    store = SportmonksPressureFeatureStore()
    pressure_cache = Path("data/feature_store/sportmonks_pressure/raw")
    uefa_cache = Path("data/egie/uefa_club/raw")

    min_ids = target_design.get("target_minimum_fixture_ids") or []
    pref_ids = target_design.get("target_preferred_fixture_ids") or []

    def _classify(ids: list[int]) -> dict[str, int]:
        cached_pressure = cached_uefa = needs_api = 0
        for sm_id in ids:
            if (pressure_cache / f"{sm_id}.json").is_file():
                cached_pressure += 1
            elif (uefa_cache / f"{sm_id}.json").is_file():
                cached_uefa += 1
            else:
                needs_api += 1
        return {
            "fixtures": len(ids),
            "pressure_cache_hits": cached_pressure,
            "uefa_cache_hits": cached_uefa,
            "api_calls_required": needs_api,
            "already_imported": int(target_design.get("imported_count") or 0),
        }

    min_est = _classify(min_ids)
    pref_est = _classify(pref_ids)
    avg_rows = 195  # from 54H store audit
    return {
        "generated_at": _utc_now(),
        "minimum_run": min_est,
        "preferred_run": pref_est,
        "expected_pressure_rows_minimum": min_est["api_calls_required"] * avg_rows,
        "expected_db_rows_minimum": min_est["api_calls_required"] * avg_rows,
        "quota_risk": (
            "LOW"
            if min_est["api_calls_required"] <= 120
            else "MEDIUM"
            if min_est["api_calls_required"] <= 300
            else "HIGH"
        ),
        "note": "Discovery pagination may add 1-4 calls per league if fixture list not cached.",
    }


@dataclass
class LiveProbeResult:
    label: str
    sportmonks_fixture_id: int
    league_id: int | None
    http_status: int | None
    pressure_rows: int
    participant_ids: list[int]
    unique_minutes: int
    minute_min: int | None
    minute_max: int | None
    cache_saved: bool
    error_redacted: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_live_probes(
    settings: Settings | None = None,
    *,
    max_calls: int = 5,
) -> list[LiveProbeResult]:
    settings = settings or get_settings()
    store = SportmonksPressureFeatureStore()
    provider = SportmonksProvider(settings)
    token = settings.sportmonks_effective_token

    probes_spec = [
        ("champions_league", _fixture_for_league(2, imported=False) or 19135063),
        ("europa_league", _fixture_for_league(5, imported=False) or 19135249),
        ("conference_league", _fixture_for_league(2286, imported=False) or 18151401),
        ("world_cup", _fixture_for_league(732, imported=False) or 19609127),
        ("control_not_imported", _fixture_for_league(2, imported=True) or 1058472),
    ]

    results: list[LiveProbeResult] = []
    calls = 0
    for label, sm_id in probes_spec[:max_calls]:
        if calls >= max_calls:
            break
        if not provider.is_configured:
            results.append(
                LiveProbeResult(
                    label=label,
                    sportmonks_fixture_id=sm_id,
                    league_id=None,
                    http_status=None,
                    pressure_rows=0,
                    participant_ids=[],
                    unique_minutes=0,
                    minute_min=None,
                    minute_max=None,
                    cache_saved=False,
                    error_redacted="token not configured",
                )
            )
            continue

        status, payload, error = provider.safe_get(
            f"/fixtures/{sm_id}",
            params={"include": "participants;pressure;events.type"},
        )
        calls += 1
        data = (payload or {}).get("data") if isinstance(payload, dict) else None
        cache_saved = False
        if isinstance(data, dict) and status == 200:
            store.save_cache(sm_id, payload if isinstance(payload, dict) else {"data": data})
            cache_saved = True

        pres = (data or {}).get("pressure") if isinstance(data, dict) else []
        pres = pres if isinstance(pres, list) else []
        participant_ids = sorted(
            {int(r.get("participant_id")) for r in pres if isinstance(r, dict) and r.get("participant_id") is not None}
        )
        minutes = sorted({int(r.get("minute") or 0) for r in pres if isinstance(r, dict)})
        league_id = int((data or {}).get("league_id") or 0) if isinstance(data, dict) else None

        results.append(
            LiveProbeResult(
                label=label,
                sportmonks_fixture_id=sm_id,
                league_id=league_id or None,
                http_status=status,
                pressure_rows=len(pres),
                participant_ids=participant_ids,
                unique_minutes=len(minutes),
                minute_min=minutes[0] if minutes else None,
                minute_max=minutes[-1] if minutes else None,
                cache_saved=cache_saved,
                error_redacted=_redact_obj(error, token) if error else None,
            )
        )
    return results


def _fixture_for_league(league_id: int, *, imported: bool) -> int | None:
    repo = SportmonksPressureRepository()
    imported_ids = {int(s["sportmonks_fixture_id"]) for s in repo.list_fixture_summaries()}
    for root in _CACHE_ROOTS:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.json"), reverse=True):
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            data = (blob.get("payload") or {}).get("data")
            if not isinstance(data, dict):
                continue
            if int(data.get("league_id") or 0) != league_id:
                continue
            sm_id = int(blob.get("sportmonks_fixture_id") or data.get("id") or path.stem)
            in_store = sm_id in imported_ids
            if imported and in_store:
                return sm_id
            if not imported and not in_store:
                return sm_id
    return None


def recommend_go(
    local: TokenReadiness,
    server: dict[str, Any] | None,
    probes: list[LiveProbeResult],
    target_design: dict[str, Any],
) -> str:
    server_ok = bool((server or {}).get("pressure_probe_ok"))
    local_ok = local.pressure_probe_ok
    if server_ok:
        return "READY_FOR_PRESSURE_BACKFILL"
    if local_ok:
        return "READY_FOR_PRESSURE_BACKFILL"
    if (server or {}).get("token_present") and not server_ok:
        if any(p.http_status == 403 for p in probes):
            return "PRESSURE_ACCESS_BLOCKED"
        return "TOKEN_NOT_READY"
    if local.token_present and not local_ok:
        if local.pressure_probe_status == 401:
            # Server may still be valid — caller should check server probe separately.
            if (server or {}).get("token_present"):
                return "TOKEN_NOT_READY"
            return "TOKEN_NOT_READY"
        if local.pressure_probe_status == 403:
            return "PRESSURE_ACCESS_BLOCKED"
    if target_design.get("candidate_total", 0) < 50:
        return "NEED_TARGET_FIXTURE_REPAIR"
    return "TOKEN_NOT_READY"


def run_plan(*, live_probes: bool = True, max_probe_calls: int = 5) -> dict[str, Any]:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    local = check_token_readiness(scope="local")
    server_path = Path("/opt/worldcup-predictor/.env.production")
    server_info: dict[str, Any] = {"checked": False, "note": "run server probe script on production host"}
    if server_path.is_file():
        server_info = {"checked": True, "env_file_exists": True, "note": "use phase54h3_server_pressure_probe.sh on server"}

    target = design_backfill_targets()
    estimate = estimate_api_calls(target)
    probes: list[LiveProbeResult] = []
    if live_probes:
        probes = run_live_probes(max_calls=max_probe_calls)

    out = {
        "generated_at": _utc_now(),
        "phase": "54H-3",
        "token_readiness": {
            "local": local.to_dict(),
            "server": server_info,
        },
        "target_design": target,
        "api_estimate": estimate,
        "live_probes": [p.to_dict() for p in probes],
        "recommendation": recommend_go(local, server_info, probes, target),
    }
    (ARTIFACT_DIR / "plan.json").write_text(json.dumps(_redact_obj(out), indent=2, default=str), encoding="utf-8")
    return out
