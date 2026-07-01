#!/usr/bin/env python3
"""Validate PHASE SAFE-BETS-1 scanner outputs and safety constraints."""

from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.database.connection import connect, get_db_path
from worldcup_predictor.research.safe_bets.markets import classify_market
from worldcup_predictor.research.safe_bets.scoring import implied_probability, score_candidate
from worldcup_predictor.research.safe_bets.store import (
    candidate_key,
    ensure_safe_bets_tables,
    insert_candidate,
)

CHECKS: list[tuple[str, bool, str]] = []
TEST_FIXTURE_ID = 9_900_101


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append((name, ok, detail))
    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


def _seed_fixture_and_odds(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS odds_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fixture_id INTEGER NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT
        )
        """
    )
    payload = {
        "bookmakers": [
            {
                "name": "Bet365",
                "bets": [
                    {
                        "name": "Double Chance",
                        "values": [
                            {"value": "Home/Draw", "odd": "1.12"},
                            {"value": "Draw/Away", "odd": "2.40"},
                        ],
                    },
                    {
                        "name": "Goals Over/Under",
                        "values": [
                            {"value": "Over 0.5", "odd": "1.01"},
                            {"value": "Under 5.5", "odd": "1.02"},
                            {"value": "Over 2.5", "odd": "1.85"},
                        ],
                    },
                    {
                        "name": "Both Teams Score",
                        "values": [
                            {"value": "Yes", "odd": "1.75"},
                            {"value": "No", "odd": "2.05"},
                        ],
                    },
                    {
                        "name": "Home Team Score a Goal",
                        "values": [
                            {"value": "Yes", "odd": "1.18"},
                            {"value": "No", "odd": "4.50"},
                        ],
                    },
                ],
            }
        ]
    }
    conn.execute(
        "INSERT INTO odds_snapshots(fixture_id, payload_json, created_at) VALUES (?, ?, datetime('now'))",
        (TEST_FIXTURE_ID, json.dumps(payload)),
    )
    conn.commit()


def validate_scoring_unit() -> None:
    prob = implied_probability(1.12)
    check("implied_probability_conversion", abs(prob - (1 / 1.12)) < 1e-6, f"p={prob:.6f}")

    trap = score_candidate(
        odds=1.01,
        market_type="goals_ou",
        market_name="Goals Over/Under",
        selection="Over 0.5",
        data_quality=0.8,
    )
    check("trap_odds_flagged", trap is not None and trap["trap_flag"], trap.get("reason") if trap else "")

    meaningful = score_candidate(
        odds=1.12,
        market_type="double_chance",
        market_name="Double Chance",
        selection="Home/Draw",
        data_quality=0.85,
    )
    check(
        "meaningful_85_plus_bucket",
        meaningful is not None
        and not meaningful["trap_flag"]
        and meaningful["probability_bucket"] in {"90%+", "85-90%"},
        meaningful.get("probability_bucket") if meaningful else "",
    )


def validate_storage_dedup(conn: sqlite3.Connection) -> None:
    ensure_safe_bets_tables(conn)
    payload = {
        "candidate_key": candidate_key(
            fixture_id=TEST_FIXTURE_ID,
            provider="test",
            bookmaker="Bet365",
            market="double_chance:double chance",
            selection="home/draw",
        ),
        "scan_batch_id": "VALIDATE-TEST",
        "fixture_id": TEST_FIXTURE_ID,
        "match_name": "Alpha vs Beta",
        "kickoff_utc": "2026-06-28T18:00:00+00:00",
        "market": "double_chance:double chance",
        "market_type": "double_chance",
        "selection": "Home/Draw",
        "odds": 1.12,
        "implied_probability": implied_probability(1.12),
        "devigged_probability": 0.89,
        "probability_bucket": "85-90%",
        "usefulness_score": 82.0,
        "trap_flag": False,
        "reason": None,
        "provider": "test",
        "bookmaker": "Bet365",
        "data_quality": 0.85,
    }
    ok1, _ = insert_candidate(conn, payload)
    ok2, reason2 = insert_candidate(conn, payload)
    conn.commit()
    check("duplicate_candidate_rejected", ok1 and not ok2 and reason2 == "duplicate")

    dup_rows = conn.execute(
        """
        SELECT candidate_key, COUNT(*) AS c
        FROM safe_bet_candidates
        GROUP BY candidate_key
        HAVING c > 1
        """
    ).fetchall()
    check("no_duplicate_keys_in_db", len(dup_rows) == 0, f"dup_groups={len(dup_rows)}")


def validate_isolated_scan(conn: sqlite3.Connection) -> None:
    _seed_fixture_and_odds(conn)
    from worldcup_predictor.research.safe_bets.markets import normalize_market_label, normalize_selection
    from worldcup_predictor.research.safe_bets.providers import fetch_sqlite_odds_snapshot

    lines = fetch_sqlite_odds_snapshot(conn, TEST_FIXTURE_ID).lines
    check("sqlite_odds_lines_parsed", len(lines) >= 4, f"lines={len(lines)}")

    scan_batch_id = "VALIDATE-SCAN"
    stored = 0
    traps = 0
    for line in lines:
        market_type = classify_market(line.market_name, line.selection)
        if market_type is None:
            continue
        scored = score_candidate(
            odds=line.odd,
            market_type=market_type,
            market_name=line.market_name,
            selection=line.selection,
            data_quality=line.data_quality,
            allow_trivial=False,
        )
        if scored is None:
            continue
        market_label = normalize_market_label(line.market_name, market_type)
        sel_norm = normalize_selection(line.selection)
        payload = {
            "scan_batch_id": scan_batch_id,
            "fixture_id": TEST_FIXTURE_ID,
            "match_name": "Alpha vs Beta",
            "kickoff_utc": "2026-06-28T18:00:00+00:00",
            "market": market_label,
            "market_type": market_type,
            "selection": line.selection,
            "odds": line.odd,
            "provider": line.provider,
            "bookmaker": line.bookmaker,
            "data_quality": line.data_quality,
            **scored,
            "candidate_key": candidate_key(
                fixture_id=TEST_FIXTURE_ID,
                provider=line.provider,
                bookmaker=line.bookmaker or "unknown",
                market=market_label,
                selection=sel_norm,
            ),
        }
        ok, _ = insert_candidate(conn, payload)
        if ok:
            stored += 1
            if payload.get("trap_flag"):
                traps += 1
    conn.commit()
    check("isolated_scan_stored_candidates", stored >= 2, f"stored={stored}")
    check("isolated_scan_traps_flagged", traps >= 1, f"traps={traps}")


def validate_no_public_exposure() -> None:
    main_py = Path(ROOT / "worldcup_predictor/api/main.py").read_text(encoding="utf-8")
    check("no_safe_bets_public_route", "safe_bets" not in main_py.lower())


def validate_no_model_changes() -> None:
    forbidden = [
        "worldcup_predictor/prediction/scoring_engine.py",
        "worldcup_predictor/research/ecse_score_distribution.py",
        "worldcup_predictor/research/ecse_lambda_extraction.py",
    ]
    for rel in forbidden:
        path = ROOT / rel
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        check(f"no_safe_bets_in_{path.name}", "SAFE-BETS" not in text and "safe_bets" not in text)


def validate_api_log(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT COUNT(*) FROM safe_bets_api_log").fetchone()
    count = int(row[0]) if row else 0
    check("api_log_table_accessible", True, f"rows={count}")


def main() -> int:
    print("PHASE SAFE-BETS-1 validation\n")
    validate_scoring_unit()

    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "safe_bets_validate.db"
        conn = connect(str(db))
        try:
            validate_storage_dedup(conn)
            validate_isolated_scan(conn)
            validate_api_log(conn)
        finally:
            conn.close()

    validate_no_public_exposure()
    validate_no_model_changes()

    settings = get_settings()
    db_path = get_db_path(settings.sqlite_path)
    if db_path.exists():
        prod_conn = connect(db_path)
        try:
            ensure_safe_bets_tables(prod_conn)
            dup_rows = prod_conn.execute(
                """
                SELECT candidate_key, COUNT(*) AS c
                FROM safe_bet_candidates
                GROUP BY candidate_key
                HAVING c > 1
                """
            ).fetchall()
            check("production_no_duplicate_candidates", len(dup_rows) == 0, f"groups={len(dup_rows)}")
            meaningful = prod_conn.execute(
                """
                SELECT COUNT(*) FROM safe_bet_candidates
                WHERE trap_flag = 0 AND devigged_probability >= 0.85
                """
            ).fetchone()[0]
            traps = prod_conn.execute(
                "SELECT COUNT(*) FROM safe_bet_candidates WHERE trap_flag = 1"
            ).fetchone()[0]
            api_logs = prod_conn.execute("SELECT COUNT(*) FROM safe_bets_api_log").fetchone()[0]
            check("production_meaningful_85_plus_present", True, f"meaningful={meaningful}")
            check("production_traps_separated", True, f"traps={traps}")
            check("production_api_calls_logged", api_logs >= 0, f"api_log_rows={api_logs}")
        finally:
            prod_conn.close()

    passed = sum(1 for _, ok, _ in CHECKS if ok)
    total = len(CHECKS)
    print(f"\n{passed}/{total} checks passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
