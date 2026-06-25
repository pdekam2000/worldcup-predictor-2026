"""Sportmonks historical xG discovery engine (Phase 54F-3, audit only)."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.feature_store.xg_discovery.coverage_matrix import build_coverage_matrix
from worldcup_predictor.feature_store.xg_discovery.fixture_probe import probe_fixture_payload
from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider, redact_sportmonks_secrets
from worldcup_predictor.providers.sportmonks_xg_extraction import (
    XG_MATCH_FIXTURE_INCLUDES,
    XG_MATCH_FALLBACK_INCLUDES,
)

_FINISHED_STATE_IDS = {5, 7, 8}

TARGET_LEAGUES: dict[str, int] = {
    "world_cup": 732,
    "european_championship": 1326,
    "champions_league": 2,
    "europa_league": 5,
    "premier_league": 8,
}

OPTIONAL_LEAGUE_HINTS: dict[str, int] = {
    "conference_league": 2286,
    "nations_league": 1538,
    "euro_qualification": 1325,
}

XG_INCLUDES = ";".join(XG_MATCH_FIXTURE_INCLUDES) + ";xGFixture.type"
STATS_INCLUDES = "participants;state;statistics.type"
DEEP_INCLUDES = (
    "participants;league;season;state;scores;"
    "statistics.type;xGFixture.type;"
    "lineups.player;lineups.xGLineup.type;lineups.details.type"
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize(obj: Any, token: str) -> Any:
    if isinstance(obj, dict):
        return {k: _sanitize(v, token) for k, v in obj.items() if str(k).lower() not in {"api_token", "authorization"}}
    if isinstance(obj, list):
        return [_sanitize(x, token) for x in obj]
    if isinstance(obj, str):
        return redact_sportmonks_secrets(obj, token)
    return obj


@dataclass
class XgDiscoveryEngine:
    settings: Settings | None = None
    max_calls: int = 400
    samples_per_season: int = 5
    max_pages_per_season: int = 5
    artifact_dir: Path = field(default_factory=lambda: Path("artifacts/phase54f3_xg_discovery"))
    save_raw: bool = True

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.provider = SportmonksProvider(self.settings)
        self.token = self.provider.api_token if self.provider.is_configured else ""
        self.calls_live = 0
        self.calls_cached = 0
        self.raw_dir = self.artifact_dir / "raw"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.manifest_path = self.artifact_dir / "api_manifest.jsonl"

    def _cache_path(self, path: str, params: dict[str, Any]) -> Path:
        key = json.dumps({"path": path, "params": {k: v for k, v in params.items() if k != "api_token"}}, sort_keys=True)
        digest = hashlib.sha256(key.encode()).hexdigest()[:16]
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", path.strip("/"))[:50]
        return self.raw_dir / f"{safe}_{digest}.json"

    def request(self, path: str, *, params: dict[str, Any] | None = None, note: str = "") -> tuple[int | None, Any | None, str | None]:
        params = dict(params or {})
        cache_file = self._cache_path(path, params)
        if cache_file.is_file():
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                self.calls_cached += 1
                return cached.get("status_code"), cached.get("payload"), cached.get("error")
            except (json.JSONDecodeError, OSError):
                pass

        if self.calls_live >= self.max_calls:
            return None, None, "max_calls_reached"

        status, payload, error = self.provider.safe_get(path, params=params)
        self.calls_live += 1
        entry = {
            "ts": _utc_now(),
            "path": path,
            "params": _sanitize(params, self.token),
            "status_code": status,
            "error": _sanitize(error, self.token) if error else None,
            "note": note,
        }
        with self.manifest_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")

        if self.save_raw:
            cache_file.write_text(
                json.dumps(
                    {"status_code": status, "payload": _sanitize(payload, self.token), "error": entry["error"]},
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
        return status, payload, error

    def discover_league_metadata(self, league_key: str, league_id: int) -> dict[str, Any]:
        status, payload, error = self.request(
            f"/leagues/{league_id}",
            params={"include": "seasons;currentSeason"},
            note=f"league_meta:{league_key}",
        )
        out: dict[str, Any] = {
            "league_key": league_key,
            "league_id": league_id,
            "league_name": None,
            "seasons": [],
            "error": error,
            "status_code": status,
        }
        if status != 200 or not isinstance(payload, dict):
            return out
        data = payload.get("data") or {}
        out["league_name"] = data.get("name")
        seasons_raw = data.get("seasons") or []
        for s in seasons_raw:
            if not isinstance(s, dict):
                continue
            out["seasons"].append(
                {
                    "season_id": s.get("id"),
                    "name": s.get("name"),
                    "finished": s.get("finished"),
                    "is_current": s.get("is_current"),
                    "starting_at": s.get("starting_at"),
                    "ending_at": s.get("ending_at"),
                }
            )
        out["seasons"] = sorted(out["seasons"], key=lambda x: str(x.get("starting_at") or x.get("name") or ""))
        return out

    def count_season_fixtures(self, season_id: int) -> tuple[int, list[int]]:
        """Return (finished_fixture_count, sample_fixture_ids)."""
        finished_ids: list[int] = []
        total_finished = 0
        page = 1
        while page <= self.max_pages_per_season:
            status, payload, error = self.request(
                "/fixtures",
                params={
                    "filters": f"fixtureSeasons:{season_id}",
                    "include": "state",
                    "per_page": 50,
                    "page": page,
                },
                note=f"fixtures_season_{season_id}_p{page}",
            )
            if status != 200 or not isinstance(payload, dict):
                break
            rows = payload.get("data") or []
            if not isinstance(rows, list) or not rows:
                break
            for row in rows:
                if not isinstance(row, dict):
                    continue
                fid = int(row.get("id") or 0)
                if int(row.get("state_id") or 0) in _FINISHED_STATE_IDS:
                    total_finished += 1
                    finished_ids.append(fid)
            pagination = payload.get("pagination") or {}
            if not pagination.get("has_more"):
                break
            page += 1
        # spread sample picks
        sample: list[int] = []
        if finished_ids:
            n = min(self.samples_per_season, len(finished_ids))
            step = max(1, len(finished_ids) // n)
            sample = [finished_ids[i] for i in range(0, len(finished_ids), step)][:n]
        return total_finished, sample

    def fetch_fixture(self, fixture_id: int, *, include: str) -> dict[str, Any] | None:
        status, payload, error = self.request(
            f"/fixtures/{fixture_id}",
            params={"include": include},
            note=f"fixture_{fixture_id}",
        )
        if status != 200 or not isinstance(payload, dict):
            return None
        data = payload.get("data")
        return data if isinstance(data, dict) else None

    def audit_season(
        self,
        league_key: str,
        league_id: int,
        league_name: str | None,
        season: dict[str, Any],
    ) -> dict[str, Any]:
        season_id = int(season.get("season_id") or 0)
        total, sample_ids = self.count_season_fixtures(season_id)
        probes: list[dict[str, Any]] = []
        team_xg = player_xg = xgot = unknown = 0
        sample_with_xg = 0

        for fid in sample_ids:
            if self.calls_live >= self.max_calls:
                break
            raw = self.fetch_fixture(fid, include=XG_INCLUDES)
            if not raw:
                continue
            probe = probe_fixture_payload(raw)
            probe["fixture_id"] = fid
            probes.append(probe)
            if probe.get("has_team_xg"):
                sample_with_xg += 1
                team_xg += 1
            if probe.get("has_player_xg"):
                player_xg += 1
            if probe.get("has_team_xgot"):
                xgot += 1
            unknown += sum((probe.get("unknown_type_counts") or {}).values())

        sampled = len(probes)
        extrapolated_with_xg = 0
        estimation = "none"
        if sampled > 0 and total > 0:
            rate = sample_with_xg / sampled
            extrapolated_with_xg = int(round(rate * total))
            estimation = "sample_extrapolation"

        return {
            "league_key": league_key,
            "league_id": league_id,
            "league_name": league_name,
            "season_id": season_id,
            "season_name": season.get("name"),
            "season_start": season.get("starting_at"),
            "season_end": season.get("ending_at"),
            "total_fixtures": total,
            "fixtures_sampled": sampled,
            "sample_with_xg": sample_with_xg,
            "fixtures_with_xg": extrapolated_with_xg,
            "team_xg_count": team_xg,
            "player_xg_count": player_xg,
            "xgot_count": xgot,
            "unknown_metric_count": unknown,
            "estimation_method": estimation,
            "sample_fixture_ids": sample_ids,
            "probes": probes,
        }

    def endpoint_audit(self, fixture_id: int) -> dict[str, Any]:
        """Compare include strategies on one fixture."""
        variants = {
            "xg_fixture_includes": XG_INCLUDES,
            "statistics_only": STATS_INCLUDES,
            "deep_combo": DEEP_INCLUDES,
            "fallback_includes": ";".join(XG_MATCH_FALLBACK_INCLUDES),
        }
        results: dict[str, Any] = {"fixture_id": fixture_id, "variants": {}}
        for name, inc in variants.items():
            if self.calls_live >= self.max_calls:
                results["variants"][name] = {"status": "skipped", "reason": "max_calls"}
                continue
            raw = self.fetch_fixture(fixture_id, include=inc)
            if not raw:
                results["variants"][name] = {"status": "error"}
                continue
            probe = probe_fixture_payload(raw)
            results["variants"][name] = {
                "status": "ok",
                "has_team_xg": probe.get("has_team_xg"),
                "has_xgfixture_block": probe.get("has_xgfixture_block"),
                "has_statistics": probe.get("has_statistics"),
                "has_lineup_xg": probe.get("has_lineup_xg"),
                "metric_counts": probe.get("metric_counts"),
                "parse_source": probe.get("parse_source"),
                "expected_row_count": probe.get("expected_row_count"),
            }
        return results

    def api_capability_audit(self, season_rows: list[dict[str, Any]], endpoint_results: list[dict[str, Any]]) -> dict[str, str]:
        any_xg = any(int(r.get("sample_with_xg") or 0) > 0 for r in season_rows)
        all_seasons_sampled = all(int(r.get("fixtures_sampled") or 0) > 0 for r in season_rows if int(r.get("total_fixtures") or 0) > 0)
        league_wide = len({r.get("league_id") for r in season_rows if int(r.get("sample_with_xg") or 0) > 0}) >= 2

        def _yn(partial_cond: bool, yes_cond: bool) -> str:
            if yes_cond:
                return "YES"
            if partial_cond:
                return "PARTIAL"
            return "NO"

        fixture_ok = any(
            v.get("has_team_xg")
            for er in endpoint_results
            for v in (er.get("variants") or {}).values()
            if isinstance(v, dict)
        )
        player_ok = any(int(r.get("player_xg_count") or 0) > 0 for r in season_rows)

        return {
            "historical_xg_retrievable": _yn(any_xg, any_xg and all_seasons_sampled),
            "league_wide_xg": _yn(any_xg, league_wide),
            "season_wide_xg": _yn(any_xg, any(int(r.get("total_fixtures") or 0) > 0 for r in season_rows)),
            "fixture_level_xg": _yn(fixture_ok, fixture_ok),
            "player_xg_retrievable": _yn(player_ok, player_ok),
        }

    def root_cause_analysis(
        self,
        league_meta: list[dict[str, Any]],
        season_rows: list[dict[str, Any]],
        endpoint_results: list[dict[str, Any]],
        importer_comparison: dict[str, Any],
    ) -> dict[str, Any]:
        causes: list[str] = []
        evidence: list[str] = []

        total_sampled = sum(int(r.get("fixtures_sampled") or 0) for r in season_rows)
        total_with_xg = sum(int(r.get("sample_with_xg") or 0) for r in season_rows)
        api_rate = (total_with_xg / total_sampled) if total_sampled else 0.0

        if api_rate < 0.15:
            causes.append("A")
            evidence.append(f"API sample xG rate only {api_rate:.1%} across {total_sampled} probes")
        else:
            evidence.append(f"API sample xG rate {api_rate:.1%} — Sportmonks has meaningful xG")

        cache_team_xg = int(importer_comparison.get("uefa_cache_team_xg_fixtures") or 0)
        cache_scanned = int(importer_comparison.get("uefa_cache_scanned") or 0)
        if cache_scanned and cache_team_xg / cache_scanned < api_rate * 0.5:
            causes.append("B")
            evidence.append(
                f"UEFA cache team xG {cache_team_xg}/{cache_scanned} vs API sample rate {api_rate:.1%} — importer/cache gap"
            )

        seasons_no_xg = [r for r in season_rows if int(r.get("total_fixtures") or 0) > 0 and int(r.get("sample_with_xg") or 0) == 0]
        if len(seasons_no_xg) >= 3:
            causes.append("C")
            evidence.append(f"{len(seasons_no_xg)} seasons with fixtures but zero xG in sample — season mapping or historical gap")

        xgfixture_miss = 0
        stats_works = 0
        for er in endpoint_results:
            for name, v in (er.get("variants") or {}).items():
                if not isinstance(v, dict) or v.get("status") != "ok":
                    continue
                if v.get("has_team_xg") and not v.get("has_xgfixture_block"):
                    stats_works += 1
                if not v.get("has_team_xg") and v.get("has_xgfixture_block"):
                    xgfixture_miss += 1
        if xgfixture_miss:
            causes.append("E")
            evidence.append("xGFixture block present but parser missed team xG on some includes")
        if stats_works:
            causes.append("E")
            evidence.append("Team xG available via statistics path without xGFixture block")

        deep_has = any(
            (er.get("variants") or {}).get("deep_combo", {}).get("has_team_xg")
            for er in endpoint_results
        )
        xg_only = any(
            (er.get("variants") or {}).get("xg_fixture_includes", {}).get("has_team_xg")
            for er in endpoint_results
        )
        if deep_has and not xg_only:
            causes.append("E")
            evidence.append("deep_combo finds xG where xg_fixture_includes alone does not")

        if not causes:
            causes.append("G")

        label_map = {
            "A": "Sportmonks has limited xG coverage",
            "B": "Our importer misses available xG",
            "C": "Wrong season mapping / historical gap",
            "D": "Wrong endpoint usage",
            "E": "Wrong include configuration",
            "F": "Pagination issue",
            "G": "Combination of multiple causes",
        }

        return {
            "primary_causes": sorted(set(causes)),
            "cause_labels": [label_map.get(c, c) for c in sorted(set(causes))],
            "evidence": evidence,
            "api_sample_xg_rate": round(api_rate, 4),
        }

    def compare_importer_to_cache(self) -> dict[str, Any]:
        from worldcup_predictor.feature_store.normalizers import normalize_fixture_xg_records

        cache_dir = Path("data/egie/uefa_club/raw")
        scanned = team_xg = 0
        if not cache_dir.is_dir():
            return {"uefa_cache_scanned": 0, "uefa_cache_team_xg_fixtures": 0}
        for path in cache_dir.glob("*.json"):
            scanned += 1
            try:
                blob = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            data = (blob.get("payload") or {}).get("data") or {}
            recs = normalize_fixture_xg_records(data, sportmonks_fixture_id=int(path.stem))
            if any(r.metric_key == "xg" and r.record_type in ("team_metric", "team_xg") for r in recs):
                team_xg += 1
        return {"uefa_cache_scanned": scanned, "uefa_cache_team_xg_fixtures": team_xg}

    def run(self, *, include_optional_leagues: bool = True) -> dict[str, Any]:
        if not self.provider.is_configured:
            return {"status": "error", "error": "sportmonks_not_configured"}

        leagues = dict(TARGET_LEAGUES)
        if include_optional_leagues:
            leagues.update(OPTIONAL_LEAGUE_HINTS)

        league_meta: list[dict[str, Any]] = []
        season_rows: list[dict[str, Any]] = []
        endpoint_results: list[dict[str, Any]] = []
        probe_fixture_for_endpoint: int | None = None

        for league_key, league_id in leagues.items():
            if self.calls_live >= self.max_calls:
                break
            meta = self.discover_league_metadata(league_key, league_id)
            league_meta.append(meta)
            if not meta.get("seasons"):
                continue

            # Audit recent seasons first (up to 6 per league to manage budget)
            seasons = list(reversed(meta["seasons"]))[:6]
            for season in seasons:
                if self.calls_live >= self.max_calls:
                    break
                row = self.audit_season(
                    league_key, league_id, meta.get("league_name"), season
                )
                season_rows.append(row)
                if probe_fixture_for_endpoint is None and row.get("sample_fixture_ids"):
                    probe_fixture_for_endpoint = int(row["sample_fixture_ids"][0])

        # Endpoint audit on first available fixture + WC 732 if we have one
        audit_fixtures: list[int] = []
        if probe_fixture_for_endpoint:
            audit_fixtures.append(probe_fixture_for_endpoint)
        for m in league_meta:
            if m.get("league_id") == 732:
                for s in season_rows:
                    if s.get("league_id") == 732 and s.get("sample_fixture_ids"):
                        fid = int(s["sample_fixture_ids"][0])
                        if fid not in audit_fixtures:
                            audit_fixtures.append(fid)
                        break

        for fid in audit_fixtures[:2]:
            if self.calls_live >= self.max_calls:
                break
            endpoint_results.append(self.endpoint_audit(fid))

        importer_comparison = self.compare_importer_to_cache()
        matrix = build_coverage_matrix(season_rows)
        capabilities = self.api_capability_audit(season_rows, endpoint_results)
        rca = self.root_cause_analysis(league_meta, season_rows, endpoint_results, importer_comparison)

        # Timeline per league
        timeline: dict[str, list[dict[str, Any]]] = {}
        for row in season_rows:
            lk = str(row.get("league_key"))
            timeline.setdefault(lk, []).append(
                {
                    "season": row.get("season_name") or row.get("season_id"),
                    "coverage_pct": row.get("coverage_pct"),
                    "sample_coverage_pct": (
                        round(100.0 * int(row.get("sample_with_xg") or 0) / int(row.get("fixtures_sampled") or 1), 2)
                        if int(row.get("fixtures_sampled") or 0) > 0
                        else 0.0
                    ),
                    "fixtures": row.get("total_fixtures"),
                }
            )

        earliest_latest: dict[str, Any] = {}
        for lk, rows in timeline.items():
            with_xg = [r for r in rows if float(r.get("sample_coverage_pct") or 0) > 0]
            earliest_latest[lk] = {
                "earliest_season_with_xg": with_xg[0]["season"] if with_xg else None,
                "latest_season_with_xg": with_xg[-1]["season"] if with_xg else None,
                "timeline": rows,
            }

        out = {
            "generated_at": _utc_now(),
            "phase": "54F-3",
            "api_calls_live": self.calls_live,
            "api_calls_cached": self.calls_cached,
            "max_calls": self.max_calls,
            "league_discovery": league_meta,
            "season_audits": [{k: v for k, v in r.items() if k != "probes"} for r in season_rows],
            "XG_COVERAGE_MATRIX": matrix,
            "endpoint_audit": endpoint_results,
            "api_capability": capabilities,
            "root_cause_analysis": rca,
            "importer_comparison": importer_comparison,
            "historical_range": earliest_latest,
            "summary": self._build_summary(matrix, capabilities, rca),
        }

        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        (self.artifact_dir / "discovery_result.json").write_text(
            json.dumps(out, indent=2, default=str), encoding="utf-8"
        )
        (self.artifact_dir / "XG_COVERAGE_MATRIX.json").write_text(
            json.dumps(matrix, indent=2), encoding="utf-8"
        )
        # strip probes from detailed probes file
        probes_out = [{"season_id": r.get("season_id"), "league_key": r.get("league_key"), "probes": r.get("probes")} for r in season_rows]
        (self.artifact_dir / "fixture_probes.json").write_text(json.dumps(probes_out, indent=2, default=str), encoding="utf-8")
        return out

    def _build_summary(
        self,
        matrix: list[dict[str, Any]],
        capabilities: dict[str, str],
        rca: dict[str, Any],
    ) -> dict[str, Any]:
        total_fixtures = sum(int(r.get("fixtures") or 0) for r in matrix)
        est_with_xg = sum(int(r.get("fixtures_with_xg") or 0) for r in matrix)
        best_leagues = sorted(matrix, key=lambda r: float(r.get("sample_coverage_pct") or 0), reverse=True)[:5]
        best_seasons = sorted(matrix, key=lambda r: float(r.get("sample_coverage_pct") or 0), reverse=True)[:5]
        return {
            "total_fixtures_estimated": total_fixtures,
            "fixtures_with_xg_estimated": est_with_xg,
            "overall_coverage_pct_estimated": round(100.0 * est_with_xg / total_fixtures, 2) if total_fixtures else 0.0,
            "api_sample_xg_rate": rca.get("api_sample_xg_rate"),
            "best_leagues_by_sample_coverage": [
                {"league": r.get("league"), "season": r.get("season"), "sample_coverage_pct": r.get("sample_coverage_pct")}
                for r in best_leagues
            ],
            "best_seasons_by_sample_coverage": [
                {"league": r.get("league"), "season": r.get("season"), "sample_coverage_pct": r.get("sample_coverage_pct")}
                for r in best_seasons
            ],
            "api_capability": capabilities,
            "root_cause_primary": rca.get("primary_causes"),
        }
