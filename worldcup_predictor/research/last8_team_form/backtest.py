"""Leakage-safe historical backtest for Last-8 shadow Top5 selectors."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterator

from worldcup_predictor.research.ecse_historical_replay.replay_engine import ReplayRow, iter_replay_rows, replay_fixture
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.research.last8_team_form.constants import (
    COVERAGE_FULL,
    COVERAGE_PARTIAL_5_7,
    PROMOTION_MIN_PAIRED_FIXTURES,
)
from worldcup_predictor.research.last8_team_form.match_record import is_friendly_competition
from worldcup_predictor.research.last8_team_form.profile_builder import build_team_last8_goal_profile
from worldcup_predictor.research.last8_team_form.scenario_profile import build_shadow_scenario_profile
from worldcup_predictor.research.last8_team_form.shadow_selector import (
    select_baseline_top5,
    select_hybrid_top5,
    select_last8_aware_top5,
    select_scenario_diversified_top5,
    select_top3_variants,
    select_wde_aligned_top5,
)


@dataclass
class TeamHistoryIndex:
    """Pre-indexed completed matches by team for CSV backtest."""

    by_team: dict[str, list[dict[str, Any]]]

    @classmethod
    def from_connection(cls, conn: sqlite3.Connection) -> "TeamHistoryIndex":
        conn.row_factory = sqlite3.Row
        by_team: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for rec in conn.execute("SELECT row_hash, source_file, raw_row_json FROM external_historical_csv_raw_rows"):
            try:
                raw = json.loads(rec["raw_row_json"])
            except json.JSONDecodeError:
                continue
            d = str(raw.get("eventDate") or "")[:10]
            if not d:
                continue
            league = str(raw.get("league") or "")
            if is_friendly_competition(league):
                continue
            try:
                hg = int(float(raw.get("goalsHomeFullTime")))
                ag = int(float(raw.get("goalsAwayFullTime")))
            except (TypeError, ValueError):
                continue
            home = str(raw.get("homeTeam") or "").strip()
            away = str(raw.get("awayTeam") or "").strip()
            if not home or not away:
                continue
            kickoff = f"{d}T{str(raw.get('eventHour') or '12:00').strip() or '12:00'}"
            base = {
                "kickoff_utc": kickoff,
                "eventDate": d,
                "competition_key": league,
                "league": league,
                "home_team": home,
                "away_team": away,
                "home_goals": hg,
                "away_goals": ag,
                "row_hash": str(rec["row_hash"]),
            }
            by_team[home.lower()].append({**base, "_venue": "home"})
            by_team[away.lower()].append({**base, "_venue": "away"})
        for team in by_team:
            by_team[team].sort(key=lambda r: r["kickoff_utc"], reverse=True)
        return cls(by_team=dict(by_team))

    def records_before(
        self,
        team_name: str,
        *,
        before_kickoff: str,
        league: str | None = None,
        limit: int = 40,
    ) -> list[dict[str, Any]]:
        rows = self.by_team.get(team_name.strip().lower(), [])
        out: list[dict[str, Any]] = []
        for r in rows:
            if r["kickoff_utc"] >= before_kickoff:
                continue
            if league and str(r.get("league") or "") != league:
                continue
            out.append(r)
            if len(out) >= limit:
                break
        return out


METHOD_KEYS = (
    "baseline_top5",
    "wde_aligned_top5",
    "scenario_diversified_top5",
    "last8_aware_top5",
    "hybrid_top5",
)

TOP3_METHOD_KEYS = (
    "raw_ecse_top3",
    "wde_aligned_top3",
    "last8_aware_top3",
    "hybrid_coverage_top3",
)


def _hit_rate(hits: int, n: int) -> float:
    return round(100.0 * hits / n, 3) if n else 0.0


def _evaluate_lines(actual: str, lines: list[str]) -> bool:
    return actual in lines[: len(lines)]


def _full_distribution(row: ReplayRow) -> list[dict[str, Any]]:
    dist = generate_score_distribution(row.lambda_home, row.lambda_away)
    return dist[:15] if dist else row.top10


def _implied_direction(row: ReplayRow) -> str:
    ph = 1.0 / max(row.odds_home, 1.01)
    pd = 1.0 / max(row.odds_draw, 1.01)
    pa = 1.0 / max(row.odds_away, 1.01)
    t = ph + pd + pa
    ph, pa = ph / t, pa / t
    if ph >= pa:
        return "home_win"
    return "away_win"


def run_paired_backtest(
    conn: sqlite3.Connection,
    *,
    min_coverage: str = COVERAGE_PARTIAL_5_7,
    max_fixtures: int | None = None,
) -> dict[str, Any]:
    """Replay ECSE fixtures with Last-8 profiles built from pre-kickoff CSV history."""
    history = TeamHistoryIndex.from_connection(conn)
    allowed_coverage = {
        COVERAGE_FULL,
        COVERAGE_PARTIAL_5_7,
        "PARTIAL_5_TO_7",
        "FULL_8_MATCH_COVERAGE",
    }

    hits_top1: Counter[str] = Counter()
    hits_top3: Counter[str] = Counter()
    hits_top5: Counter[str] = Counter()
    hits_top3_methods: Counter[str] = Counter()
    n_total = 0
    n_paired = 0
    by_league: dict[str, Counter[str]] = defaultdict(Counter)
    coverage_hist: Counter[str] = Counter()
    segment: dict[str, Counter[str]] = defaultdict(Counter)

    for row in iter_replay_rows(conn):
        if max_fixtures and n_total >= max_fixtures:
            break
        n_total += 1
        home = row.match.split(" vs ")[0].strip()
        away = row.match.split(" vs ")[-1].strip()
        kickoff = row.kickoff if "T" in row.kickoff else f"{row.event_date}T12:00"

        home_records = history.records_before(home, before_kickoff=kickoff, league=row.league, limit=20)
        away_records = history.records_before(away, before_kickoff=kickoff, league=row.league, limit=20)
        if len(home_records) < 5:
            home_records = history.records_before(home, before_kickoff=kickoff, league=None, limit=20)
        if len(away_records) < 5:
            away_records = history.records_before(away, before_kickoff=kickoff, league=None, limit=20)

        home_profile = build_team_last8_goal_profile(
            team_name=home,
            fixture_kickoff_utc=kickoff,
            competition_context=row.league,
            match_records=home_records,
        )
        away_profile = build_team_last8_goal_profile(
            team_name=away,
            fixture_kickoff_utc=kickoff,
            competition_context=row.league,
            match_records=away_records,
        )
        hc = home_profile["identity"]["coverage_status"]
        ac = away_profile["identity"]["coverage_status"]
        coverage_hist[hc] += 1
        coverage_hist[ac] += 1

        if hc not in allowed_coverage or ac not in allowed_coverage:
            continue

        n_paired += 1
        dist = _full_distribution(row)
        scenario = build_shadow_scenario_profile(home_profile=home_profile, away_profile=away_profile)
        wde_dir = _implied_direction(row)

        methods = {
            "baseline_top5": select_baseline_top5(dist),
            "wde_aligned_top5": select_wde_aligned_top5(
                dist,
                wde_direction=wde_dir,
                odds_home=row.odds_home,
                odds_draw=row.odds_draw,
                odds_away=row.odds_away,
            ),
            "scenario_diversified_top5": select_scenario_diversified_top5(dist, scenario_profile=scenario),
            "last8_aware_top5": select_last8_aware_top5(dist, scenario_profile=scenario, wde_direction=wde_dir),
            "hybrid_top5": select_hybrid_top5(
                dist,
                scenario_profile=scenario,
                wde_direction=wde_dir,
                odds_home=row.odds_home,
                odds_draw=row.odds_draw,
                odds_away=row.odds_away,
            ),
        }
        top3v = select_top3_variants(
            dist,
            scenario_profile=scenario,
            wde_direction=wde_dir,
            odds_home=row.odds_home,
            odds_draw=row.odds_draw,
            odds_away=row.odds_away,
        )

        actual = row.actual_score
        if row.top1 == actual:
            hits_top1["canonical_top1"] += 1
        if actual in row.top5:
            hits_top5["canonical_top5"] += 1
        if actual in [x["scoreline"] for x in row.top10[:3]]:
            hits_top3["canonical_top3"] += 1

        for key, lines in methods.items():
            if _evaluate_lines(actual, lines):
                hits_top5[key] += 1
                by_league[row.league][key] += 1

        for key in TOP3_METHOD_KEYS:
            if _evaluate_lines(actual, top3v.get(key, [])):
                hits_top3_methods[key] += 1

        if row.actual_home == 0 or row.actual_away == 0:
            segment["clean_sheet_actual"]["n"] += 1
            if actual in methods["last8_aware_top5"]:
                segment["clean_sheet_actual"]["last8_hit"] += 1
            if actual in methods["baseline_top5"]:
                segment["clean_sheet_actual"]["baseline_hit"] += 1
        if row.actual_away == 1 or row.actual_home == 1:
            segment["one_goal_opponent"]["n"] += 1
            if actual in methods["last8_aware_top5"]:
                segment["one_goal_opponent"]["last8_hit"] += 1
            if actual in methods["baseline_top5"]:
                segment["one_goal_opponent"]["baseline_hit"] += 1
        if row.actual_home + row.actual_away >= 5:
            segment["high_score_tail"]["n"] += 1
            if actual in methods["last8_aware_top5"]:
                segment["high_score_tail"]["last8_hit"] += 1
            if actual in methods["baseline_top5"]:
                segment["high_score_tail"]["baseline_hit"] += 1

    metrics: dict[str, Any] = {
        "paired_fixtures": n_paired,
        "replay_rows_scanned": n_total,
        "coverage_histogram": dict(coverage_hist),
        "top1_hit_rate_pct": {
            "canonical_top1": _hit_rate(hits_top1["canonical_top1"], n_paired),
        },
        "top3_hit_rate_pct": {
            "canonical_top3": _hit_rate(hits_top3["canonical_top3"], n_paired),
            **{k: _hit_rate(hits_top3_methods[k], n_paired) for k in TOP3_METHOD_KEYS},
        },
        "top5_hit_rate_pct": {
            "canonical_top5": _hit_rate(hits_top5["canonical_top5"], n_paired),
            **{k: _hit_rate(hits_top5[k], n_paired) for k in METHOD_KEYS},
        },
        "top5_lift_vs_baseline_pp": {
            k: round(_hit_rate(hits_top5[k], n_paired) - _hit_rate(hits_top5["baseline_top5"], n_paired), 3)
            for k in METHOD_KEYS
            if k != "baseline_top5"
        },
        "top3_degradation_vs_raw_pp": {
            k: round(_hit_rate(hits_top3_methods[k], n_paired) - _hit_rate(hits_top3["canonical_top3"], n_paired), 3)
            for k in TOP3_METHOD_KEYS
            if k != "raw_ecse_top3"
        },
        "segment_analysis": {
            name: {
                "n": int(seg.get("n", 0)),
                "baseline_hit_rate_pct": _hit_rate(int(seg.get("baseline_hit", 0)), int(seg.get("n", 0))),
                "last8_hit_rate_pct": _hit_rate(int(seg.get("last8_hit", 0)), int(seg.get("n", 0))),
            }
            for name, seg in segment.items()
        },
        "league_breakdown_top5": {
            league: {k: _hit_rate(int(v), sum(by_league[league].values()) // max(len(METHOD_KEYS), 1)) for k, v in ctr.items()}
            for league, ctr in sorted(by_league.items(), key=lambda x: -sum(x[1].values()))[:15]
        },
        "promotion_gate": {
            "min_paired_fixtures": PROMOTION_MIN_PAIRED_FIXTURES,
            "paired_met": n_paired >= PROMOTION_MIN_PAIRED_FIXTURES,
            "top5_lift_last8_pp": round(
                _hit_rate(hits_top5["last8_aware_top5"], n_paired) - _hit_rate(hits_top5["baseline_top5"], n_paired),
                3,
            ),
            "top3_delta_last8_pp": round(
                _hit_rate(hits_top3_methods["last8_aware_top3"], n_paired) - _hit_rate(hits_top3["canonical_top3"], n_paired),
                3,
            ),
        },
    }
    return metrics
