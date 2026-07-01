"""PHASE ECSE-X2-M2 — Implied probability features from ecse_training_dataset."""

from __future__ import annotations

import sqlite3
from typing import Any

PROB_STEMS = (
    "ft_home",
    "ft_away",
    "ft_draw",
    "btts_yes",
    "btts_no",
    "ou_over_15",
    "ou_under_15",
    "ou_over_25",
    "ou_under_25",
    "ou_over_35",
    "ou_under_35",
    "ou_over_45",
    "ou_under_45",
    "team_home_over_05",
    "team_home_over_15",
    "team_away_over_05",
    "team_away_over_15",
    "fh_home",
    "fh_draw",
    "fh_away",
    "corner_over_85",
    "corner_over_95",
    "corner_under_105",
)

FIXTURE_LOAD_SQL = """
    SELECT
        d.registry_fixture_id,
        d.league,
        d.season,
        d.kickoff_utc,
        d.kickoff_unix,
        d.home_team,
        d.away_team,
        d.feature_coverage_count,
        d.exact_score,
        d.home_goals,
        d.away_goals,
        {feature_cols}
    FROM ecse_training_dataset d
    INNER JOIN historical_fixture_results r
        ON r.registry_fixture_id = d.registry_fixture_id
    INNER JOIN ecse_score_distributions sd
        ON sd.registry_fixture_id = d.registry_fixture_id AND sd.rank = 1
    ORDER BY d.kickoff_unix, d.registry_fixture_id
"""


def _implied(odd: float | None) -> float | None:
    if odd is None or odd <= 1.0:
        return None
    return 1.0 / float(odd)


def _devig_pair(a: float | None, b: float | None) -> tuple[float | None, float | None]:
    if a is None or b is None:
        return a, b
    total = a + b
    if total <= 0:
        return None, None
    return a / total, b / total


def _devig_triple(
    a: float | None, b: float | None, c: float | None
) -> tuple[float | None, float | None, float | None]:
    vals = [v for v in (a, b, c) if v is not None]
    if len(vals) < 2:
        return a, b, c
    total = sum(vals)
    if total <= 0:
        return a, b, c
    out_a = a / total if a is not None else None
    out_b = b / total if b is not None else None
    out_c = c / total if c is not None else None
    return out_a, out_b, out_c


def build_prob_map(row: dict[str, Any]) -> dict[str, float | None]:
    raw = {stem: _implied(row.get(f"{stem}_closing")) for stem in PROB_STEMS}

    h, a, dr = _devig_triple(raw["ft_home"], raw["ft_away"], raw["ft_draw"])
    raw["ft_home"], raw["ft_away"], raw["ft_draw"] = h, a, dr

    y, n = _devig_pair(raw["btts_yes"], raw["btts_no"])
    raw["btts_yes"], raw["btts_no"] = y, n

    for stem in ("ou_over_15", "ou_over_25", "ou_over_35", "ou_over_45"):
        under = stem.replace("over", "under")
        o, u = _devig_pair(raw[stem], raw[under])
        raw[stem], raw[under] = o, u

    for side in ("team_home", "team_away"):
        o05, u05 = _devig_pair(raw[f"{side}_over_05"], raw.get(f"{side}_under_05"))
        o15, u15 = _devig_pair(raw[f"{side}_over_15"], raw.get(f"{side}_under_15"))
        raw[f"{side}_over_05"] = o05
        raw[f"{side}_over_15"] = o15

    fh, fd, fa = _devig_triple(raw["fh_home"], raw["fh_draw"], raw["fh_away"])
    raw["fh_home"], raw["fh_draw"], raw["fh_away"] = fh, fd, fa

    draw_proxy = dr
    if draw_proxy is None and h is not None and a is not None:
        draw_proxy = max(0.01, 1.0 - h - a)
    raw["draw_proxy"] = draw_proxy

    return raw


def load_fixture_records(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    feature_cols = ",\n        ".join(f"d.{stem}_closing" for stem in PROB_STEMS)
    sql = FIXTURE_LOAD_SQL.format(feature_cols=feature_cols)
    records: list[dict[str, Any]] = []
    for row in conn.execute(sql):
        item = dict(row)
        item["probs"] = build_prob_map(item)
        item["actual"] = str(item["exact_score"])
        records.append(item)
    return records


def load_baseline_top_scores(conn: sqlite3.Connection, *, top_n: int = 15) -> dict[int, list[dict[str, Any]]]:
    out: dict[int, list[dict[str, Any]]] = {}
    current_id: int | None = None
    bucket: list[dict[str, Any]] = []
    for row in conn.execute(
        """
        SELECT registry_fixture_id, scoreline, home_goals, away_goals, probability, rank
        FROM ecse_score_distributions
        ORDER BY registry_fixture_id, rank
        """
    ):
        fid = int(row["registry_fixture_id"])
        if current_id is not None and fid != current_id:
            out[current_id] = bucket[:top_n]
            bucket = []
        current_id = fid
        if len(bucket) < top_n:
            bucket.append(dict(row))
    if current_id is not None and bucket:
        out[current_id] = bucket[:top_n]
    return out
