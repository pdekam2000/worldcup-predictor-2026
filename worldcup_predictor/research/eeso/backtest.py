"""Leakage-safe EESO historical backtest — extends Last-8 paired replay."""

from __future__ import annotations

import sqlite3
from collections import Counter, defaultdict
from typing import Any

from worldcup_predictor.research.ecse_historical_replay.replay_engine import iter_replay_rows
from worldcup_predictor.research.ecse_score_distribution import generate_score_distribution
from worldcup_predictor.research.last8_team_form.backtest import TeamHistoryIndex
from worldcup_predictor.research.last8_team_form.constants import COVERAGE_FULL, COVERAGE_PARTIAL_5_7
from worldcup_predictor.research.last8_team_form.profile_builder import build_team_last8_goal_profile
from worldcup_predictor.research.last8_team_form.scenario_profile import build_shadow_scenario_profile
from worldcup_predictor.research.eeso.constants import METHOD_KEYS_TOP3, METHOD_KEYS_TOP5, NAMED_LEAGUE_SPECS
from worldcup_predictor.research.eeso.metrics import (
    actual_end_result,
    bucket_data_quality,
    bucket_entropy,
    bucket_mass,
    classify_named_league,
    compute_lift_pp,
    compute_relative_lift,
    hit_rate,
    implied_wde_direction,
    paired_comparison,
    top1_end_result_hit,
    topn_contains_end_result,
)
from worldcup_predictor.research.eeso.selectors import (
    select_baseline_top5,
    select_hybrid_top5,
    select_last8_aware_top5,
    select_scenario_diversified_top5,
    select_top3_variants,
    select_wde_aligned_top5,
)


def _full_distribution(row) -> list[dict[str, Any]]:
    dist = generate_score_distribution(row.lambda_home, row.lambda_away)
    return dist[:15] if dist else row.top10


def _evaluate_lines(actual: str, lines: list[str]) -> bool:
    return actual in lines[: len(lines)]


def run_eeso_paired_backtest(
    conn: sqlite3.Connection,
    *,
    max_fixtures: int | None = None,
    sample_dataset_rows: int = 0,
) -> dict[str, Any]:
    """Full leakage-safe replay with End Result metrics and named league breakdown."""
    history = TeamHistoryIndex.from_connection(conn)
    allowed_coverage = {COVERAGE_FULL, COVERAGE_PARTIAL_5_7, "PARTIAL_5_TO_7", "FULL_8_MATCH_COVERAGE"}

    hits_top1: Counter[str] = Counter()
    hits_top3: Counter[str] = Counter()
    hits_top5: Counter[str] = Counter()
    end_result_top1: Counter[str] = Counter()
    end_result_top3: Counter[str] = Counter()
    end_result_top5: Counter[str] = Counter()
    wde_end_result_hits = 0

    baseline_top5_pair: list[bool] = []
    method_top5_pairs: dict[str, list[bool]] = defaultdict(list)

    by_league_top1: dict[str, Counter[str]] = defaultdict(Counter)
    by_league_hits: dict[str, dict[str, Counter[str]]] = defaultdict(lambda: defaultdict(Counter))
    by_league_n: Counter[str] = Counter()

    segment_top5: dict[str, Counter[str]] = defaultdict(Counter)
    segment_n: Counter[str] = Counter()

    bucket_hits: dict[str, Counter[str]] = defaultdict(Counter)
    bucket_n: Counter[str] = Counter()

    coverage_hist: Counter[str] = Counter()
    dataset_rows: list[dict[str, Any]] = []

    n_total = 0
    n_paired = 0

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
        wde_dir = implied_wde_direction(row.odds_home, row.odds_draw, row.odds_away)
        actual = row.actual_score
        actual_er = actual_end_result(row.actual_home, row.actual_away)

        methods_top5 = {
            "canonical_top5": row.top5,
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
        methods_top3 = {
            "canonical_top3": [x["scoreline"] for x in row.top10[:3]],
            **top3v,
        }

        # Exact score hits
        if row.top1 == actual:
            hits_top1["canonical_top1"] += 1

        baseline_hit = _evaluate_lines(actual, methods_top5["baseline_top5"])
        baseline_top5_pair.append(baseline_hit)
        for key, lines in methods_top5.items():
            hit = _evaluate_lines(actual, lines)
            if hit:
                hits_top5[key] += 1
            if key not in ("canonical_top5", "baseline_top5"):
                method_top5_pairs[key].append(hit)

        for key, lines in methods_top3.items():
            if _evaluate_lines(actual, lines):
                hits_top3[key] += 1

        # End Result metrics (one increment per method per fixture)
        if wde_dir == actual_er:
            wde_end_result_hits += 1
        if top1_end_result_hit(row.top1, actual_er):
            end_result_top1["canonical_top1"] += 1
        for key, lines in methods_top5.items():
            if lines and top1_end_result_hit(lines[0], actual_er):
                end_result_top1[key] += 1
            if topn_contains_end_result(lines, actual_er):
                end_result_top5[key] += 1
        for key, lines in methods_top3.items():
            if topn_contains_end_result(lines, actual_er):
                end_result_top3[key] += 1

        # Named league breakdown
        league_key = classify_named_league(row)
        if league_key:
            by_league_n[league_key] += 1
            if row.top1 == actual:
                by_league_top1[league_key]["canonical_top1"] += 1
            for key, lines in methods_top5.items():
                if _evaluate_lines(actual, lines):
                    by_league_hits[league_key]["top5"][key] += 1
            for key, lines in methods_top3.items():
                if _evaluate_lines(actual, lines):
                    by_league_hits[league_key]["top3"][key] += 1
            if topn_contains_end_result(row.top5, actual_er):
                by_league_hits[league_key]["er_top5"]["canonical_top5"] += 1
            for key, lines in methods_top5.items():
                if key in ("canonical_top5", "baseline_top5"):
                    continue
                if topn_contains_end_result(lines, actual_er):
                    by_league_hits[league_key]["er_top5"][key] += 1

        # Segments
        segments: list[str] = []
        if row.actual_home == 0 or row.actual_away == 0:
            segments.append("clean_sheet_actual")
        if row.actual_away == 1 or row.actual_home == 1:
            segments.append("one_goal_opponent")
        if row.actual_home + row.actual_away >= 5:
            segments.append("high_score_tail")
        if is_btts_segment(row.actual_home, row.actual_away):
            segments.append("btts_yes")
        else:
            segments.append("btts_no")
        if row.actual_home + row.actual_away > 2:
            segments.append("ou_over_2_5")
        else:
            segments.append("ou_under_2_5")
        if actual_er == "home_win":
            segments.append("home_win_fixtures")
        elif actual_er == "away_win":
            segments.append("away_win_fixtures")
        else:
            segments.append("draw_fixtures")

        for seg in segments:
            segment_n[seg] += 1
            for key, lines in methods_top5.items():
                if _evaluate_lines(actual, lines):
                    segment_top5[seg][key] += 1

        # Buckets
        for bkey in (
            bucket_entropy(row.entropy),
            bucket_mass(row.top3_mass, kind="top3"),
            bucket_mass(row.top5_mass, kind="top5"),
            bucket_data_quality(row.data_quality_score),
        ):
            bucket_n[bkey] += 1
            for key, lines in methods_top5.items():
                if _evaluate_lines(actual, lines):
                    bucket_hits[bkey][key] += 1

        if sample_dataset_rows and len(dataset_rows) < sample_dataset_rows:
            from worldcup_predictor.research.eeso.dataset import build_fixture_dataset_row

            dataset_rows.append(
                build_fixture_dataset_row(
                    row,
                    home_profile=home_profile,
                    away_profile=away_profile,
                    full_distribution=dist,
                    wde_direction=wde_dir,
                )
            )

    baseline_rate = hit_rate(hits_top5["baseline_top5"], n_paired)
    top5_rates = {k: hit_rate(hits_top5[k], n_paired) for k in METHOD_KEYS_TOP5 if k in hits_top5}
    top3_rates = {k: hit_rate(hits_top3[k], n_paired) for k in METHOD_KEYS_TOP3 if k in hits_top3}
    top1_rates = {k: hit_rate(hits_top1[k], n_paired) for k in hits_top1}

    top5_lift = {
        k: compute_lift_pp(top5_rates.get(k, 0.0), baseline_rate)
        for k in top5_rates
        if k not in ("baseline_top5", "canonical_top5")
    }
    top3_lift = {
        k: compute_lift_pp(top3_rates.get(k, 0.0), top3_rates.get("canonical_top3", 0.0))
        for k in top3_rates
        if k != "canonical_top3"
    }

    paired_stats = {}
    for key, pairs in method_top5_pairs.items():
        if len(pairs) == len(baseline_top5_pair):
            paired_stats[key] = paired_comparison(baseline_hits=baseline_top5_pair, method_hits=pairs)

    best_top5_method = max(top5_lift.items(), key=lambda x: x[1])[0] if top5_lift else "none"
    best_top5_lift = top5_lift.get(best_top5_method, 0.0)

    named_league_breakdown = _build_named_league_breakdown(by_league_n, by_league_hits, by_league_top1, n_paired)

    return {
        "paired_fixtures": n_paired,
        "replay_rows_scanned": n_total,
        "coverage_histogram": dict(coverage_hist),
        "top1_hit_rate_pct": top1_rates,
        "top3_hit_rate_pct": top3_rates,
        "top5_hit_rate_pct": top5_rates,
        "top5_lift_vs_baseline_pp": top5_lift,
        "top5_relative_lift_pct": {
            k: compute_relative_lift(top5_rates.get(k, 0.0), baseline_rate) for k in top5_lift
        },
        "top3_lift_vs_canonical_pp": top3_lift,
        "end_result_accuracy_pct": {
            "wde_implied": hit_rate(wde_end_result_hits, n_paired),
            "top1": {k: hit_rate(v, n_paired) for k, v in end_result_top1.items()},
            "top3": {k: hit_rate(v, n_paired) for k, v in end_result_top3.items()},
            "top5": {k: hit_rate(v, n_paired) for k, v in end_result_top5.items()},
        },
        "paired_top5_comparison": paired_stats,
        "segment_analysis": _segment_rates(segment_n, segment_top5),
        "bucket_analysis": _segment_rates(bucket_n, bucket_hits),
        "named_league_breakdown": named_league_breakdown,
        "best_selector": {"method": best_top5_method, "top5_lift_pp": best_top5_lift},
        "dataset_sample": dataset_rows,
        "reproduces_last8_baseline": {
            "expected_canonical_top5_pct": 50.29,
            "actual_canonical_top5_pct": top5_rates.get("canonical_top5"),
            "expected_paired_fixtures": 72678,
        },
    }


def is_btts_segment(home: int, away: int) -> bool:
    return home > 0 and away > 0


def _segment_rates(segment_n: Counter[str], segment_hits: dict[str, Counter[str]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for seg, n in segment_n.items():
        hits = segment_hits.get(seg, Counter())
        out[seg] = {
            "n": int(n),
            "top5_hit_rate_pct": {k: hit_rate(int(v), n) for k, v in hits.items()},
        }
    return out


def _build_named_league_breakdown(
    by_league_n: Counter[str],
    by_league_hits: dict[str, dict[str, Counter[str]]],
    by_league_top1: dict[str, Counter[str]],
    total_paired: int,
) -> dict[str, Any]:
    from worldcup_predictor.research.eeso.metrics import league_breakdown_entry

    entries: dict[str, Any] = {}
    for league_key in NAMED_LEAGUE_SPECS:
        n = by_league_n.get(league_key, 0)
        top5_hits = by_league_hits.get(league_key, {}).get("top5", Counter())
        top3_hits = by_league_hits.get(league_key, {}).get("top3", Counter())
        er_hits = by_league_hits.get(league_key, {}).get("er_top5", Counter())

        canonical_top5 = hit_rate(top5_hits.get("canonical_top5", 0), n)
        canonical_top3 = hit_rate(top3_hits.get("canonical_top3", 0), n)
        canonical_top1 = hit_rate(by_league_top1[league_key].get("canonical_top1", 0), n)

        shadow_top5_rates = {
            k: hit_rate(v, n)
            for k, v in top5_hits.items()
            if k not in ("canonical_top5", "baseline_top5")
        }
        shadow_top3_rates = {
            k: hit_rate(v, n)
            for k, v in top3_hits.items()
            if k not in ("canonical_top3", "raw_ecse_top3")
        }
        best_top5_method = max(shadow_top5_rates.items(), key=lambda x: x[1])[0] if shadow_top5_rates else "none"
        best_top3_method = max(shadow_top3_rates.items(), key=lambda x: x[1])[0] if shadow_top3_rates else "none"
        best_top5 = shadow_top5_rates.get(best_top5_method, 0.0)
        best_top3 = shadow_top3_rates.get(best_top3_method, 0.0)

        shadow_er_rates = {
            k: hit_rate(v, n)
            for k, v in er_hits.items()
            if k != "canonical_top5"
        }
        best_er_method = max(shadow_er_rates.items(), key=lambda x: x[1])[0] if shadow_er_rates else "none"
        best_er = shadow_er_rates.get(best_er_method, 0.0)

        entries[league_key] = league_breakdown_entry(
            league_key=league_key,
            n=n,
            canonical_top1=canonical_top1,
            canonical_top3=canonical_top3,
            canonical_top5=canonical_top5,
            best_eeso_top3=best_top3,
            best_eeso_top5=best_top5,
            best_eeso_top3_method=best_top3_method,
            best_eeso_top5_method=best_top5_method,
            end_result_canonical_top5=hit_rate(er_hits.get("canonical_top5", 0), n),
            end_result_best_eeso=best_er,
        )
    entries["_total_paired_fixtures"] = total_paired
    return entries
