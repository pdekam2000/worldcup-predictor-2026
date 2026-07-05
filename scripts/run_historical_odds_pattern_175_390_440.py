#!/usr/bin/env python3
"""HISTORICAL ODDS PATTERN 1.75 / 3.90 / 4.40 — read-only analysis."""

from __future__ import annotations

import json
import math
import re
import sqlite3
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings

PHASE = "HISTORICAL-ODDS-PATTERN-175-390-440"
TARGET_FAV = 1.75
TARGET_DRAW = 3.90
TARGET_DOG = 4.40
EXACT_TOL = 0.005
CLOSE_FAV = (1.70, 1.80)
CLOSE_DRAW = (3.80, 4.00)
CLOSE_DOG = (4.25, 4.60)
ARTIFACT_JSON = ROOT / "artifacts" / "historical_odds_pattern_175_390_440.json"
REPORT_MD = ROOT / "reports" / "owner" / "historical_odds_pattern_175_390_440.md"


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _norm_team(value: str | None) -> str:
    text = (value or "").lower().strip()
    text = re.sub(r"\b(fc|cf|sc|afc|bsc|sv|vfb|tsg|ud)\b", " ", text)
    text = re.sub(r"[^a-z0-9]+", "", text)
    return text


def _parse_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        v = float(value)
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _parse_goals(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _schema_report(conn: sqlite3.Connection) -> dict[str, Any]:
    tables = [
        "fixtures",
        "fixture_results",
        "odds_snapshots",
        "historical_csv_odds_imports",
        "historical_csv_odds_prematch_clean",
        "historical_fixture_registry",
        "historical_fixture_results",
        "external_historical_csv_raw_rows",
        "external_match_history_staging",
        "oddalerts_odds_history",
    ]
    out: dict[str, Any] = {}
    for t in tables:
        try:
            cols = conn.execute(f"PRAGMA table_info({t})").fetchall()
            n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            out[t] = {"row_count": int(n), "columns": [c[1] for c in cols]}
        except sqlite3.Error as exc:
            out[t] = {"error": str(exc)}

    prematch_draw = conn.execute(
        "SELECT COUNT(1) FROM historical_csv_odds_prematch_clean WHERE market='ft_result' AND selection='draw'"
    ).fetchone()[0]
    prematch_home = conn.execute(
        "SELECT COUNT(1) FROM historical_csv_odds_prematch_clean WHERE market='ft_result' AND selection='home'"
    ).fetchone()[0]

    out["analysis_source"] = {
        "primary_odds_results": "external_historical_csv_raw_rows",
        "primary_odds_fields": {
            "home": "oddsFT_1",
            "draw": "oddsFT_X",
            "away": "oddsFT_2",
            "home_goals": "goalsHomeFullTime",
            "away_goals": "goalsAwayFullTime",
            "kickoff_date": "eventDate",
            "league": "league",
            "country": "countryName",
            "status": "status",
        },
        "odds_timing": "single pre-match closing line per row (football-data zip export; no separate open/close timestamps in raw JSON)",
        "bookmaker": "embedded in zip export (not split per bookmaker in raw rows)",
        "market": "full-time 1X2 (Match Winner)",
        "fixture_status_filter": "finished rows with non-null goalsHomeFullTime/goalsAwayFullTime",
        "dedup": "one row per external_historical_csv_raw_rows row_hash; composite key home|away|date for cross-source dedup",
        "secondary_source_note": "historical_csv_odds_prematch_clean has ft_result home/away only — draw selection count=0 (SOURCE_EXPORT_GAP); not used for 3-way pattern search",
        "production_odds_snapshots": "odds_snapshots + fixture_results — live cache only (~179 finished fixtures); supplemental",
        "results_verification": "final scores from goalsHomeFullTime/goalsAwayFullTime in external raw rows; BTTS/O2.5 derived from goals",
        "prematch_ft_draw_rows_in_clean_table": int(prematch_draw),
        "prematch_ft_home_rows_in_clean_table": int(prematch_home),
    }
    return out


def _load_external_1x2_rows(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT row_hash, source_file, raw_row_json FROM external_historical_csv_raw_rows"
    ).fetchall()
    out: list[dict[str, Any]] = []
    for r in rows:
        try:
            j = json.loads(r["raw_row_json"])
        except json.JSONDecodeError:
            continue
        oh = _parse_float(j.get("oddsFT_1"))
        od = _parse_float(j.get("oddsFT_X"))
        oa = _parse_float(j.get("oddsFT_2"))
        hg = _parse_goals(j.get("goalsHomeFullTime"))
        ag = _parse_goals(j.get("goalsAwayFullTime"))
        if oh is None or od is None or oa is None or hg is None or ag is None:
            continue
        if hg < 0 or ag < 0:
            continue
        home = str(j.get("homeTeam") or "")
        away = str(j.get("awayTeam") or "")
        event_date = str(j.get("eventDate") or "")[:10]
        kickoff = event_date
        if j.get("eventHour"):
            kickoff = f"{event_date}T{j.get('eventHour')}"
        total = hg + ag
        out.append(
            {
                "fixture_key": r["row_hash"],
                "source": "external_historical_csv_raw_rows",
                "home_team": home,
                "away_team": away,
                "kickoff_utc": kickoff,
                "event_date": event_date,
                "league": str(j.get("league") or ""),
                "country": str(j.get("countryName") or ""),
                "competition_name": str(j.get("league") or ""),
                "source_file": r["source_file"],
                "odds_home": oh,
                "odds_draw": od,
                "odds_away": oa,
                "home_goals": hg,
                "away_goals": ag,
                "total_goals": total,
                "btts_actual": 1 if hg > 0 and ag > 0 else 0,
                "over_25_actual": 1 if total > 2 else 0,
            }
        )
    return out


def _exact_match(a: float, b: float, tol: float = EXACT_TOL) -> bool:
    return abs(a - b) <= tol


def _in_range(v: float, lo: float, hi: float) -> bool:
    return lo <= v <= hi


def _normalize_fav_score(row: dict, fav_side: str) -> str:
    hg, ag = int(row["home_goals"]), int(row["away_goals"])
    if fav_side == "home":
        return f"{hg}-{ag}"
    return f"{ag}-{hg}"


def _fav_outcome(row: dict, fav_side: str) -> str:
    hg, ag = int(row["home_goals"]), int(row["away_goals"])
    if hg == ag:
        return "draw"
    if fav_side == "home":
        return "win" if hg > ag else "loss"
    return "win" if ag > hg else "loss"


def _orient_match(row: dict, fav_side: str) -> dict:
    oh, od, oa = row["odds_home"], row["odds_draw"], row["odds_away"]
    if fav_side == "home":
        fav_odds, dog_odds = oh, oa
    else:
        fav_odds, dog_odds = oa, oh
    return {
        **row,
        "fav_side": fav_side,
        "fav_odds": fav_odds,
        "draw_odds": od,
        "dog_odds": dog_odds,
        "raw_score": f"{row['home_goals']}-{row['away_goals']}",
        "norm_score": _normalize_fav_score(row, fav_side),
        "fav_outcome": _fav_outcome(row, fav_side),
    }


def _pick_orientation(row: dict, *, exact: bool) -> dict | None:
    oh, od, oa = row["odds_home"], row["odds_draw"], row["odds_away"]
    candidates: list[dict] = []
    if exact:
        if _exact_match(oh, TARGET_FAV) and _exact_match(od, TARGET_DRAW) and _exact_match(oa, TARGET_DOG):
            candidates.append(_orient_match(row, "home"))
        if _exact_match(oa, TARGET_FAV) and _exact_match(od, TARGET_DRAW) and _exact_match(oh, TARGET_DOG):
            candidates.append(_orient_match(row, "away"))
    else:
        if (
            _in_range(oh, *CLOSE_FAV)
            and _in_range(od, *CLOSE_DRAW)
            and _in_range(oa, *CLOSE_DOG)
        ):
            candidates.append(_orient_match(row, "home"))
        if (
            _in_range(oa, *CLOSE_FAV)
            and _in_range(od, *CLOSE_DRAW)
            and _in_range(oh, *CLOSE_DOG)
        ):
            candidates.append(_orient_match(row, "away"))
    if not candidates:
        return None
    return candidates[0]


def _score_table(counter: Counter, total: int, top_n: int = 20) -> list[dict]:
    rows = []
    for rank, (score, cnt) in enumerate(counter.most_common(top_n), 1):
        rows.append(
            {
                "rank": rank,
                "score": score,
                "count": cnt,
                "percentage": round(100.0 * cnt / total, 2) if total else 0,
            }
        )
    return rows


def _summary_stats(matches: list[dict]) -> dict[str, Any]:
    n = len(matches)
    if not n:
        return {"sample_size": 0}
    fav_w = sum(1 for m in matches if m["fav_outcome"] == "win")
    dr = sum(1 for m in matches if m["fav_outcome"] == "draw")
    dog_w = sum(1 for m in matches if m["fav_outcome"] == "loss")
    btts = sum(1 for m in matches if int(m["btts_actual"]) == 1)
    over25 = sum(1 for m in matches if int(m["over_25_actual"]) == 1)
    goals = [int(m["total_goals"]) for m in matches]
    goals_sorted = sorted(goals)
    med = goals_sorted[len(goals_sorted) // 2]
    return {
        "sample_size": n,
        "favorite_win_pct": round(100 * fav_w / n, 2),
        "draw_pct": round(100 * dr / n, 2),
        "underdog_win_pct": round(100 * dog_w / n, 2),
        "btts_yes_pct": round(100 * btts / n, 2),
        "over_2_5_pct": round(100 * over25 / n, 2),
        "under_2_5_pct": round(100 * (n - over25) / n, 2),
        "avg_total_goals": round(sum(goals) / n, 3),
        "median_total_goals": med,
    }


def _implied_probs(fav: float, draw: float, dog: float) -> tuple[float, float, float]:
    raw = [1 / fav, 1 / draw, 1 / dog]
    s = sum(raw)
    return tuple(x / s for x in raw)


def _distance(p1: tuple[float, float, float], p2: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


def _nearest_neighbors(all_rows: list[dict], k: int) -> list[dict]:
    target = _implied_probs(TARGET_FAV, TARGET_DRAW, TARGET_DOG)
    scored: list[tuple[float, dict, str]] = []
    for row in all_rows:
        if row["odds_home"] <= row["odds_away"]:
            side = "home"
            p = _implied_probs(row["odds_home"], row["odds_draw"], row["odds_away"])
        else:
            side = "away"
            p = _implied_probs(row["odds_away"], row["odds_draw"], row["odds_home"])
        dist = _distance(p, target)
        scored.append((dist, row, side))
    scored.sort(key=lambda x: x[0])
    out = []
    for dist, row, side in scored[:k]:
        out.append(
            {
                "fixture_key": row["fixture_key"],
                "distance": round(dist, 6),
                "fav_side": side,
                "odds_home": row["odds_home"],
                "odds_draw": row["odds_draw"],
                "odds_away": row["odds_away"],
                "raw_score": f"{row['home_goals']}-{row['away_goals']}",
                "norm_score": _normalize_fav_score(row, side),
                "kickoff_utc": row.get("kickoff_utc"),
                "league": row.get("league"),
            }
        )
    return out


def _time_bucket(kickoff: str | None) -> str:
    if not kickoff:
        return "unknown"
    try:
        y = int(str(kickoff)[:4])
    except ValueError:
        return "unknown"
    if y < 2018:
        return "before_2018"
    if y <= 2021:
        return "2018-2021"
    if y <= 2024:
        return "2022-2024"
    return "2025-present"


def _comp_segment(row: dict) -> str:
    league = str(row.get("league") or "").upper().strip()
    source = str(row.get("source_file") or "").lower()
    country = str(row.get("country") or "").lower()
    text = f"{league} {source} {country}"

    if any(x in text for x in ("world cup", "worldcup", "euro ", "euro20", "copa america", "nations league", "qualif", "international")):
        return "national_teams"
    if any(x in text for x in ("champions", "europa", "conference", "uefa", "cl1", "el1")):
        return "uefa_club"
    if any(x in text for x in ("world cup", "wc ", "fifa")):
        return "world_cup_major"
    # football-data league codes: EN1, SP1, IT1, FR1, DE1, NL1, US1, BR1, JP1, etc.
    domestic_codes = (
        "EN1", "EN2", "EN3", "EN4", "SP1", "SP2", "IT1", "IT2", "FR1", "FR2",
        "DE1", "DE2", "NL1", "BE1", "PT1", "TR1", "GR1", "RU1", "SC1", "PL1",
        "US1", "US2", "BR1", "BR2", "JP1", "JP2", "MX1", "AR1", "AU1", "CN1",
    )
    if league in domestic_codes or re.match(r"^[A-Z]{2}\d$", league):
        return "domestic_leagues"
    if "football-" in source and not any(x in source for x in ("champions", "europa", "world")):
        return "domestic_leagues"
    return "other"


def _analyze_sample(matches: list[dict], label: str) -> dict[str, Any]:
    norm_c = Counter(m["norm_score"] for m in matches)
    raw_c = Counter(m["raw_score"] for m in matches)
    stats = _summary_stats(matches)
    top3 = norm_c.most_common(3)
    return {
        "label": label,
        "stats": stats,
        "normalized_score_frequencies": _score_table(norm_c, len(matches), 20),
        "raw_score_frequencies": _score_table(raw_c, len(matches), 20),
        "top3_scores": [{"score": s, "count": c} for s, c in top3],
    }


def render_md(report: dict) -> str:
    lines = [
        "# Historical Odds Pattern Analysis — 1.75 / 3.90 / 4.40",
        "",
        f"**Generated:** {report['generated_at_utc']}",
        "**Mode:** read-only",
        "",
        "## Phase 1 — Schema & Data Sources",
        "",
        f"- Primary source: `{report['phase1_schema']['analysis_source']['primary_odds_results']}`",
        f"- Odds fields: home=`oddsFT_1`, draw=`oddsFT_X`, away=`oddsFT_2`",
        f"- Results: `goalsHomeFullTime` / `goalsAwayFullTime`",
        f"- Canonical fixtures loaded: **{report['phase1_schema'].get('canonical_1x2_fixtures_loaded', 0):,}**",
        f"- OddAlerts prematch draw gap: **{report['phase1_schema']['analysis_source']['prematch_ft_draw_rows_in_clean_table']}** ft_result draw rows",
        "",
    ]

    for key in ("phase2_exact", "phase3_close"):
        block = report[key]
        lines += [f"## {block['label']}", "", f"Sample size: **{block['stats'].get('sample_size', 0)}**", ""]
        if block["stats"].get("sample_size"):
            s = block["stats"]
            lines += [
                f"- Favorite win: {s.get('favorite_win_pct')}%",
                f"- Draw: {s.get('draw_pct')}%",
                f"- Underdog win: {s.get('underdog_win_pct')}%",
                f"- BTTS Yes: {s.get('btts_yes_pct')}%",
                f"- Over 2.5: {s.get('over_2_5_pct')}%",
                f"- Avg total goals: {s.get('avg_total_goals')}",
                "",
                "### Normalized score frequencies (Top 20)",
                "",
                "| Rank | Favorite-perspective score | Count | Percentage |",
                "| --- | --- | ---: | ---: |",
            ]
            for r in block["normalized_score_frequencies"]:
                lines.append(f"| {r['rank']} | {r['score']} | {r['count']} | {r['percentage']}% |")
            lines.append("")

    p4 = report.get("phase4_nearest_neighbors", {})
    if p4:
        lines += ["## Phase 4 — Nearest Implied-Probability Neighbors", ""]
        lines += [
            "| Sample | Most common score | Count | % | 2nd | 3rd |",
            "| --- | --- | ---: | ---: | --- | --- |",
        ]
        for k in ("25", "50", "100", "250"):
            block = p4.get(k, {})
            cr = block.get("comparison_row") or {}
            if not cr.get("sample"):
                continue
            lines.append(
                f"| {cr['sample']} | {cr.get('most_common')} | {cr.get('count')} | {cr.get('pct')} | {cr.get('2nd')} | {cr.get('3rd')} |"
            )
        lines.append("")

    p6 = report.get("phase6_time_segments", {})
    if p6:
        lines += ["## Phase 6 — Time Segments (close band)", ""]
        for bucket, block in p6.items():
            if not block.get("sample_size"):
                continue
            lines.append(f"### {bucket} (N={block['sample_size']})")
            lines.append(
                f"Fav {block.get('favorite_win_pct')}% | Draw {block.get('draw_pct')}% | Dog {block.get('underdog_win_pct')}%"
            )
            top5 = block.get("top5_normalized_scores") or []
            if top5:
                lines.append("Top scores: " + ", ".join(f"{x['score']} ({x['count']})" for x in top5))
            lines.append("")

    p7 = report.get("phase7_competition_segments", {})
    if p7:
        lines += [
            "## Phase 7 — Competition Segments (close band)",
            "",
            "| Segment | N | Fav Win % | Draw % | Dog Win % | Most Common Score |",
            "| --- | ---: | ---: | ---: | ---: | --- |",
        ]
        for seg, block in p7.items():
            label = block.get("label", "")
            mc = block.get("most_common_score") or "-"
            if block.get("sample_size", 0) < 10:
                mc = f"{mc} ({label or 'LOW_SAMPLE'})"
            lines.append(
                f"| {seg} | {block.get('sample_size', 0)} | {block.get('favorite_win_pct', '-')} | {block.get('draw_pct', '-')} | {block.get('underdog_win_pct', '-')} | {mc} |"
            )
        lines.append("")

    lines += ["## Phase 8 — Final Summary", "", "```json", json.dumps(report["phase8_final"], indent=2), "```", ""]
    top15 = report["phase8_final"].get("top15_normalized_close") or []
    if top15:
        lines += [
            "### Top 15 normalized exact-score frequencies (close band)",
            "",
            "| Rank | Favorite-perspective score | Count | Percentage |",
            "| --- | --- | ---: | ---: |",
        ]
        for r in top15:
            lines.append(f"| {r['rank']} | {r['score']} | {r['count']} | {r['percentage']}% |")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    settings = get_settings()
    conn = sqlite3.connect(f"file:{settings.sqlite_path}?mode=ro", uri=True)
    report: dict[str, Any] = {"phase": PHASE, "generated_at_utc": _utc_now()}

    report["phase1_schema"] = _schema_report(conn)
    all_rows = _load_external_1x2_rows(conn)
    report["phase1_schema"]["canonical_1x2_fixtures_loaded"] = len(all_rows)

    exact_matches: list[dict] = []
    close_matches: list[dict] = []
    for row in all_rows:
        ex = _pick_orientation(row, exact=True)
        if ex:
            exact_matches.append(ex)
        cl = _pick_orientation(row, exact=False)
        if cl:
            close_matches.append(cl)

    p2 = _analyze_sample(exact_matches, "Phase 2 — Exact match 1.75 / 3.90 / 4.40")
    p2["home_favorite_count"] = sum(1 for m in exact_matches if m["fav_side"] == "home")
    p2["away_favorite_count"] = sum(1 for m in exact_matches if m["fav_side"] == "away")
    if exact_matches:
        dates = sorted(str(m.get("kickoff_utc") or m.get("event_date") or "") for m in exact_matches)
        p2["date_range"] = {"min": dates[0], "max": dates[-1]}
        p2["competitions"] = sorted({str(m.get("league") or "?") for m in exact_matches})[:30]
    report["phase2_exact"] = p2

    p3 = _analyze_sample(close_matches, "Phase 3 — Close match band")
    report["phase3_close"] = p3

    nn_sizes = [25, 50, 100, 250]
    phase4: dict[str, Any] = {}
    for k in nn_sizes:
        sample = _nearest_neighbors(all_rows, k)
        if not sample:
            phase4[str(k)] = {"sample_size": 0}
            continue
        c = Counter(x["norm_score"] for x in sample)
        top10 = c.most_common(10)
        phase4[str(k)] = {
            "sample_size": len(sample),
            "top10_normalized_scores": [
                {"score": s, "count": n, "pct": round(100 * n / len(sample), 2)} for s, n in top10
            ],
            "comparison_row": {
                "sample": k,
                "most_common": top10[0][0] if top10 else None,
                "count": top10[0][1] if top10 else 0,
                "pct": round(100 * top10[0][1] / len(sample), 2) if top10 else 0,
                "2nd": top10[1][0] if len(top10) > 1 else None,
                "3rd": top10[2][0] if len(top10) > 2 else None,
            },
        }
    report["phase4_nearest_neighbors"] = phase4

    phase6: dict[str, Any] = {}
    for bucket in ("before_2018", "2018-2021", "2022-2024", "2025-present"):
        seg = [m for m in close_matches if _time_bucket(m.get("kickoff_utc")) == bucket]
        if not seg:
            phase6[bucket] = {"sample_size": 0}
            continue
        st = _summary_stats(seg)
        top5 = Counter(m["norm_score"] for m in seg).most_common(5)
        phase6[bucket] = {**st, "top5_normalized_scores": [{"score": s, "count": c} for s, c in top5]}
    report["phase6_time_segments"] = phase6

    phase7: dict[str, Any] = {}
    for seg_name in ("national_teams", "domestic_leagues", "uefa_club", "world_cup_major", "other"):
        seg = [m for m in close_matches if _comp_segment(m) == seg_name]
        if len(seg) < 10:
            st = _summary_stats(seg)
            top1 = Counter(m["norm_score"] for m in seg).most_common(1)
            phase7[seg_name] = {
                "sample_size": len(seg),
                "label": "LOW_SAMPLE",
                "favorite_win_pct": st.get("favorite_win_pct"),
                "draw_pct": st.get("draw_pct"),
                "underdog_win_pct": st.get("underdog_win_pct"),
                "most_common_score": top1[0][0] if top1 else None,
            }
            continue
        st = _summary_stats(seg)
        top1 = Counter(m["norm_score"] for m in seg).most_common(1)
        phase7[seg_name] = {
            "sample_size": len(seg),
            "favorite_win_pct": st.get("favorite_win_pct"),
            "draw_pct": st.get("draw_pct"),
            "underdog_win_pct": st.get("underdog_win_pct"),
            "most_common_score": top1[0][0] if top1 else None,
        }
    report["phase7_competition_segments"] = phase7

    def _top3(block: dict) -> list[str | None]:
        t = block.get("top3_scores") or []
        scores = [x["score"] for x in t[:3]]
        while len(scores) < 3:
            scores.append(None)
        return scores

    top15 = p3["normalized_score_frequencies"][:15]
    t3e = _top3(p2)
    t3c = _top3(p3)
    phase8 = {
        "exact_odds": {
            "total_matches": p2["stats"].get("sample_size", 0),
            "most_repeated": t3e[0],
            "second_most_repeated": t3e[1],
            "third_most_repeated": t3e[2],
            "favorite_win_rate": p2["stats"].get("favorite_win_pct"),
            "draw_rate": p2["stats"].get("draw_pct"),
            "underdog_win_rate": p2["stats"].get("underdog_win_pct"),
        },
        "close_odds_range": {
            "total_matches": p3["stats"].get("sample_size", 0),
            "most_repeated": t3c[0],
            "second_most_repeated": t3c[1],
            "third_most_repeated": t3c[2],
            "favorite_win_rate": p3["stats"].get("favorite_win_pct"),
            "draw_rate": p3["stats"].get("draw_pct"),
            "underdog_win_rate": p3["stats"].get("underdog_win_pct"),
        },
        "nearest_neighbors_stability": {
            k: phase4[str(k)]["comparison_row"]
            for k in nn_sizes
            if str(k) in phase4 and phase4[str(k)].get("sample_size")
        },
        "dominant_pattern": None,
        "predictive_use": None,
        "top15_normalized_close": top15,
    }
    close_n = p3["stats"].get("sample_size", 0)
    if close_n >= 100:
        top1_pct = top15[0]["percentage"] if top15 else 0
        phase8["dominant_pattern"] = "Yes" if top1_pct >= 15 else "No"
        phase8["predictive_use"] = (
            "Yes" if close_n >= 250 and top1_pct >= 12 else ("Weak" if close_n >= 50 else "No")
        )
    elif close_n >= 30:
        phase8["dominant_pattern"] = "Unclear"
        phase8["predictive_use"] = "Weak"
    else:
        phase8["dominant_pattern"] = "No"
        phase8["predictive_use"] = "No"
    report["phase8_final"] = phase8

    conn.close()

    ARTIFACT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_JSON.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    REPORT_MD.write_text(render_md(report), encoding="utf-8")

    print(
        json.dumps(
            {
                "artifact": str(ARTIFACT_JSON),
                "report": str(REPORT_MD),
                "canonical_fixtures": len(all_rows),
                "exact_n": len(exact_matches),
                "close_n": len(close_matches),
            },
            indent=2,
        )
    )
    print("HISTORICAL_ODDS_PATTERN_175_390_440_ANALYSIS_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
