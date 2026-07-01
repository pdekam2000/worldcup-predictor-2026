"""PHASE ECSE-1C — Lambda extraction from ECSE training odds features (research only)."""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

METHOD_VERSION = "ECSE-1C-v1"
MIN_DATA_QUALITY = 0.20
LAMBDA_FLOOR = 0.15
LAMBDA_CEIL = 6.0

# Weights for combining independent lambda estimates
WEIGHT_OU_25 = 0.40
WEIGHT_OU_15 = 0.20
WEIGHT_OU_35 = 0.15
WEIGHT_TEAM_SUM = 0.25

DATASET_SELECT_SQL = """
    SELECT
        registry_fixture_id,
        ft_home_closing,
        ft_away_closing,
        ft_draw_closing,
        btts_yes_closing,
        btts_no_closing,
        ou_over_15_closing,
        ou_under_15_closing,
        ou_over_25_closing,
        ou_under_25_closing,
        ou_over_35_closing,
        ou_under_35_closing,
        ou_over_45_closing,
        ou_under_45_closing,
        team_home_over_05_closing,
        team_home_under_05_closing,
        team_home_over_15_closing,
        team_home_under_15_closing,
        team_away_over_05_closing,
        team_away_under_05_closing,
        team_away_over_15_closing,
        team_away_under_15_closing,
        fh_home_closing,
        fh_draw_closing,
        fh_away_closing,
        dc_home_draw_closing,
        dc_home_away_closing,
        dc_draw_away_closing
    FROM ecse_training_dataset
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def implied_raw(odds: float | None) -> float | None:
    if odds is None or odds < 1.0:
        return None
    return 1.0 / float(odds)


def devig_two_way(over_odds: float | None, under_odds: float | None) -> float | None:
    """Return de-vigged probability for the over (or first) side."""
    p_over = implied_raw(over_odds)
    p_under = implied_raw(under_odds)
    if p_over is not None and p_under is not None:
        total = p_over + p_under
        if total <= 0:
            return None
        return p_over / total
    if p_over is not None:
        return min(max(p_over, 0.01), 0.99)
    return None


def devig_yes_no(yes_odds: float | None, no_odds: float | None) -> float | None:
    return devig_two_way(yes_odds, no_odds)


def _poisson_pmf(k: int, lam: float) -> float:
    lam = max(lam, 1e-9)
    return math.exp(-lam) * (lam**k) / math.factorial(k)


def prob_total_over(lam: float, line: float) -> float:
    """Poisson total goals strictly over Asian line (e.g. 2.5 -> >2 goals)."""
    lam = max(lam, 1e-9)
    if line == 1.5:
        k_max = 1
    elif line == 2.5:
        k_max = 2
    elif line == 3.5:
        k_max = 3
    elif line == 4.5:
        k_max = 4
    else:
        k_max = max(0, int(line))
    cdf = sum(_poisson_pmf(k, lam) for k in range(k_max + 1))
    return 1.0 - cdf


def solve_lambda_total_from_over(p_over: float, line: float) -> float | None:
    if p_over is None or p_over <= 0.01 or p_over >= 0.99:
        return None
    lo, hi = 0.2, 7.0
    for _ in range(64):
        mid = (lo + hi) / 2.0
        if prob_total_over(mid, line) < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def solve_lambda_team_from_over15(p_over: float) -> float | None:
    """P(team goals > 1) = 1 - e^-λ - λ e^-λ."""
    if p_over is None or p_over <= 0.01 or p_over >= 0.99:
        return None
    lo, hi = 0.2, 5.0
    for _ in range(64):
        mid = (lo + hi) / 2.0
        lam = max(mid, 1e-9)
        p = 1.0 - math.exp(-lam) * (1.0 + lam)
        if p < p_over:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def lambda_team_from_over05(p_over: float) -> float | None:
    if p_over is None or p_over <= 0.01 or p_over >= 0.99:
        return None
    return -math.log(1.0 - p_over)


def draw_proxy_from_double_chance(
    dc_home_draw: float | None,
    dc_draw_away: float | None,
    dc_home_away: float | None,
) -> float | None:
    i_hd = implied_raw(dc_home_draw)
    i_da = implied_raw(dc_draw_away)
    i_ha = implied_raw(dc_home_away)
    if i_hd is None or i_da is None or i_ha is None:
        if i_hd is not None and i_da is not None:
            return min(max((i_hd + i_da - 1.0) / 2.0, 0.05), 0.45)
        return None
    p_draw = (i_hd + i_da - i_ha) / 2.0
    return min(max(p_draw, 0.02), 0.50)


def outcome_probs_from_1x2(
    ft_home: float | None,
    ft_away: float | None,
    ft_draw: float | None,
    draw_proxy: float | None,
) -> tuple[float | None, float | None, float | None]:
    """De-vigged home/draw/away probabilities."""
    if ft_draw is not None:
        inv = [implied_raw(ft_home), implied_raw(ft_draw), implied_raw(ft_away)]
        if any(x is None for x in inv):
            return None, None, None
        total = sum(inv)  # type: ignore[arg-type]
        if total <= 0:
            return None, None, None
        p_h, p_d, p_a = (inv[0] / total, inv[1] / total, inv[2] / total)
        return p_h, p_d, p_a

    inv_h = implied_raw(ft_home)
    inv_a = implied_raw(ft_away)
    if inv_h is None or inv_a is None:
        return None, None, None

    p_d = draw_proxy
    if p_d is None:
        p_d = 0.26
    p_d = min(max(p_d, 0.05), 0.45)
    remain = 1.0 - p_d
    denom = inv_h + inv_a
    if denom <= 0:
        return None, None, None
    p_h = remain * inv_h / denom
    p_a = remain * inv_a / denom
    return p_h, p_d, p_a


def btts_prob_independent(lambda_home: float, lambda_away: float) -> float:
    lh = max(lambda_home, 1e-9)
    la = max(lambda_away, 1e-9)
    return 1.0 - math.exp(-lh) - math.exp(-la) + math.exp(-lh - la)


def _count_features(row: dict[str, Any]) -> int:
    keys = [
        "ft_home_closing",
        "ft_away_closing",
        "ft_draw_closing",
        "btts_yes_closing",
        "btts_no_closing",
        "ou_over_15_closing",
        "ou_over_25_closing",
        "ou_over_35_closing",
        "team_home_over_05_closing",
        "team_away_over_05_closing",
        "fh_home_closing",
        "fh_draw_closing",
        "fh_away_closing",
        "dc_home_draw_closing",
        "dc_home_away_closing",
        "dc_draw_away_closing",
    ]
    return sum(1 for k in keys if row.get(k) is not None)


def _data_quality_score(row: dict[str, Any], *, has_lambda: bool) -> float:
    score = 0.0
    if row.get("ou_over_25_closing") is not None:
        score += 0.25
    if row.get("ft_home_closing") is not None and row.get("ft_away_closing") is not None:
        score += 0.20
    if row.get("btts_yes_closing") is not None or row.get("btts_no_closing") is not None:
        score += 0.10
    if row.get("team_home_over_05_closing") is not None:
        score += 0.10
    if row.get("team_away_over_05_closing") is not None:
        score += 0.10
    if row.get("dc_home_draw_closing") is not None:
        score += 0.05
    if row.get("dc_draw_away_closing") is not None:
        score += 0.05
    if row.get("dc_home_away_closing") is not None:
        score += 0.05
    if row.get("ou_over_15_closing") is not None:
        score += 0.05
    if row.get("ou_over_35_closing") is not None:
        score += 0.05
    if has_lambda:
        score = min(score + 0.10, 1.0)
    return round(min(score, 1.0), 4)


def extract_lambdas(row: dict[str, Any]) -> dict[str, Any] | None:
    """Return lambda feature dict or None if insufficient odds."""
    missing_draw_flag = 1 if row.get("ft_draw_closing") is None else 0

    draw_proxy = draw_proxy_from_double_chance(
        row.get("dc_home_draw_closing"),
        row.get("dc_draw_away_closing"),
        row.get("dc_home_away_closing"),
    )
    p_home, p_draw, p_away = outcome_probs_from_1x2(
        row.get("ft_home_closing"),
        row.get("ft_away_closing"),
        row.get("ft_draw_closing"),
        draw_proxy,
    )

    # Total goals from O/U markets
    ou_estimates: list[tuple[float, float]] = []
    for line, over_key, under_key, weight in (
        (2.5, "ou_over_25_closing", "ou_under_25_closing", WEIGHT_OU_25),
        (1.5, "ou_over_15_closing", "ou_under_15_closing", WEIGHT_OU_15),
        (3.5, "ou_over_35_closing", "ou_under_35_closing", WEIGHT_OU_35),
    ):
        p_over = devig_two_way(row.get(over_key), row.get(under_key))
        lam = solve_lambda_total_from_over(p_over, line) if p_over is not None else None
        if lam is not None:
            ou_estimates.append((lam, weight))

    lambda_total_ou: float | None = None
    if ou_estimates:
        wsum = sum(w for _, w in ou_estimates)
        lambda_total_ou = sum(lam * w for lam, w in ou_estimates) / wsum

    # Team lambdas from team O/U
    p_th_over05 = devig_two_way(
        row.get("team_home_over_05_closing"), row.get("team_home_under_05_closing")
    )
    p_ta_over05 = devig_two_way(
        row.get("team_away_over_05_closing"), row.get("team_away_under_05_closing")
    )
    lambda_home_team = lambda_team_from_over05(p_th_over05) if p_th_over05 is not None else None
    lambda_away_team = lambda_team_from_over05(p_ta_over05) if p_ta_over05 is not None else None

    p_th_over15 = devig_two_way(
        row.get("team_home_over_15_closing"), row.get("team_home_under_15_closing")
    )
    p_ta_over15 = devig_two_way(
        row.get("team_away_over_15_closing"), row.get("team_away_under_15_closing")
    )
    if p_th_over15 is not None:
        lam15 = solve_lambda_team_from_over15(p_th_over15)
        if lam15 is not None:
            lambda_home_team = (
                lam15
                if lambda_home_team is None
                else (lambda_home_team * 0.6 + lam15 * 0.4)
            )
    if p_ta_over15 is not None:
        lam15 = solve_lambda_team_from_over15(p_ta_over15)
        if lam15 is not None:
            lambda_away_team = (
                lam15
                if lambda_away_team is None
                else (lambda_away_team * 0.6 + lam15 * 0.4)
            )

    lambda_total_team: float | None = None
    if lambda_home_team is not None and lambda_away_team is not None:
        lambda_total_team = lambda_home_team + lambda_away_team

    # Split from 1X2 strength
    share_home = 0.5
    if p_home is not None and p_away is not None and (p_home + p_away) > 0:
        share_home = p_home / (p_home + p_away)

    lambda_total: float | None = None
    if lambda_total_ou is not None and lambda_total_team is not None:
        lambda_total = lambda_total_ou * 0.65 + lambda_total_team * 0.35
    elif lambda_total_ou is not None:
        lambda_total = lambda_total_ou
    elif lambda_total_team is not None:
        lambda_total = lambda_total_team

    if lambda_total is None:
        if lambda_home_team is not None and lambda_away_team is not None:
            lambda_total = lambda_home_team + lambda_away_team
        else:
            return None

    lambda_home = lambda_total * share_home
    lambda_away = lambda_total * (1.0 - share_home)

    if lambda_home_team is not None:
        lambda_home = lambda_home * 0.55 + lambda_home_team * 0.45
    if lambda_away_team is not None:
        lambda_away = lambda_away * 0.55 + lambda_away_team * 0.45

    # BTTS calibration (gentle)
    p_btts = devig_yes_no(row.get("btts_yes_closing"), row.get("btts_no_closing"))
    if p_btts is not None and lambda_home > 0 and lambda_away > 0:
        model_btts = btts_prob_independent(lambda_home, lambda_away)
        if abs(model_btts - p_btts) > 0.03:
            scale = 1.0 + (p_btts - model_btts) * 0.25
            scale = min(max(scale, 0.85), 1.15)
            lambda_home *= scale
            lambda_away *= scale

    # Enforce lambda_total = home + away
    lambda_home = min(max(lambda_home, LAMBDA_FLOOR), LAMBDA_CEIL)
    lambda_away = min(max(lambda_away, LAMBDA_FLOOR), LAMBDA_CEIL)
    lambda_total = lambda_home + lambda_away

    if draw_proxy is None and p_draw is not None:
        draw_proxy = p_draw
    if draw_proxy is None:
        # League prior when neither DC nor 1X2 balance available
        draw_proxy = 0.26

    source_feature_count = _count_features(row)
    quality = _data_quality_score(row, has_lambda=True)
    if quality < MIN_DATA_QUALITY:
        return None

    return {
        "registry_fixture_id": row["registry_fixture_id"],
        "lambda_home": round(lambda_home, 6),
        "lambda_away": round(lambda_away, 6),
        "lambda_total": round(lambda_total, 6),
        "draw_proxy_probability": round(draw_proxy, 6),
        "implied_home_probability": round(p_home, 6) if p_home is not None else None,
        "implied_away_probability": round(p_away, 6) if p_away is not None else None,
        "implied_draw_probability": round(p_draw, 6) if p_draw is not None else None,
        "data_quality_score": quality,
        "missing_draw_flag": missing_draw_flag,
        "source_feature_count": source_feature_count,
        "method_version": METHOD_VERSION,
        "insufficient_odds_flag": 0,
    }


def _ddl_statements() -> tuple[str, ...]:
    return (
        """
        CREATE TABLE IF NOT EXISTS ecse_lambda_features (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            registry_fixture_id INTEGER NOT NULL UNIQUE,
            lambda_home REAL NOT NULL,
            lambda_away REAL NOT NULL,
            lambda_total REAL NOT NULL,
            draw_proxy_probability REAL,
            implied_home_probability REAL,
            implied_away_probability REAL,
            implied_draw_probability REAL,
            data_quality_score REAL NOT NULL,
            missing_draw_flag INTEGER NOT NULL DEFAULT 1,
            source_feature_count INTEGER NOT NULL DEFAULT 0,
            insufficient_odds_flag INTEGER NOT NULL DEFAULT 0,
            method_version TEXT NOT NULL,
            build_batch TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (registry_fixture_id) REFERENCES ecse_training_dataset(registry_fixture_id)
        )
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ecse_lambda_quality
        ON ecse_lambda_features(data_quality_score)
        """,
        """
        CREATE INDEX IF NOT EXISTS idx_ecse_lambda_method
        ON ecse_lambda_features(method_version)
        """,
    )


def ensure_ecse_lambda_features_table(conn: sqlite3.Connection) -> None:
    for ddl in _ddl_statements():
        conn.execute(ddl)
    conn.commit()


def _build_batch_id() -> str:
    return f"ECSE-1C-{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"


@dataclass
class LambdaBuildStats:
    dataset_rows_scanned: int = 0
    rows_inserted: int = 0
    rows_skipped_existing: int = 0
    rows_skipped_insufficient: int = 0
    rows_missing_draw: int = 0
    avg_lambda_total: float = 0.0
    avg_data_quality: float = 0.0
    build_batch: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_rows_scanned": self.dataset_rows_scanned,
            "rows_inserted": self.rows_inserted,
            "rows_skipped_existing": self.rows_skipped_existing,
            "rows_skipped_insufficient": self.rows_skipped_insufficient,
            "rows_missing_draw": self.rows_missing_draw,
            "avg_lambda_total": self.avg_lambda_total,
            "avg_data_quality": self.avg_data_quality,
            "build_batch": self.build_batch,
            "method_version": METHOD_VERSION,
        }


def build_ecse_lambda_features(
    conn: sqlite3.Connection,
    *,
    dry_run: bool = False,
    rebuild: bool = False,
) -> LambdaBuildStats:
    ensure_ecse_lambda_features_table(conn)
    stats = LambdaBuildStats(build_batch=_build_batch_id())

    if rebuild and not dry_run:
        conn.execute("DELETE FROM ecse_lambda_features")

    existing: set[int] = set()
    if not rebuild and not dry_run:
        existing = {int(r[0]) for r in conn.execute("SELECT registry_fixture_id FROM ecse_lambda_features")}

    insert_sql = """
        INSERT INTO ecse_lambda_features (
            registry_fixture_id, lambda_home, lambda_away, lambda_total,
            draw_proxy_probability, implied_home_probability, implied_away_probability,
            implied_draw_probability, data_quality_score, missing_draw_flag,
            source_feature_count, insufficient_odds_flag, method_version, build_batch, created_at
        ) VALUES (
            :registry_fixture_id, :lambda_home, :lambda_away, :lambda_total,
            :draw_proxy_probability, :implied_home_probability, :implied_away_probability,
            :implied_draw_probability, :data_quality_score, :missing_draw_flag,
            :source_feature_count, :insufficient_odds_flag, :method_version, :build_batch, :created_at
        )
    """

    batch: list[dict[str, Any]] = []
    lambda_totals: list[float] = []
    qualities: list[float] = []
    created_at = _utc_now()

    for db_row in conn.execute(DATASET_SELECT_SQL):
        stats.dataset_rows_scanned += 1
        row = dict(db_row)
        fid = int(row["registry_fixture_id"])
        if fid in existing:
            stats.rows_skipped_existing += 1
            continue

        extracted = extract_lambdas(row)
        if extracted is None:
            stats.rows_skipped_insufficient += 1
            continue

        if extracted["missing_draw_flag"]:
            stats.rows_missing_draw += 1

        extracted["build_batch"] = stats.build_batch
        extracted["created_at"] = created_at
        batch.append(extracted)
        lambda_totals.append(float(extracted["lambda_total"]))
        qualities.append(float(extracted["data_quality_score"]))

        if len(batch) >= 2000:
            if not dry_run:
                conn.executemany(insert_sql, batch)
            stats.rows_inserted += len(batch)
            batch.clear()

    if batch:
        if not dry_run:
            conn.executemany(insert_sql, batch)
        stats.rows_inserted += len(batch)

    if lambda_totals:
        stats.avg_lambda_total = round(sum(lambda_totals) / len(lambda_totals), 4)
    if qualities:
        stats.avg_data_quality = round(sum(qualities) / len(qualities), 4)

    if not dry_run:
        conn.commit()
    return stats


def audit_ecse_lambda_features(conn: sqlite3.Connection) -> dict[str, Any]:
    ensure_ecse_lambda_features_table(conn)
    total = conn.execute("SELECT COUNT(1) FROM ecse_lambda_features").fetchone()[0]
    if total == 0:
        return {"rows": 0}

    row = conn.execute(
        """
        SELECT
            COUNT(1) AS n,
            SUM(CASE WHEN lambda_home <= 0 OR lambda_away <= 0 OR lambda_total <= 0 THEN 1 ELSE 0 END) AS non_positive,
            SUM(CASE WHEN ABS(lambda_total - (lambda_home + lambda_away)) > 0.0001 THEN 1 ELSE 0 END) AS total_mismatch,
            AVG(lambda_home) AS avg_lh,
            AVG(lambda_away) AS avg_la,
            AVG(lambda_total) AS avg_lt,
            AVG(data_quality_score) AS avg_quality,
            SUM(missing_draw_flag) AS missing_draw,
            AVG(source_feature_count) AS avg_features,
            SUM(insufficient_odds_flag) AS insufficient
        FROM ecse_lambda_features
        """
    ).fetchone()

    return {
        "rows": total,
        "non_positive_lambdas": row[1],
        "lambda_total_mismatch": row[2],
        "avg_lambda_home": round(row[3], 4),
        "avg_lambda_away": round(row[4], 4),
        "avg_lambda_total": round(row[5], 4),
        "avg_data_quality_score": round(row[6], 4),
        "missing_draw_rows": row[7],
        "avg_source_feature_count": round(row[8], 2),
        "insufficient_odds_rows": row[9],
        "method_versions": [
            {"version": r[0], "count": r[1]}
            for r in conn.execute(
                "SELECT method_version, COUNT(1) FROM ecse_lambda_features GROUP BY method_version"
            ).fetchall()
        ],
    }


def lambda_fingerprint(conn: sqlite3.Connection) -> str:
    row = conn.execute(
        """
        SELECT COUNT(1), SUM(lambda_home), SUM(lambda_away), SUM(lambda_total)
        FROM ecse_lambda_features
        """
    ).fetchone()
    payload = json.dumps({"n": row[0], "lh": row[1], "la": row[2], "lt": row[3]}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:16]
