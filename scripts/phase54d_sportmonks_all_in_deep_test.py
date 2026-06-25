#!/usr/bin/env python3
"""Phase 54D — Sportmonks ALL-IN paid feature deep test (audit only)."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_ROOT = ROOT / "artifacts" / "sportmonks_all_in_deep_test"
RAW_DIR = ARTIFACT_ROOT / "raw"

ResultClass = Literal[
    "accessible", "forbidden", "not_found", "empty", "error", "parse_error", "skipped", "cached"
]

_FINISHED_STATE_IDS = {5, 7, 8}
_UPCOMING_STATE_IDS = {1, 2, 3, 4, 6, 22, 25}  # NS, LIVE variants — best-effort

DEEP_FIXTURE_INCLUDES = (
    "participants;league;season;scores;state;"
    "events.type;events.period;events.player;"
    "statistics.type;lineups.player;lineups.details.type;"
    "formations;sidelined.sideline;coaches;venue;referees;"
    "xGFixture.type;pressure;"
    "odds.bookmaker;odds.market;predictions.type;metadata;form"
)

DEFAULT_LEAGUES: dict[str, int] = {
    "world_cup": 732,
    "european_championship": 1326,
    "champions_league": 2,
    "europa_league": 5,
    "premier_league": 8,
}

UEFA_CACHE_DIR = ROOT / "data" / "egie" / "uefa_club" / "raw"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(obj: Any, token: str) -> Any:
    from worldcup_predictor.providers.sportmonks_provider import redact_sportmonks_secrets

    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            lk = str(k).lower()
            if lk in {"api_token", "authorization", "token", "x-api-key"}:
                out[k] = "***REDACTED***"
                continue
            out[k] = _sanitize(v, token)
        return out
    if isinstance(obj, list):
        return [_sanitize(x, token) for x in obj]
    if isinstance(obj, str):
        return redact_sportmonks_secrets(obj, token)
    return obj


def _recursive_keys(obj: Any, prefix: str = "") -> list[str]:
    keys: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            path = f"{prefix}.{k}" if prefix else str(k)
            keys.append(path)
            keys.extend(_recursive_keys(v, path))
    elif isinstance(obj, list):
        if not obj:
            keys.append(f"{prefix}[]")
        else:
            keys.append(f"{prefix}[]")
            keys.extend(_recursive_keys(obj[0], f"{prefix}[]"))
    return keys


def _classify(status: int | None, payload: Any, error: str | None) -> ResultClass:
    if error and "timed out" in error.lower():
        return "error"
    if status in (401, 403):
        return "forbidden"
    if status == 404:
        return "not_found"
    if status is None or status >= 500:
        return "error"
    if status >= 400:
        return "error"
    if not isinstance(payload, dict):
        return "parse_error"
    data = payload.get("data")
    if data is None:
        msg = str(payload.get("message") or "")
        if "No result" in msg or not data:
            return "empty"
    if isinstance(data, list) and len(data) == 0:
        return "empty"
    if isinstance(data, dict) and not data:
        return "empty"
    return "accessible"


@dataclass
class LeagueSample:
    league_key: str
    league_id: int
    season_id: int | None = None
    season_name: str | None = None
    completed_fixture_id: int | None = None
    upcoming_fixture_id: int | None = None
    team_id: int | None = None
    player_id: int | None = None
    fixture_count: int = 0


@dataclass
class DeepTestRunner:
    max_calls: int
    save_raw: bool
    dry_run: bool
    token: str
    provider: Any
    manifest_path: Path
    calls_live: int = 0
    calls_cached: int = 0
    results: list[dict[str, Any]] = field(default_factory=list)
    key_inventory: dict[str, list[str]] = field(default_factory=dict)

    def _cache_path(self, path: str, params: dict[str, Any]) -> Path:
        key = json.dumps({"path": path, "params": {k: v for k, v in params.items() if k != "api_token"}}, sort_keys=True)
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", path.strip("/"))[:60]
        return RAW_DIR / f"{safe}_{digest}.json"

    def _append_manifest(self, entry: dict[str, Any]) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        with self.manifest_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

    def request(
        self,
        *,
        group: str,
        path: str,
        params: dict[str, Any] | None = None,
        league_key: str | None = None,
        note: str = "",
    ) -> tuple[int | None, Any | None, str | None, ResultClass, bool]:
        params = dict(params or {})
        if self.calls_live >= self.max_calls:
            rc: ResultClass = "skipped"
            self._append_manifest(
                {
                    "ts": _utc_now(),
                    "group": group,
                    "path": path,
                    "params": _sanitize(params, self.token),
                    "classification": rc,
                    "note": "api_cap_reached",
                }
            )
            return None, None, "max_calls_reached", rc, False

        cache_file = self._cache_path(path, params)
        if cache_file.is_file():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                self.calls_cached += 1
                status = cached.get("status_code")
                payload = cached.get("payload")
                error = cached.get("error")
                rc = _classify(status, payload, error)
                self._record(group, path, params, status, payload, error, rc, league_key, note, from_cache=True)
                return status, payload, error, rc, True
            except (json.JSONDecodeError, OSError):
                pass

        if self.dry_run:
            rc = "skipped"
            self._append_manifest({"ts": _utc_now(), "group": group, "path": path, "dry_run": True})
            return None, None, "dry_run", rc, False

        status, payload, error = self.provider.safe_get(path, params=params)
        self.calls_live += 1
        rc = _classify(status, payload, error)
        if self.save_raw:
            RAW_DIR.mkdir(parents=True, exist_ok=True)
            cache_file.write_text(
                json.dumps(
                    {
                        "fetched_at": _utc_now(),
                        "path": path,
                        "params": _sanitize(params, self.token),
                        "status_code": status,
                        "classification": rc,
                        "error": _sanitize(error, self.token) if error else None,
                        "payload": _sanitize(payload, self.token),
                    },
                    indent=2,
                    ensure_ascii=False,
                    default=str,
                ),
                encoding="utf-8",
            )
        self._record(group, path, params, status, payload, error, rc, league_key, note, from_cache=False)
        return status, payload, error, rc, False

    def _record(
        self,
        group: str,
        path: str,
        params: dict[str, Any],
        status: int | None,
        payload: Any,
        error: str | None,
        rc: ResultClass,
        league_key: str | None,
        note: str,
        *,
        from_cache: bool,
    ) -> None:
        data = payload.get("data") if isinstance(payload, dict) else None
        count = len(data) if isinstance(data, list) else (1 if isinstance(data, dict) and data else 0)
        entry = {
            "ts": _utc_now(),
            "group": group,
            "league_key": league_key,
            "path": path,
            "params": _sanitize(params, self.token),
            "status_code": status,
            "classification": rc,
            "record_count": count,
            "from_cache": from_cache,
            "note": note,
            "error": _sanitize(error, self.token) if error else None,
        }
        self.results.append(entry)
        self._append_manifest(entry)
        if rc == "accessible" and payload is not None:
            inv_key = f"{group}:{path}"
            self.key_inventory[inv_key] = sorted(set(_recursive_keys(_sanitize(payload, self.token))))


def _teams_from_fixture(row: dict[str, Any]) -> tuple[int | None, int | None, int | None]:
    home_id = away_id = None
    player_id = None
    for p in row.get("participants") or []:
        if not isinstance(p, dict):
            continue
        loc = str((p.get("meta") or {}).get("location") or "").lower()
        pid = p.get("id")
        if loc == "home" and pid:
            home_id = int(pid)
        elif loc == "away" and pid:
            away_id = int(pid)
    lineups = row.get("lineups") or []
    for lu in lineups:
        if isinstance(lu, dict) and lu.get("player_id"):
            player_id = int(lu["player_id"])
            break
        if isinstance(lu, dict):
            pl = lu.get("player")
            if isinstance(pl, dict) and pl.get("id"):
                player_id = int(pl["id"])
                break
    team_id = home_id or away_id
    return home_id, away_id, player_id or team_id


def discover_league(runner: DeepTestRunner, league_key: str, league_id: int) -> LeagueSample:
    sample = LeagueSample(league_key=league_key, league_id=league_id)
    _, payload, _, rc, _ = runner.request(
        group="discovery",
        path=f"/leagues/{league_id}",
        params={"include": "seasons;currentSeason"},
        league_key=league_key,
        note="league_metadata",
    )
    if rc != "accessible" or not isinstance(payload, dict):
        return sample
    data = payload.get("data") or {}
    seasons = data.get("seasons") or []
    current = data.get("currentseason") or data.get("currentSeason")
    if isinstance(current, dict) and current.get("id"):
        sample.season_id = int(current["id"])
        sample.season_name = str(current.get("name") or "")
    elif seasons:
        finished = sorted(
            [s for s in seasons if isinstance(s, dict) and s.get("finished")],
            key=lambda x: int(x.get("id") or 0),
            reverse=True,
        )
        current_list = [s for s in seasons if isinstance(s, dict) and s.get("is_current")]
        pick = (current_list or finished or seasons)[0]
        if isinstance(pick, dict):
            sample.season_id = int(pick.get("id") or 0) or None
            sample.season_name = str(pick.get("name") or "")

    filters = (
        f"fixtureSeasons:{sample.season_id}"
        if sample.season_id
        else f"fixtureLeagues:{league_id}"
    )
    _, fx_payload, _, fx_rc, _ = runner.request(
        group="fixtures_schedules",
        path="/fixtures",
        params={
            "filters": filters,
            "include": "participants;state;scores",
            "per_page": 50,
            "page": 1,
        },
        league_key=league_key,
        note="fixture_discovery",
    )
    if fx_rc != "accessible" or not isinstance(fx_payload, dict):
        return sample
    rows = fx_payload.get("data") or []
    sample.fixture_count = len(rows)
    finished = [r for r in rows if int(r.get("state_id") or 0) in _FINISHED_STATE_IDS]
    upcoming = [r for r in rows if int(r.get("state_id") or 0) not in _FINISHED_STATE_IDS]
    if finished:
        pick = finished[len(finished) // 2]
        sample.completed_fixture_id = int(pick.get("id") or 0) or None
        _, _, sample.player_id = _teams_from_fixture(pick)
        sample.team_id = _teams_from_fixture(pick)[0] or _teams_from_fixture(pick)[1]
    if upcoming:
        pick = upcoming[0]
        sample.upcoming_fixture_id = int(pick.get("id") or 0) or None
        if not sample.team_id:
            sample.team_id = _teams_from_fixture(pick)[0] or _teams_from_fixture(pick)[1]
    return sample


def _extract_fixture_fields(data: dict[str, Any]) -> dict[str, Any]:
    keys_present = sorted(data.keys())
    includes_found = {
        "participants": bool(data.get("participants")),
        "scores": bool(data.get("scores")),
        "state": bool(data.get("state")),
        "events": bool(data.get("events")),
        "statistics": bool(data.get("statistics")),
        "lineups": bool(data.get("lineups")),
        "formations": bool(data.get("formations")),
        "sidelined": bool(data.get("sidelined")),
        "coaches": bool(data.get("coaches")),
        "venue": bool(data.get("venue")),
        "referee": bool(data.get("referee") or data.get("referees")),
        "xGFixture": bool(data.get("xgfixture") or data.get("xGFixture")),
        "pressure": bool(data.get("pressure")),
        "odds": bool(data.get("odds")),
        "predictions": bool(data.get("predictions")),
        "metadata": bool(data.get("metadata")),
        "form": bool(data.get("form")),
    }
    events = data.get("events") or []
    event_fields: set[str] = set()
    for ev in events[:20]:
        if isinstance(ev, dict):
            event_fields.update(ev.keys())
    stats_types: set[str] = set()
    for st in data.get("statistics") or []:
        if isinstance(st, dict):
            tb = st.get("type")
            if isinstance(tb, dict):
                stats_types.add(str(tb.get("name") or tb.get("developer_name") or ""))
    odds_markets: set[str] = set()
    for ob in data.get("odds") or []:
        if isinstance(ob, dict):
            m = ob.get("market")
            if isinstance(m, dict):
                odds_markets.add(str(m.get("name") or m.get("developer_name") or ""))
            for mk in ob.get("markets") or []:
                if isinstance(mk, dict):
                    odds_markets.add(str(mk.get("name") or mk.get("developer_name") or ""))
    return {
        "keys_present": keys_present,
        "includes_found": includes_found,
        "event_field_keys": sorted(event_fields),
        "statistics_type_names": sorted(x for x in stats_types if x),
        "odds_market_names": sorted(x for x in odds_markets if x),
        "xg_row_count": len(data.get("xgfixture") or data.get("xGFixture") or []),
        "pressure_row_count": len(data.get("pressure") or []) if isinstance(data.get("pressure"), list) else int(bool(data.get("pressure"))),
        "predictions_count": len(data.get("predictions") or []),
        "lineups_count": len(data.get("lineups") or []),
        "events_count": len(events),
    }


def test_fixture_deep(runner: DeepTestRunner, sample: LeagueSample, fixture_id: int, label: str) -> dict[str, Any]:
    _, payload, err, rc, _ = runner.request(
        group="fixture_deep",
        path=f"/fixtures/{fixture_id}",
        params={"include": DEEP_FIXTURE_INCLUDES},
        league_key=sample.league_key,
        note=f"{label}_full_includes",
    )
    out: dict[str, Any] = {
        "fixture_id": fixture_id,
        "label": label,
        "classification": rc,
        "error": err,
    }
    if rc == "accessible" and isinstance(payload, dict) and isinstance(payload.get("data"), dict):
        out.update(_extract_fixture_fields(payload["data"]))
    return out


def _build_field_availability(cap: dict[str, Any]) -> dict[str, str]:
    def _st(*keys: str, default: str = "not_available") -> str:
        for k in keys:
            v = cap.get(k)
            if v in ("accessible", "partially_available"):
                return v
            if v == "forbidden":
                return "blocked"
            if v == "empty":
                return "empty"
        return default

    fa: dict[str, str] = {}
    fa["fixture_xg"] = _st("xg_fixture_include", "xg_expected_endpoint")
    fa["team_xg"] = _st("xg_fixture_include", "xg_expected_endpoint")
    fa["player_xg"] = _st("xg_fixture_include", default="unknown")
    fa["pressure_index"] = _st("pressure_include", "pressure_endpoint")
    fa["pressure_timeline"] = _st("pressure_include", default="unknown")
    fa["1x2_odds"] = _st("odds_include")
    fa["btts_odds"] = _st("odds_include", default="partially_available")
    fa["over_under_2_5_odds"] = _st("odds_include", default="partially_available")
    fa["lineups"] = _st("lineups_include")
    fa["injuries_sidelined"] = _st("sidelined_include")
    fa["match_statistics"] = _st("statistics_include")
    fa["dangerous_attacks"] = _st("statistics_include", default="partially_available")
    fa["events_timeline"] = _st("events_include")
    fa["player_stats"] = _st("player_endpoint", "topscorers_endpoint", default="unknown")
    fa["team_news"] = _st("news_endpoint", default="unknown")
    fa["sportmonks_predictions"] = _st("predictions_include")
    fa["standings"] = _st("standings_endpoint")
    fa["h2h"] = _st("h2h_endpoint")
    fa["recent_form"] = _st("form_include", default="partially_available")
    return fa


def analyze_local_uefa_cache() -> dict[str, Any]:
    """Offline capability probe from prior Sportmonks UEFA ingest (0 API calls)."""
    files = sorted(UEFA_CACHE_DIR.glob("*.json"))
    if not files:
        return {"available": False, "file_count": 0}

    from collections import Counter

    n_ok = 0
    league_ids: Counter[int] = Counter()
    include_hits: Counter[str] = Counter()
    xg_type_names: Counter[str] = Counter()
    stat_type_names: Counter[str] = Counter()
    event_type_names: Counter[str] = Counter()
    odds_market_names: Counter[str] = Counter()
    prediction_type_names: Counter[str] = Counter()
    fixtures_with_xg_value = 0
    fixtures_with_pressure = 0
    pressure_minute_rows = 0
    key_inventory: dict[str, list[str]] = {}
    sample_fixture_fields: dict[str, Any] = {}

    for path in files:
        try:
            blob = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if int(blob.get("status_code") or 0) != 200:
            continue
        data = (blob.get("payload") or {}).get("data")
        if not isinstance(data, dict):
            continue
        n_ok += 1
        league_ids[int(data.get("league_id") or 0)] += 1

        for field in (
            "participants",
            "scores",
            "state",
            "events",
            "statistics",
            "lineups",
            "formations",
            "sidelined",
            "coaches",
            "venue",
            "referee",
            "referees",
            "xgfixture",
            "xGFixture",
            "pressure",
            "odds",
            "predictions",
            "form",
        ):
            if data.get(field) or (field in ("xgfixture", "xGFixture") and (data.get("xgfixture") or data.get("xGFixture"))):
                include_hits[field] += 1

        extracted = _extract_fixture_fields(data)
        if not sample_fixture_fields:
            sample_fixture_fields = extracted

        has_xg = False
        for row in data.get("xgfixture") or data.get("xGFixture") or []:
            if not isinstance(row, dict):
                continue
            t = row.get("type") or {}
            name = str(t.get("name") or t.get("developer_name") or "")
            xg_type_names[name] += 1
            if "expected goals" in name.lower() and name.lower() not in {"expected goals against (xga)"}:
                val = (row.get("data") or {}).get("value")
                if val is not None:
                    has_xg = True
        if has_xg:
            fixtures_with_xg_value += 1

        pr = data.get("pressure")
        if isinstance(pr, list) and pr:
            fixtures_with_pressure += 1
            for row in pr:
                if isinstance(row, dict) and row.get("minute") is not None:
                    pressure_minute_rows += 1

        for ev in data.get("events") or []:
            if isinstance(ev, dict):
                t = ev.get("type") or {}
                if isinstance(t, dict):
                    event_type_names[str(t.get("name") or t.get("developer_name") or "")] += 1

        for st in data.get("statistics") or []:
            if isinstance(st, dict):
                t = st.get("type") or {}
                if isinstance(t, dict):
                    stat_type_names[str(t.get("name") or t.get("developer_name") or "")] += 1

        for ob in data.get("odds") or []:
            if isinstance(ob, dict):
                m = ob.get("market") or {}
                if isinstance(m, dict):
                    odds_market_names[str(m.get("name") or m.get("developer_name") or "")] += 1

        for pred in data.get("predictions") or []:
            if isinstance(pred, dict):
                t = pred.get("type") or {}
                if isinstance(t, dict):
                    prediction_type_names[str(t.get("name") or t.get("developer_name") or "")] += 1

        if len(key_inventory) < 3:
            inv_key = f"cache_fixture:{path.stem}"
            key_inventory[inv_key] = sorted(set(_recursive_keys(data)))

    rate = lambda k: round(include_hits[k] / n_ok, 3) if n_ok else 0.0
    cap_from_cache: dict[str, str] = {}
    if n_ok:
        cap_from_cache["lineups_include"] = "accessible" if rate("lineups") >= 0.5 else "empty"
        cap_from_cache["events_include"] = "accessible" if rate("events") >= 0.5 else "empty"
        cap_from_cache["statistics_include"] = "accessible" if rate("statistics") >= 0.5 else "empty"
        cap_from_cache["formations_include"] = "accessible" if rate("formations") >= 0.5 else "empty"
        cap_from_cache["odds_include"] = "accessible" if rate("odds") >= 0.5 else "empty"
        cap_from_cache["predictions_include"] = "accessible" if rate("predictions") >= 0.5 else "empty"
        cap_from_cache["pressure_include"] = "accessible" if fixtures_with_pressure >= n_ok * 0.5 else "empty"
        cap_from_cache["xg_fixture_include"] = (
            "accessible" if fixtures_with_xg_value >= max(1, n_ok * 0.05) else "partially_available"
        )
        cap_from_cache["form_include"] = "accessible" if rate("form") >= 0.3 else "empty"
        cap_from_cache["sidelined_include"] = "accessible" if rate("sidelined") >= 0.2 else "empty"

    return {
        "available": n_ok > 0,
        "file_count": len(files),
        "fixtures_analyzed": n_ok,
        "league_ids": dict(league_ids),
        "include_rates": {
            k: rate(k)
            for k in (
                "participants",
                "events",
                "lineups",
                "statistics",
                "formations",
                "xgfixture",
                "pressure",
                "odds",
                "predictions",
                "form",
                "sidelined",
            )
        },
        "fixtures_with_expected_xg": fixtures_with_xg_value,
        "fixtures_with_pressure": fixtures_with_pressure,
        "pressure_minute_rows": pressure_minute_rows,
        "xg_type_names_top": xg_type_names.most_common(20),
        "stat_type_names_top": stat_type_names.most_common(15),
        "event_type_names_top": event_type_names.most_common(12),
        "odds_market_names_top": odds_market_names.most_common(15),
        "prediction_type_names_top": prediction_type_names.most_common(12),
        "sample_fixture_fields": sample_fixture_fields,
        "capability_from_cache": cap_from_cache,
        "json_key_inventory": key_inventory,
        "source": "data/egie/uefa_club/raw",
        "note": "Prior UEFA CL/EL/Conference ingest with UEFA_FULL_INCLUDES — proves ALL-IN fixture includes when token valid.",
    }


def _merge_capability(live: dict[str, Any], cache: dict[str, Any]) -> dict[str, Any]:
    merged = dict(live)
    cache_cap = cache.get("capability_from_cache") or {}
    for k, v in cache_cap.items():
        if merged.get(k) in (None, "unknown", "empty", "forbidden", "error", "not_found"):
            merged[k] = v
        elif merged.get(k) == "partially_available" and v == "accessible":
            merged[k] = v
    merged["cache_supplement"] = cache
    return merged


def _build_egie_matrix(cap: dict[str, Any], fa: dict[str, str]) -> list[dict[str, Any]]:
    rows = [
        ("xG", "xg_fixture_include", "VERY HIGH", "First Goal Team, Goal Range, Team Goals", "54E"),
        ("Player xG", "xg_fixture_include", "HIGH", "Goalscorer, First Goalscorer", "54H"),
        ("Pressure Index", "pressure_include", "VERY HIGH", "Next Goal Team, Live Goal Probability", "54G"),
        ("Minute-level pressure", "pressure_include", "HIGH", "Goal Minute, In-play warning", "54G"),
        ("Odds 1X2", "odds_include", "HIGH", "First Goal Team, Confidence", "54J"),
        ("Odds O/U 2.5", "odds_include", "HIGH", "Goal Range", "54J"),
        ("BTTS odds", "odds_include", "MEDIUM", "Goal Range", "54J"),
        ("Goalscorer odds", "odds_include", "VERY HIGH", "Goalscorer Engine", "54H"),
        ("Lineups", "lineups_include", "HIGH", "Lineup strength, Goalscorer", "54E"),
        ("Injuries/Sidelined", "sidelined_include", "HIGH", "Lineup risk", "54E"),
        ("Match statistics", "statistics_include", "HIGH", "Pressure proxy, attacking form", "54E"),
        ("Dangerous attacks", "statistics_include", "MEDIUM", "Pressure proxy", "54E"),
        ("Events timeline", "events_include", "VERY HIGH", "Goal timing, First goal team", "54E"),
        ("Player stats", "player_endpoint", "VERY HIGH", "Goalscorer Engine", "54H"),
        ("News", "news_endpoint", "MEDIUM", "Motivation Agent", "54I"),
        ("Sportmonks Predictions", "predictions_include", "MEDIUM", "Benchmark only — not direct target", "54J"),
        ("Standings", "standings_endpoint", "HIGH", "Motivation Agent, Must-win", "54I"),
        ("H2H", "h2h_endpoint", "HIGH", "First Goal Team, Goal Range", "54E"),
        ("Recent Form", "form_include", "HIGH", "First Goal Team", "54E"),
    ]
    out: list[dict[str, Any]] = []
    for feature, cap_key, egie_val, best_use, phase in rows:
        status = cap.get(cap_key, "unknown")
        avail = fa.get(feature.lower().replace(" ", "_").replace("/", "_"), "unknown")
        if status == "accessible":
            coverage = "high"
            available = True
        elif status == "partially_available":
            coverage = "partial"
            available = True
        elif status in ("empty", "forbidden", "not_found", "error", "unknown", "skipped"):
            coverage = "none"
            available = False
        else:
            coverage = "partial"
            available = False
        out.append(
            {
                "feature": feature,
                "available": available,
                "coverage": coverage,
                "egie_value": egie_val,
                "best_use": best_use,
                "recommended_phase": phase,
                "capability_status": status,
                "field_classification": avail,
            }
        )
    return out


def run_deep_test(
    *,
    max_calls: int,
    leagues: dict[str, int],
    save_raw: bool,
    dry_run: bool,
    analyze_cache: bool = True,
) -> dict[str, Any]:
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

    settings = get_settings()
    provider = SportmonksProvider(settings)
    token = provider.api_token

    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    if save_raw:
        RAW_DIR.mkdir(parents=True, exist_ok=True)
    manifest_path = ARTIFACT_ROOT / "manifest.jsonl"
    if manifest_path.exists():
        manifest_path.unlink()

    runner = DeepTestRunner(
        max_calls=max_calls,
        save_raw=save_raw,
        dry_run=dry_run,
        token=token,
        provider=provider,
        manifest_path=manifest_path,
    )

    league_samples: list[LeagueSample] = []
    for lk, lid in leagues.items():
        league_samples.append(discover_league(runner, lk, lid))

    fixture_deep_results: list[dict[str, Any]] = []
    for sample in league_samples:
        fid = sample.completed_fixture_id or sample.upcoming_fixture_id
        if fid:
            fixture_deep_results.append(test_fixture_deep(runner, sample, fid, "primary"))
        if sample.upcoming_fixture_id and sample.upcoming_fixture_id != fid:
            fixture_deep_results.append(
                test_fixture_deep(runner, sample, sample.upcoming_fixture_id, "upcoming")
            )

    # Group endpoints — small candidate lists only
    primary = league_samples[0] if league_samples else None
    wc = next((s for s in league_samples if s.league_key == "world_cup"), league_samples[0] if league_samples else None)
    probe_fixture = (wc.completed_fixture_id or wc.upcoming_fixture_id) if wc else None
    probe_season = wc.season_id if wc else None
    team_a = wc.team_id if wc else None
    team_b = None
    if wc and wc.completed_fixture_id:
        _, payload, _, rc, _ = runner.request(
            group="discovery",
            path=f"/fixtures/{wc.completed_fixture_id}",
            params={"include": "participants"},
            league_key="world_cup",
            note="team_ids_for_h2h",
        )
        if rc == "accessible" and isinstance(payload, dict):
            data = payload.get("data") or {}
            tids = [
                int(p.get("id"))
                for p in data.get("participants") or []
                if isinstance(p, dict) and p.get("id")
            ]
            if len(tids) >= 2:
                team_a, team_b = tids[0], tids[1]

    extra_tests: list[tuple[str, str, dict[str, Any], str]] = [
        ("livescores", "/livescores/inplay", {}, "livescores_inplay"),
        ("livescores", "/livescores", {"include": "fixtures"}, "livescores_latest"),
        ("xg", "/expected/fixtures", {"per_page": 5}, "expected_fixtures_list"),
    ]
    if probe_fixture:
        extra_tests.append(
            ("xg", "/expected/fixtures", {"filters": f"fixtureIds:{probe_fixture}", "per_page": 5}, "expected_by_fixture")
        )
    if probe_season:
        extra_tests.append(
            ("standings", f"/standings/seasons/{probe_season}", {"include": "participant;details;form"}, "standings_season")
        )
        extra_tests.append(
            ("players", f"/topscorers/seasons/{probe_season}", {"include": "player;participant"}, "topscorers_season")
        )
    for news_path in ("/news", "/news/pre-match", "/pre-match-news"):
        extra_tests.append(("news", news_path, {"per_page": 5}, f"news_{news_path.strip('/').replace('/', '_')}"))
    if team_a:
        extra_tests.append(
            ("players", f"/teams/{team_a}", {"include": "players;latest"}, "team_squad")
        )
    if wc and wc.player_id:
        extra_tests.append(
            ("players", f"/players/{wc.player_id}", {"include": "statistics.details"}, "player_profile")
        )
    if team_a and team_b:
        extra_tests.append(
            ("h2h", f"/fixtures/head-to-head/{team_a}/{team_b}", {"include": "participants;scores"}, "head_to_head")
        )

    capability: dict[str, Any] = {}
    for group, path, params, note in extra_tests:
        _, _, _, rc, _ = runner.request(group=group, path=path, params=params, note=note)
        capability[f"{group}:{note}"] = rc

    # Summarize includes from deep fixture tests
    cap_summary: dict[str, str] = {}
    for r in fixture_deep_results:
        inc = r.get("includes_found") or {}
        for k, v in inc.items():
            key = f"{k}_include"
            if v:
                cap_summary[key] = "accessible"
            elif key not in cap_summary:
                cap_summary[key] = "empty"
    cap_summary.update(capability)
    if any((r.get("xg_row_count") or 0) > 0 for r in fixture_deep_results):
        cap_summary["xg_fixture_include"] = "accessible"
    if any((r.get("pressure_row_count") or 0) > 0 for r in fixture_deep_results):
        cap_summary["pressure_include"] = "accessible"
    cap_summary["xg_expected_endpoint"] = capability.get("xg:expected_by_fixture") or capability.get("xg:expected_fixtures_list") or "unknown"
    cap_summary["pressure_endpoint"] = cap_summary.get("pressure_include", "unknown")
    cap_summary["news_endpoint"] = next(
        (capability[k] for k in capability if k.startswith("news:") and capability[k] == "accessible"),
        next((capability[k] for k in capability if k.startswith("news:")), "not_found"),
    )
    cap_summary["standings_endpoint"] = capability.get("standings:standings_season", "unknown")
    cap_summary["player_endpoint"] = capability.get("players:player_profile", capability.get("players:team_squad", "unknown"))
    cap_summary["topscorers_endpoint"] = capability.get("players:topscorers_season", "unknown")
    cap_summary["h2h_endpoint"] = capability.get("h2h:head_to_head", "unknown")
    cap_summary["livescores_endpoint"] = capability.get("livescores:livescores_inplay") or capability.get("livescores:livescores_latest") or "unknown"

    cache_analysis = analyze_local_uefa_cache() if analyze_cache else {"available": False}
    cap_summary = _merge_capability(cap_summary, cache_analysis)
    if cache_analysis.get("json_key_inventory"):
        runner.key_inventory.update(cache_analysis["json_key_inventory"])

    field_availability = _build_field_availability(cap_summary)
    egie_matrix = _build_egie_matrix(cap_summary, field_availability)

    live_auth_ok = provider.is_configured and not any(
        r.get("status_code") == 401 or "Invalid token" in str(r.get("error") or "")
        or "not configured" in str(r.get("error") or "").lower()
        for r in runner.results
    )
    cache_ok = bool(cache_analysis.get("available"))

    all_in_checklist = {
        "livescores": cap_summary.get("livescores_endpoint") in ("accessible", "empty"),
        "lineups_events": cap_summary.get("lineups_include") == "accessible"
        and cap_summary.get("events_include") == "accessible",
        "statistics": cap_summary.get("statistics_include") == "accessible",
        "xg_pressure": cap_summary.get("xg_fixture_include") in ("accessible", "partially_available")
        or cap_summary.get("pressure_include") == "accessible",
        "odds_predictions": cap_summary.get("odds_include") == "accessible"
        or cap_summary.get("predictions_include") == "accessible",
        "news": cap_summary.get("news_endpoint") == "accessible",
    }
    all_in_checklist_live = dict(all_in_checklist)
    if not live_auth_ok and cache_ok:
        all_in_checklist["lineups_events"] = all_in_checklist["lineups_events"] or (
            cache_analysis.get("include_rates", {}).get("lineups", 0) >= 0.5
            and cache_analysis.get("include_rates", {}).get("events", 0) >= 0.5
        )
        all_in_checklist["statistics"] = all_in_checklist["statistics"] or (
            cache_analysis.get("include_rates", {}).get("statistics", 0) >= 0.5
        )
        all_in_checklist["xg_pressure"] = all_in_checklist["xg_pressure"] or (
            cache_analysis.get("fixtures_with_pressure", 0) > 0
            or cache_analysis.get("fixtures_with_expected_xg", 0) > 0
        )
        all_in_checklist["odds_predictions"] = all_in_checklist["odds_predictions"] or (
            cache_analysis.get("include_rates", {}).get("odds", 0) >= 0.5
            or cache_analysis.get("include_rates", {}).get("predictions", 0) >= 0.5
        )

    payload = {
        "generated_at": _utc_now(),
        "dry_run": dry_run,
        "max_calls": max_calls,
        "api_calls_live": runner.calls_live,
        "api_calls_cached": runner.calls_cached,
        "configured": provider.is_configured,
        "live_auth_ok": live_auth_ok,
        "cache_analysis_used": cache_ok,
        "auth_note": (
            "Live API reachable with valid token."
            if live_auth_ok
            else (
                "SPORTMONKS_API_TOKEN not configured — set SPORTMONKS_API_TOKEN in environment."
                if not provider.is_configured
                else "Live API returned 401 Invalid token — token missing/stale; UEFA cache supplement applied where available."
            )
        ),
        "leagues_tested": {s.league_key: {"league_id": s.league_id, **s.__dict__} for s in league_samples},
        "fixture_deep_results": fixture_deep_results,
        "capability_matrix": cap_summary,
        "all_in_subscription_checklist": all_in_checklist,
        "all_in_subscription_checklist_live_only": all_in_checklist_live,
        "cache_analysis": cache_analysis,
        "field_availability": field_availability,
        "egie_feature_value_matrix": egie_matrix,
        "endpoint_results": runner.results,
        "json_key_inventory": runner.key_inventory,
    }

    (ARTIFACT_ROOT / "capability_matrix.json").write_text(json.dumps(cap_summary, indent=2), encoding="utf-8")
    (ARTIFACT_ROOT / "field_availability.json").write_text(json.dumps(field_availability, indent=2), encoding="utf-8")
    (ARTIFACT_ROOT / "egie_feature_value_matrix.json").write_text(
        json.dumps(egie_matrix, indent=2), encoding="utf-8"
    )
    (ARTIFACT_ROOT / "json_key_inventory.json").write_text(
        json.dumps(runner.key_inventory, indent=2), encoding="utf-8"
    )
    if cache_analysis.get("available"):
        (ARTIFACT_ROOT / "cache_analysis.json").write_text(
            json.dumps(cache_analysis, indent=2, default=str), encoding="utf-8"
        )
    (ARTIFACT_ROOT / "deep_test_summary.json").write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 54D Sportmonks ALL-IN deep test")
    parser.add_argument("--max-calls", type=int, default=80)
    parser.add_argument("--worldcup-league-id", type=int, default=732)
    parser.add_argument("--euro-league-id", type=int, default=1326)
    parser.add_argument("--champions-league-id", type=int, default=2)
    parser.add_argument("--europa-league-id", type=int, default=5)
    parser.add_argument("--premier-league-id", type=int, default=8)
    parser.add_argument("--save-raw", type=str, default="true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--only-worldcup", action="store_true")
    parser.add_argument("--only-europe", action="store_true")
    parser.add_argument("--analyze-cache", dest="analyze_cache", action="store_true", default=True)
    parser.add_argument("--no-analyze-cache", dest="analyze_cache", action="store_false")
    args = parser.parse_args()

    leagues = {
        "world_cup": args.worldcup_league_id,
        "european_championship": args.euro_league_id,
        "champions_league": args.champions_league_id,
        "europa_league": args.europa_league_id,
        "premier_league": args.premier_league_id,
    }
    if args.only_worldcup:
        leagues = {"world_cup": args.worldcup_league_id}
    elif args.only_europe:
        leagues = {
            "european_championship": args.euro_league_id,
            "champions_league": args.champions_league_id,
            "europa_league": args.europa_league_id,
        }

    save_raw = str(args.save_raw).lower() in ("1", "true", "yes")
    result = run_deep_test(
        max_calls=args.max_calls,
        leagues=leagues,
        save_raw=save_raw,
        dry_run=args.dry_run,
        analyze_cache=args.analyze_cache,
    )
    print(
        json.dumps(
            {
                "artifact_root": str(ARTIFACT_ROOT),
                "api_calls_live": result.get("api_calls_live"),
                "api_calls_cached": result.get("api_calls_cached"),
                "all_in_checklist": result.get("all_in_subscription_checklist"),
                "leagues": list((result.get("leagues_tested") or {}).keys()),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
