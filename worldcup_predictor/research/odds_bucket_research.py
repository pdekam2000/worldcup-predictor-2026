"""Phase 60C — Odds bucket research for completed matches."""

from __future__ import annotations

import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.repository import FootballIntelligenceRepository
from worldcup_predictor.egie.provider_features.odds_snapshot_parser import (
    normalize_snapshot_odds_lines,
    parse_implied_1x2,
    parse_implied_ou25,
)
from worldcup_predictor.research.first_goal_timing_distribution import (
    BUCKET_LABELS,
    FINISHED_STATUSES,
    minute_bucket,
)
from worldcup_predictor.automation.worldcup_background.goal_minute_evaluator import effective_goal_minute

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_DIR = ROOT / "artifacts" / "phase60c_goal_event_backfill"

FAVORITE_BUCKETS = [
    (1.01, 1.20, "1.01-1.20"),
    (1.21, 1.40, "1.21-1.40"),
    (1.41, 1.60, "1.41-1.60"),
    (1.61, 1.80, "1.61-1.80"),
    (1.81, 2.00, "1.81-2.00"),
    (2.01, 2.50, "2.01-2.50"),
    (2.51, 3.00, "2.51-3.00"),
    (3.01, 999.0, "3.01+"),
]

OU_BUCKETS = [
    (1.01, 1.50, "1.01-1.50"),
    (1.51, 1.80, "1.51-1.80"),
    (1.81, 2.10, "1.81-2.10"),
    (2.11, 2.50, "2.11-2.50"),
    (2.51, 999.0, "2.51+"),
]


def _bucket_label(value: float | None, buckets: list[tuple[float, float, str]]) -> str | None:
    if value is None or value <= 1.0:
        return None
    for lo, hi, label in buckets:
        if lo <= value <= hi:
            return label
    return None


def _pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 2) if d else None


@dataclass
class OddsMatchRow:
    fixture_id: int
    competition_key: str
    home_goals: int
    away_goals: int
    favorite_side: str | None
    favorite_odds: float | None
    favorite_bucket: str | None
    over_25_odds: float | None
    under_25_odds: float | None
    ou_bucket: str | None
    favorite_won: bool | None
    is_draw: bool
    underdog_won: bool | None
    over_25: bool
    btts_yes: bool
    first_goal_bucket: str
    first_goal_1_30: bool | None
    first_goal_31_plus: bool | None
    total_goals: int

    def to_csv_dict(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "competition_key": self.competition_key,
            "home_goals": self.home_goals,
            "away_goals": self.away_goals,
            "favorite_side": self.favorite_side or "",
            "favorite_odds": self.favorite_odds if self.favorite_odds is not None else "",
            "favorite_bucket": self.favorite_bucket or "",
            "over_25_odds": self.over_25_odds if self.over_25_odds is not None else "",
            "under_25_odds": self.under_25_odds if self.under_25_odds is not None else "",
            "ou_bucket": self.ou_bucket or "",
            "favorite_won": int(self.favorite_won) if self.favorite_won is not None else "",
            "is_draw": int(self.is_draw),
            "underdog_won": int(self.underdog_won) if self.underdog_won is not None else "",
            "over_25": int(self.over_25),
            "btts_yes": int(self.btts_yes),
            "first_goal_bucket": self.first_goal_bucket,
            "first_goal_1_30": int(self.first_goal_1_30) if self.first_goal_1_30 is not None else "",
            "first_goal_31_plus": int(self.first_goal_31_plus) if self.first_goal_31_plus is not None else "",
            "total_goals": self.total_goals,
        }


class OddsBucketResearch:
    def __init__(self) -> None:
        settings = get_settings()
        self.repo = FootballIntelligenceRepository(settings.sqlite_path or None)
        self.warnings: list[str] = []

    def _first_goal_info(self, fixture_id: int) -> tuple[str, bool | None, bool | None]:
        events = self.repo.list_fixture_goal_events(fixture_id)
        if not events:
            return "data_missing", None, None
        first = sorted(events, key=lambda e: (e.get("minute") or 9999, e.get("sort_index") or 0))[0]
        raw = first.get("minute")
        if raw is None:
            return "data_missing", None, None
        eff = effective_goal_minute(int(raw), first.get("extra_minute"))
        bucket = minute_bucket(eff)
        label = BUCKET_LABELS.get(bucket or "", "data_missing")
        return label, eff <= 30, eff >= 31

    def _parse_fixture_odds(self, snapshots: list[dict[str, Any]]) -> dict[str, float | None]:
        if not snapshots:
            return {}
        latest = snapshots[-1]
        payload = latest.get("payload_json") or latest.get("payload") or latest
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                return {}
        lines = normalize_snapshot_odds_lines(
            payload,
            fixture_id=latest.get("fixture_id"),
            captured_at=latest.get("snapshot_at"),
        )
        if not lines:
            return {}
        best_home = best_away = best_draw = best_over = best_under = None
        for line in lines:
            market = line.market_name.lower()
            sel = line.selection.lower()
            if "match winner" in market or market in {"1x2", "match result"}:
                if sel == "home":
                    best_home = line.odd if best_home is None or line.odd < best_home else best_home
                elif sel == "away":
                    best_away = line.odd if best_away is None or line.odd < best_away else best_away
                elif sel == "draw":
                    best_draw = line.odd if best_draw is None or line.odd < best_draw else best_draw
            if "over/under" in market or "goals over" in market:
                if "over 2.5" in sel:
                    best_over = line.odd if best_over is None or line.odd < best_over else best_over
                elif "under 2.5" in sel:
                    best_under = line.odd if best_under is None or line.odd < best_under else best_under
        x12_implied = parse_implied_1x2(lines)
        ou_implied = parse_implied_ou25(lines)
        return {
            "odds_home": best_home,
            "odds_away": best_away,
            "odds_draw": best_draw,
            "odds_over_25": best_over,
            "odds_under_25": best_under,
            "implied_over_25": ou_implied.get("over_2_5"),
            "implied_home": x12_implied.get("home"),
            "implied_away": x12_implied.get("away"),
        }

    def _determine_favorite(self, odds: dict[str, float | None]) -> tuple[str | None, float | None]:
        home = odds.get("odds_home")
        away = odds.get("odds_away")
        if home is None and away is None:
            return None, None
        if home is not None and (away is None or home <= away):
            return "home", home
        if away is not None:
            return "away", away
        return "home", home

    def _match_outcome(self, hg: int, ag: int) -> str:
        if hg > ag:
            return "home"
        if ag > hg:
            return "away"
        return "draw"

    def load_rows(self) -> list[OddsMatchRow]:
        ph = ",".join("?" * len(FINISHED_STATUSES))
        fixtures = self.repo._conn.execute(
            f"""
            SELECT f.fixture_id, f.competition_key, r.home_goals, r.away_goals
            FROM fixtures f
            JOIN fixture_results r ON r.fixture_id = f.fixture_id
            JOIN odds_snapshots o ON o.fixture_id = f.fixture_id
            WHERE f.status IN ({ph})
            GROUP BY f.fixture_id
            """,
            FINISHED_STATUSES,
        ).fetchall()

        out: list[OddsMatchRow] = []
        for fx in fixtures:
            fid = int(fx["fixture_id"])
            hg = int(fx["home_goals"] or 0)
            ag = int(fx["away_goals"] or 0)
            snapshots = self.repo.fetch_odds_snapshots(fid, limit=20)
            if not snapshots:
                continue
            odds = self._parse_fixture_odds(snapshots)
            fav_side, fav_odds = self._determine_favorite(odds)
            if fav_odds is None:
                self.warnings.append(f"fixture_{fid}_missing_favorite_odds")
                continue
            bucket = _bucket_label(fav_odds, FAVORITE_BUCKETS)
            if bucket is None:
                continue
            over_odds = odds.get("odds_over_25")
            under_odds = odds.get("odds_under_25")
            ou_bucket = _bucket_label(over_odds, OU_BUCKETS) or _bucket_label(under_odds, OU_BUCKETS)
            outcome = self._match_outcome(hg, ag)
            is_draw = outcome == "draw"
            fav_won = (fav_side == outcome) if not is_draw else False
            underdog_won = (not is_draw and fav_side != outcome) if fav_side else None
            fg_bucket, in_1_30, in_31_plus = self._first_goal_info(fid)
            if hg == 0 and ag == 0:
                fg_bucket = "no_goal"
                in_1_30 = None
                in_31_plus = None
            out.append(
                OddsMatchRow(
                    fixture_id=fid,
                    competition_key=str(fx["competition_key"] or ""),
                    home_goals=hg,
                    away_goals=ag,
                    favorite_side=fav_side,
                    favorite_odds=fav_odds,
                    favorite_bucket=bucket,
                    over_25_odds=over_odds,
                    under_25_odds=under_odds,
                    ou_bucket=ou_bucket,
                    favorite_won=fav_won,
                    is_draw=is_draw,
                    underdog_won=underdog_won,
                    over_25=(hg + ag) > 2,
                    btts_yes=hg > 0 and ag > 0,
                    first_goal_bucket=fg_bucket,
                    first_goal_1_30=in_1_30,
                    first_goal_31_plus=in_31_plus,
                    total_goals=hg + ag,
                )
            )
        return out

    def summarize_buckets(self, rows: list[OddsMatchRow]) -> dict[str, Any]:
        groups: dict[str, list[OddsMatchRow]] = defaultdict(list)
        for row in rows:
            if row.favorite_bucket:
                groups[row.favorite_bucket].append(row)

        bucket_order = [b[2] for b in FAVORITE_BUCKETS]
        stats: dict[str, Any] = {}
        for label in bucket_order:
            items = groups.get(label, [])
            if not items:
                stats[label] = {"match_count": 0}
                continue
            with_goal = [r for r in items if r.first_goal_bucket not in ("no_goal", "data_missing")]
            no_goal = [r for r in items if r.first_goal_bucket == "no_goal"]
            in_1_30 = [r for r in with_goal if r.first_goal_1_30]
            in_31_plus = [r for r in with_goal if r.first_goal_31_plus]
            fav_wins = sum(1 for r in items if r.favorite_won)
            draws = sum(1 for r in items if r.is_draw)
            underdog = sum(1 for r in items if r.underdog_won)
            over25 = sum(1 for r in items if r.over_25)
            btts = sum(1 for r in items if r.btts_yes)
            roi_stake = len(items)
            roi_return = sum((r.favorite_odds or 0) for r in items if r.favorite_won)
            stats[label] = {
                "match_count": len(items),
                "favorite_win_pct": _pct(fav_wins, len(items)),
                "draw_pct": _pct(draws, len(items)),
                "underdog_win_pct": _pct(underdog, len(items)),
                "over_25_pct": _pct(over25, len(items)),
                "under_25_pct": _pct(len(items) - over25, len(items)),
                "btts_yes_pct": _pct(btts, len(items)),
                "btts_no_pct": _pct(len(items) - btts, len(items)),
                "first_goal_1_30_pct": _pct(len(in_1_30), len(with_goal)),
                "first_goal_31_plus_pct": _pct(len(in_31_plus), len(with_goal)),
                "no_goal_pct": _pct(len(no_goal), len(items)),
                "avg_goals": round(sum(r.total_goals for r in items) / len(items), 2),
                "favorite_blind_roi_pct": round(100 * (roi_return - roi_stake) / roi_stake, 2) if roi_stake else None,
                "with_goal_sample": len(with_goal),
            }
        return stats

    def summarize_ou_buckets(self, rows: list[OddsMatchRow]) -> dict[str, Any]:
        groups: dict[str, list[OddsMatchRow]] = defaultdict(list)
        for row in rows:
            if row.ou_bucket and row.over_25_odds is not None:
                groups[row.ou_bucket].append(row)
        out: dict[str, Any] = {}
        for label in [b[2] for b in OU_BUCKETS]:
            items = groups.get(label, [])
            if not items:
                out[label] = {"match_count": 0}
                continue
            hits = sum(1 for r in items if r.over_25)
            implied_probs = [
                self._parse_fixture_odds(self.repo.fetch_odds_snapshots(r.fixture_id, limit=5)).get("implied_over_25")
                for r in items
            ]
            implied_probs = [p for p in implied_probs if p is not None]
            avg_implied = round(sum(implied_probs) / len(implied_probs), 4) if implied_probs else None
            actual = round(hits / len(items), 4)
            out[label] = {
                "match_count": len(items),
                "over_25_hit_rate_pct": _pct(hits, len(items)),
                "avg_implied_over_prob": avg_implied,
                "actual_over_prob": actual,
                "edge_estimate": round(actual - avg_implied, 4) if avg_implied is not None else None,
            }
        return out

    def run(self) -> dict[str, Any]:
        rows = self.load_rows()
        favorite_stats = self.summarize_buckets(rows)
        ou_stats = self.summarize_ou_buckets(rows)
        return {
            "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
            "match_rows": rows,
            "favorite_bucket_stats": favorite_stats,
            "ou_bucket_stats": ou_stats,
            "warnings": self.warnings,
            "sample_size": len(rows),
        }


def write_odds_artifacts(research_output: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    rows: list[OddsMatchRow] = research_output["match_rows"]
    with (ARTIFACT_DIR / "odds_bucket_research.csv").open("w", newline="", encoding="utf-8") as fh:
        if rows:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].to_csv_dict().keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow(row.to_csv_dict())
    summary = {
        "generated_at": research_output["generated_at"],
        "sample_size": research_output["sample_size"],
        "favorite_bucket_stats": research_output["favorite_bucket_stats"],
        "ou_bucket_stats": research_output["ou_bucket_stats"],
        "warnings": research_output["warnings"],
        "data_quality_warnings": [
            "Historical API-Football odds coverage is sparse for finished PL fixtures",
            "Favorite ROI is illustrative only — not betting advice",
        ],
    }
    (ARTIFACT_DIR / "odds_bucket_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
