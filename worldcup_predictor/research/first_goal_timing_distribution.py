"""Phase 60B — First goal timing distribution research (read-only)."""

from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from worldcup_predictor.automation.worldcup_background.goal_minute_evaluator import effective_goal_minute
from worldcup_predictor.config.settings import get_settings

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "phase60b_first_goal_timing_distribution"

Classification = Literal[
    "bucket_1_15",
    "bucket_16_30",
    "bucket_31_45_plus",
    "bucket_46_60",
    "bucket_61_75",
    "bucket_76_90_plus",
    "no_goal",
    "data_missing",
]

BUCKET_LABELS = {
    "bucket_1_15": "1-15",
    "bucket_16_30": "16-30",
    "bucket_31_45_plus": "31-45+",
    "bucket_46_60": "46-60",
    "bucket_61_75": "61-75",
    "bucket_76_90_plus": "76-90+",
    "no_goal": "no_goal",
    "data_missing": "data_missing",
}

FINISHED_STATUSES = ("FT", "AET", "PEN", "FINISHED")


@dataclass
class FirstGoalRow:
    fixture_id: int
    competition_key: str
    season: int | None
    home_team: str
    away_team: str
    kickoff_utc: str | None
    home_goals: int | None
    away_goals: int | None
    first_goal_minute_raw: int | None
    first_goal_minute_effective: int | None
    first_goal_team: str | None
    first_goal_side: str | None
    classification: Classification
    bucket_label: str
    in_1_30: bool | None
    in_31_plus: bool | None
    data_source: str
    goal_event_count: int
    quality_flags: list[str] = field(default_factory=list)

    def to_csv_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition_key": self.competition_key,
            "season": self.season if self.season is not None else "",
            "home_team": self.home_team,
            "away_team": self.away_team,
            "kickoff_utc": self.kickoff_utc or "",
            "home_goals": self.home_goals if self.home_goals is not None else "",
            "away_goals": self.away_goals if self.away_goals is not None else "",
            "first_goal_minute_raw": self.first_goal_minute_raw if self.first_goal_minute_raw is not None else "",
            "first_goal_minute_effective": self.first_goal_minute_effective if self.first_goal_minute_effective is not None else "",
            "first_goal_team": self.first_goal_team or "",
            "first_goal_side": self.first_goal_side or "",
            "classification": self.classification,
            "bucket_label": self.bucket_label,
            "in_1_30": self.in_1_30 if self.in_1_30 is not None else "",
            "in_31_plus": self.in_31_plus if self.in_31_plus is not None else "",
            "data_source": self.data_source,
            "goal_event_count": self.goal_event_count,
            "quality_flags": ";".join(self.quality_flags),
        }


def minute_bucket(effective: int | None) -> Classification | None:
    if effective is None:
        return None
    if effective <= 15:
        return "bucket_1_15"
    if effective <= 30:
        return "bucket_16_30"
    if effective <= 45:
        return "bucket_31_45_plus"
    if effective <= 60:
        return "bucket_46_60"
    if effective <= 75:
        return "bucket_61_75"
    return "bucket_76_90_plus"


def _side(team: str | None, home: str, away: str) -> str | None:
    if not team:
        return None
    t = team.lower().strip()
    if home and t in home.lower():
        return "home"
    if away and t in away.lower():
        return "away"
    return "unknown"


def _is_goal_event_row(row: dict[str, Any]) -> bool:
    detail = str(row.get("detail") or "").lower()
    if "missed penalty" in detail or "missed pen" in detail:
        return False
    if "penalty cancelled" in detail:
        return False
    return row.get("minute") is not None


def extract_first_goal_from_events(events: list[dict[str, Any]]) -> tuple[int | None, int | None, str | None]:
    valid = [e for e in events if _is_goal_event_row(e)]
    if not valid:
        return None, None, None
    valid.sort(key=lambda e: (int(e.get("sort_index") or 0), int(e.get("minute") or 999)))
    first = valid[0]
    raw = int(first["minute"])
    extra = int(first["extra_minute"]) if first.get("extra_minute") is not None else None
    eff = effective_goal_minute(raw, extra)
    return raw, eff, first.get("team")


def _pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 2) if d else None


def _distribution_counts(rows: list[FirstGoalRow]) -> dict[str, Any]:
    reliable = [r for r in rows if r.classification != "data_missing"]
    with_goal = [r for r in reliable if r.classification != "no_goal"]
    no_goal = [r for r in reliable if r.classification == "no_goal"]
    in_1_30 = [r for r in with_goal if r.in_1_30]
    in_31_plus = [r for r in with_goal if r.in_31_plus]

    bucket_counts = Counter(r.classification for r in reliable)
    return {
        "total_reliable_fixtures": len(reliable),
        "with_at_least_one_goal": len(with_goal),
        "no_goal_fixtures": len(no_goal),
        "data_missing_fixtures": sum(1 for r in rows if r.classification == "data_missing"),
        "first_goal_1_30_count": len(in_1_30),
        "first_goal_31_plus_count": len(in_31_plus),
        "pct_A_with_goal_first_1_30": _pct(len(in_1_30), len(with_goal)),
        "pct_A_with_goal_first_31_plus": _pct(len(in_31_plus), len(with_goal)),
        "pct_B_all_reliable_first_1_30": _pct(len(in_1_30), len(reliable)),
        "pct_B_all_reliable_first_31_plus": _pct(len(in_31_plus), len(reliable)),
        "pct_B_no_goal": _pct(len(no_goal), len(reliable)),
        "bucket_counts": {BUCKET_LABELS.get(k, k): bucket_counts.get(k, 0) for k in BUCKET_LABELS},
        "bucket_pct_of_reliable": {
            BUCKET_LABELS[k]: _pct(bucket_counts.get(k, 0), len(reliable))
            for k in BUCKET_LABELS
            if k != "data_missing"
        },
    }


class FirstGoalTimingResearch:
    """Aggregate first-goal timing from SQLite + supplemental artifacts."""

    def __init__(self, *, db_path: str | Path | None = None) -> None:
        settings = get_settings()
        self.db_path = Path(db_path or settings.sqlite_path or ROOT / "data" / "football_intelligence.db")
        self.api_calls_used = 0
        self.quality = {
            "fixtures_skipped_missing_events": 0,
            "fixtures_score_event_inconsistent": 0,
            "events_missing_minute": 0,
            "duplicate_events_deduped": 0,
            "sources_used": [],
        }

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load_sqlite_rows(self) -> list[FirstGoalRow]:
        conn = self._connect()
        fixtures = conn.execute(
            f"""
            SELECT f.fixture_id, f.competition_key, f.season, f.home_team, f.away_team, f.kickoff_utc, f.status,
                   r.home_goals, r.away_goals
            FROM fixtures f
            JOIN fixture_results r ON r.fixture_id = f.fixture_id
            WHERE f.status IN ({",".join("?" * len(FINISHED_STATUSES))})
            """,
            FINISHED_STATUSES,
        ).fetchall()

        event_map: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for ev in conn.execute(
            "SELECT fixture_id, sort_index, minute, extra_minute, team, is_penalty, is_own_goal, detail FROM fixture_goal_events ORDER BY fixture_id, sort_index"
        ):
            event_map[int(ev["fixture_id"])].append(dict(ev))

        null_minute = conn.execute("SELECT COUNT(*) FROM fixture_goal_events WHERE minute IS NULL").fetchone()[0]
        self.quality["events_missing_minute"] = int(null_minute or 0)

        cache_events = self._scan_api_cache_goal_events(conn)
        conn.close()

        rows: list[FirstGoalRow] = []
        seen: set[int] = set()

        for fx in fixtures:
            fid = int(fx["fixture_id"])
            seen.add(fid)
            home = str(fx["home_team"] or "")
            away = str(fx["away_team"] or "")
            hg = int(fx["home_goals"]) if fx["home_goals"] is not None else None
            ag = int(fx["away_goals"]) if fx["away_goals"] is not None else None
            events = event_map.get(fid, [])
            row = self._classify_fixture(
                fixture_id=fid,
                competition_key=str(fx["competition_key"] or ""),
                season=int(fx["season"]) if fx["season"] is not None else None,
                home_team=home,
                away_team=away,
                kickoff_utc=fx["kickoff_utc"],
                home_goals=hg,
                away_goals=ag,
                events=events,
                data_source="sqlite_goal_events" if events else "sqlite_results_only",
            )
            rows.append(row)

        for fid, payload in cache_events.items():
            if fid in seen:
                continue
            row = self._classify_fixture(
                fixture_id=fid,
                competition_key=str(payload.get("competition_key") or "api_cache"),
                season=payload.get("season"),
                home_team=str(payload.get("home_team") or ""),
                away_team=str(payload.get("away_team") or ""),
                kickoff_utc=payload.get("kickoff_utc"),
                home_goals=payload.get("home_goals"),
                away_goals=payload.get("away_goals"),
                events=payload.get("events") or [],
                data_source="api_response_cache",
            )
            rows.append(row)

        self.quality["sources_used"].append("sqlite")
        if cache_events:
            self.quality["sources_used"].append("api_response_cache")
        return rows

    def _scan_api_cache_goal_events(self, conn: sqlite3.Connection) -> dict[int, dict[str, Any]]:
        out: dict[int, dict[str, Any]] = {}
        try:
            rows = conn.execute(
                "SELECT endpoint, params_json, payload_json FROM api_response_cache WHERE endpoint LIKE '%fixture%' OR endpoint LIKE '%event%'"
            ).fetchall()
        except sqlite3.Error:
            return out
        for row in rows:
            try:
                params = json.loads(row["params_json"] or "{}")
                payload = json.loads(row["payload_json"] or "{}")
            except (json.JSONDecodeError, TypeError):
                continue
            fid = params.get("fixture_id") or params.get("id")
            if fid is None:
                resp = payload.get("response") if isinstance(payload, dict) else payload
                if isinstance(resp, list) and resp:
                    item = resp[0]
                    fid = item.get("fixture", {}).get("id") if isinstance(item, dict) else None
            if fid is None:
                continue
            events = self._parse_api_football_events(
                payload if isinstance(payload, dict) else {"response": payload}
            )
            if events:
                out[int(fid)] = {"events": events, "competition_key": "api_cache"}
        return out

    def _parse_api_football_events(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        resp = payload.get("response")
        items = resp if isinstance(resp, list) else [payload]
        for block in items:
            if not isinstance(block, dict):
                continue
            for idx, ev in enumerate(block.get("events") or []):
                if not isinstance(ev, dict):
                    continue
                etype = str((ev.get("type") or "")).lower()
                detail = str(ev.get("detail") or "").lower()
                if "goal" not in etype and "goal" not in detail:
                    continue
                if "missed" in detail:
                    continue
                time = ev.get("time") or {}
                minute = time.get("elapsed")
                if minute is None:
                    continue
                team = (ev.get("team") or {}).get("name")
                events.append(
                    {
                        "sort_index": idx,
                        "minute": minute,
                        "extra_minute": time.get("extra"),
                        "team": team,
                        "is_penalty": 1 if "penalty" in detail else 0,
                        "is_own_goal": 1 if "own" in detail else 0,
                        "detail": ev.get("detail"),
                    }
                )
        return events

    def _classify_fixture(
        self,
        *,
        fixture_id: int,
        competition_key: str,
        season: int | None,
        home_team: str,
        away_team: str,
        kickoff_utc: str | None,
        home_goals: int | None,
        away_goals: int | None,
        events: list[dict[str, Any]],
        data_source: str,
    ) -> FirstGoalRow:
        flags: list[str] = []
        scoreless = home_goals == 0 and away_goals == 0
        has_score = (home_goals or 0) + (away_goals or 0) > 0

        raw, eff, team = extract_first_goal_from_events(events)
        if events and raw is None:
            flags.append("events_present_no_valid_minute")

        if scoreless and not events:
            return FirstGoalRow(
                fixture_id=fixture_id,
                competition_key=competition_key,
                season=season,
                home_team=home_team,
                away_team=away_team,
                kickoff_utc=kickoff_utc,
                home_goals=home_goals,
                away_goals=away_goals,
                first_goal_minute_raw=None,
                first_goal_minute_effective=None,
                first_goal_team=None,
                first_goal_side=None,
                classification="no_goal",
                bucket_label="no_goal",
                in_1_30=None,
                in_31_plus=None,
                data_source=data_source,
                goal_event_count=len(events),
                quality_flags=flags,
            )

        if scoreless and events:
            flags.append("scoreless_but_events_present")
            self.quality["fixtures_score_event_inconsistent"] += 1

        if raw is None:
            if has_score:
                self.quality["fixtures_skipped_missing_events"] += 1
                return FirstGoalRow(
                    fixture_id=fixture_id,
                    competition_key=competition_key,
                    season=season,
                    home_team=home_team,
                    away_team=away_team,
                    kickoff_utc=kickoff_utc,
                    home_goals=home_goals,
                    away_goals=away_goals,
                    first_goal_minute_raw=None,
                    first_goal_minute_effective=None,
                    first_goal_team=None,
                    first_goal_side=None,
                    classification="data_missing",
                    bucket_label="data_missing",
                    in_1_30=None,
                    in_31_plus=None,
                    data_source=data_source,
                    goal_event_count=len(events),
                    quality_flags=flags + ["scored_match_no_first_goal_minute"],
                )
            return FirstGoalRow(
                fixture_id=fixture_id,
                competition_key=competition_key,
                season=season,
                home_team=home_team,
                away_team=away_team,
                kickoff_utc=kickoff_utc,
                home_goals=home_goals,
                away_goals=away_goals,
                first_goal_minute_raw=None,
                first_goal_minute_effective=None,
                first_goal_team=None,
                first_goal_side=None,
                classification="data_missing",
                bucket_label="data_missing",
                in_1_30=None,
                in_31_plus=None,
                data_source=data_source,
                goal_event_count=len(events),
                quality_flags=flags + ["unclassified"],
            )

        if has_score and events and len(events) > (home_goals or 0) + (away_goals or 0):
            flags.append("event_count_exceeds_score")

        bucket = minute_bucket(eff)
        assert bucket is not None
        return FirstGoalRow(
            fixture_id=fixture_id,
            competition_key=competition_key,
            season=season,
            home_team=home_team,
            away_team=away_team,
            kickoff_utc=kickoff_utc,
            home_goals=home_goals,
            away_goals=away_goals,
            first_goal_minute_raw=raw,
            first_goal_minute_effective=eff,
            first_goal_team=team,
            first_goal_side=_side(team, home_team, away_team),
            classification=bucket,
            bucket_label=BUCKET_LABELS[bucket],
            in_1_30=eff <= 30 if eff is not None else None,
            in_31_plus=eff >= 31 if eff is not None else None,
            data_source=data_source,
            goal_event_count=len(events),
            quality_flags=flags,
        )

    def load_egie_backtest_rows(self, path: Path) -> list[FirstGoalRow]:
        if not path.is_file():
            return []
        rows: list[FirstGoalRow] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            if not rec.get("evaluable"):
                continue
            fid = int(rec["fixture_id"])
            minute = rec.get("actual_first_goal_minute")
            final = str(rec.get("final_score") or "")
            hg = ag = None
            if "-" in final:
                parts = final.split("-")
                try:
                    hg, ag = int(parts[0]), int(parts[1])
                except (ValueError, IndexError):
                    pass
            if minute is None and final in ("0-0", ""):
                classification: Classification = "no_goal"
                eff = None
            elif minute is None:
                continue
            else:
                eff = effective_goal_minute(int(minute), None)
                classification = minute_bucket(eff) or "data_missing"
            rows.append(
                FirstGoalRow(
                    fixture_id=fid,
                    competition_key=str(rec.get("competition_key") or "premier_league"),
                    season=None,
                    home_team=str(rec.get("home_team") or ""),
                    away_team=str(rec.get("away_team") or ""),
                    kickoff_utc=rec.get("kickoff_utc"),
                    home_goals=hg,
                    away_goals=ag,
                    first_goal_minute_raw=int(minute) if minute is not None else None,
                    first_goal_minute_effective=eff,
                    first_goal_team=rec.get("actual_first_goal_team"),
                    first_goal_side=None,
                    classification=classification,
                    bucket_label=BUCKET_LABELS.get(classification, classification),
                    in_1_30=eff <= 30 if eff is not None else None,
                    in_31_plus=eff >= 31 if eff is not None else None,
                    data_source="egie_backtest_jsonl",
                    goal_event_count=int(rec.get("goal_event_count") or 0),
                    quality_flags=[],
                )
            )
        self.quality["sources_used"].append("egie_backtest_jsonl")
        return rows

    def load_uefa_parquet_rows(self, path: Path) -> list[FirstGoalRow]:
        if not path.is_file():
            return []
        try:
            import pandas as pd
        except ImportError:
            return []
        df = pd.read_parquet(path)
        rows: list[FirstGoalRow] = []
        for _, rec in df.iterrows():
            minute = rec.get("first_goal_minute")
            hg = rec.get("home_goals")
            ag = rec.get("away_goals")
            try:
                hg_i = int(hg) if hg == hg else None
                ag_i = int(ag) if ag == ag else None
            except (TypeError, ValueError):
                hg_i = ag_i = None
            if minute != minute and (hg_i == 0 and ag_i == 0):  # NaN minute, 0-0
                classification = "no_goal"
                eff = None
            elif minute != minute:
                continue
            else:
                eff = effective_goal_minute(int(minute), None)
                classification = minute_bucket(eff) or "data_missing"
            rows.append(
                FirstGoalRow(
                    fixture_id=int(rec.get("fixture_id") or 0),
                    competition_key=str(rec.get("competition_key") or "uefa_club"),
                    season=None,
                    home_team=str(rec.get("home_team") or ""),
                    away_team=str(rec.get("away_team") or ""),
                    kickoff_utc=str(rec.get("kickoff_utc") or ""),
                    home_goals=hg_i,
                    away_goals=ag_i,
                    first_goal_minute_raw=int(minute) if minute == minute else None,
                    first_goal_minute_effective=eff,
                    first_goal_team=None,
                    first_goal_side=None,
                    classification=classification,
                    bucket_label=BUCKET_LABELS.get(classification, str(classification)),
                    in_1_30=eff <= 30 if eff is not None else None,
                    in_31_plus=eff >= 31 if eff is not None else None,
                    data_source="uefa_survival_parquet",
                    goal_event_count=0,
                    quality_flags=[],
                )
            )
        self.quality["sources_used"].append("uefa_survival_parquet")
        return rows

    def run(self) -> dict[str, Any]:
        primary = self.load_sqlite_rows()
        egie = self.load_egie_backtest_rows(ROOT / "artifacts" / "phase51h_egie_backtest.jsonl")
        uefa = self.load_uefa_parquet_rows(ROOT / "data" / "egie" / "uefa_club" / "uefa_survival_dataset.parquet")

        by_source = {
            "sqlite_primary": _distribution_counts(primary),
            "egie_backtest_jsonl": _distribution_counts(egie),
            "uefa_survival_parquet": _distribution_counts(uefa),
        }

        merged = self._merge_sources(primary, egie, uefa)
        overall = _distribution_counts(merged)

        by_league = self._group_breakdown(merged, "competition_key")
        by_season = self._group_breakdown(merged, "season")
        by_source_breakdown = self._group_breakdown(merged, "data_source")
        by_side = self._group_breakdown([r for r in merged if r.first_goal_side], "first_goal_side")

        summary = {
            "generated_at": __import__("datetime").datetime.utcnow().isoformat() + "Z",
            "db_path": str(self.db_path),
            "api_calls_used": self.api_calls_used,
            "main_answer": {
                "among_fixtures_with_at_least_one_goal": {
                    "first_goal_1_30_pct": overall["pct_A_with_goal_first_1_30"],
                    "first_goal_31_plus_pct": overall["pct_A_with_goal_first_31_plus"],
                    "sample_size": overall["with_at_least_one_goal"],
                },
                "among_all_reliable_completed_fixtures": {
                    "first_goal_1_30_pct": overall["pct_B_all_reliable_first_1_30"],
                    "first_goal_31_plus_pct": overall["pct_B_all_reliable_first_31_plus"],
                    "no_goal_pct": overall["pct_B_no_goal"],
                    "sample_size": overall["total_reliable_fixtures"],
                },
            },
            "overall": overall,
            "by_source": by_source,
            "by_league": by_league,
            "by_season": by_season,
            "by_data_source": by_source_breakdown,
            "by_first_goal_side": by_side,
            "data_quality": self.quality,
            "recommendation": self._recommend(overall, by_league),
        }
        return {"rows": merged, "summary": summary}

    def _merge_sources(self, *groups: list[FirstGoalRow]) -> list[FirstGoalRow]:
        merged: dict[int, FirstGoalRow] = {}
        priority = {"sqlite_goal_events": 0, "sqlite_results_only": 1, "egie_backtest_jsonl": 2, "uefa_survival_parquet": 3, "api_response_cache": 4}
        for group in groups:
            for row in group:
                existing = merged.get(row.fixture_id)
                if existing is None or priority.get(row.data_source, 9) < priority.get(existing.data_source, 9):
                    merged[row.fixture_id] = row
                elif existing.classification == "data_missing" and row.classification != "data_missing":
                    merged[row.fixture_id] = row
        return list(merged.values())

    def _group_breakdown(self, rows: list[FirstGoalRow], key: str) -> dict[str, Any]:
        groups: dict[str, list[FirstGoalRow]] = defaultdict(list)
        for row in rows:
            val = getattr(row, key, None)
            label = str(val) if val is not None else "unknown"
            groups[label].append(row)
        return {k: _distribution_counts(v) for k, v in sorted(groups.items(), key=lambda x: -len(x[1]))}

    def _recommend(self, overall: dict[str, Any], by_league: dict[str, Any]) -> str:
        reliable = overall.get("total_reliable_fixtures", 0)
        with_goal = overall.get("with_at_least_one_goal", 0)
        if reliable < 100:
            return "NEEDS_MORE_DATA"
        if with_goal < 80:
            return "NEEDS_MORE_DATA"
        leagues_with_data = sum(1 for k, v in by_league.items() if v.get("with_at_least_one_goal", 0) >= 30)
        if leagues_with_data >= 2:
            spread = []
            for k, v in by_league.items():
                if v.get("with_at_least_one_goal", 0) >= 30:
                    spread.append(abs((v.get("pct_A_with_goal_first_1_30") or 0) - (overall.get("pct_A_with_goal_first_1_30") or 0)))
            if spread and max(spread) >= 8.0:
                return "USE_LEAGUE_SPECIFIC_PRIORS"
        pct_1_30 = overall.get("pct_A_with_goal_first_1_30")
        if pct_1_30 is not None and 40 <= pct_1_30 <= 70:
            return "USE_1_30_PRIOR"
        return "USE_LEAGUE_SPECIFIC_PRIORS"


def write_artifacts(result: dict[str, Any]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[FirstGoalRow] = result["rows"]
    summary: dict[str, Any] = result["summary"]

    if rows:
        fields = list(rows[0].to_csv_dict().keys())
        with (ARTIFACT_DIR / "first_goal_timing_rows.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in sorted(rows, key=lambda r: (r.competition_key, r.fixture_id)):
                writer.writerow(row.to_csv_dict())

    (ARTIFACT_DIR / "first_goal_timing_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    league_rows = []
    for league, stats in (summary.get("by_league") or {}).items():
        league_rows.append({"competition_key": league, **stats})
    if league_rows:
        fields = list(league_rows[0].keys())
        with (ARTIFACT_DIR / "first_goal_timing_by_league.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in league_rows:
                flat = dict(row)
                if isinstance(flat.get("bucket_counts"), dict):
                    flat["bucket_counts"] = json.dumps(flat["bucket_counts"])
                if isinstance(flat.get("bucket_pct_of_reliable"), dict):
                    flat["bucket_pct_of_reliable"] = json.dumps(flat["bucket_pct_of_reliable"])
                writer.writerow(flat)

    season_rows = [{"season": k, **v} for k, v in (summary.get("by_season") or {}).items()]
    if season_rows:
        fields = list(season_rows[0].keys())
        with (ARTIFACT_DIR / "first_goal_timing_by_season.csv").open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            for row in season_rows:
                flat = dict(row)
                if isinstance(flat.get("bucket_counts"), dict):
                    flat["bucket_counts"] = json.dumps(flat["bucket_counts"])
                writer.writerow(flat)

    quality = {
        **summary.get("data_quality", {}),
        "source_reliability_ranking": [
            "sqlite_goal_events (highest — per-event minute, sort_index)",
            "egie_backtest_jsonl (premier_league validated replay)",
            "uefa_survival_parquet (Sportmonks UEFA club subset)",
            "sqlite_results_only / data_missing (score only, no timing)",
        ],
        "api_calls_used": summary.get("api_calls_used", 0),
    }
    (ARTIFACT_DIR / "data_quality_report.json").write_text(json.dumps(quality, indent=2), encoding="utf-8")
    return ARTIFACT_DIR
