"""Paper betting SQLite store — Phase A18."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from worldcup_predictor.config.settings import Settings, get_settings
from worldcup_predictor.database.migrations import ensure_schema_compat
from worldcup_predictor.database.repository import FootballIntelligenceRepository


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).isoformat()


def _current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


class PaperBettingStore:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._repo = FootballIntelligenceRepository(self.settings.sqlite_path or None)
        self._conn: sqlite3.Connection = self._repo._conn  # noqa: SLF001
        ensure_schema_compat(self._conn)

    def get_account(self, user_id: str, *, month: str | None = None) -> dict[str, Any] | None:
        m = month or _current_month()
        row = self._conn.execute(
            "SELECT * FROM paper_betting_accounts WHERE user_id = ? AND month = ?",
            (user_id, m),
        ).fetchone()
        return dict(row) if row else None

    def upsert_account(
        self,
        user_id: str,
        *,
        starting_bankroll: float,
        current_bankroll: float | None = None,
        currency: str = "EUR",
        risk_profile: str = "balanced",
        month: str | None = None,
    ) -> dict[str, Any]:
        m = month or _current_month()
        now = _utc_now()
        cur = current_bankroll if current_bankroll is not None else starting_bankroll
        existing = self.get_account(user_id, month=m)
        if existing:
            self._conn.execute(
                """
                UPDATE paper_betting_accounts
                SET starting_bankroll = ?, current_bankroll = ?, currency = ?,
                    risk_profile = ?, updated_at = ?
                WHERE id = ?
                """,
                (starting_bankroll, cur, currency, risk_profile, now, existing["id"]),
            )
            self._conn.commit()
            return self.get_account(user_id, month=m) or {}

        self._conn.execute(
            """
            INSERT INTO paper_betting_accounts (
                user_id, starting_bankroll, current_bankroll, currency,
                risk_profile, month, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (user_id, starting_bankroll, cur, currency, risk_profile, m, now, now),
        )
        self._conn.commit()
        return self.get_account(user_id, month=m) or {}

    def reset_account_month(
        self,
        user_id: str,
        *,
        starting_bankroll: float,
        currency: str = "EUR",
        risk_profile: str = "balanced",
        month: str | None = None,
    ) -> dict[str, Any]:
        m = month or _current_month()
        return self.upsert_account(
            user_id,
            starting_bankroll=starting_bankroll,
            current_bankroll=starting_bankroll,
            currency=currency,
            risk_profile=risk_profile,
            month=m,
        )

    def update_bankroll(self, account_id: int, new_balance: float) -> None:
        self._conn.execute(
            "UPDATE paper_betting_accounts SET current_bankroll = ?, updated_at = ? WHERE id = ?",
            (new_balance, _utc_now(), account_id),
        )
        self._conn.commit()

    def count_bets_today(self, user_id: str) -> int:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COUNT(*) FROM paper_betting_bets WHERE user_id = ? AND created_at LIKE ?",
            (user_id, f"{today}%"),
        ).fetchone()
        return int(row[0]) if row else 0

    def insert_bet(self, bet: dict[str, Any]) -> int:
        cols = [
            "user_id", "account_id", "fixture_id", "competition_key", "home_team", "away_team",
            "market", "prediction", "stake", "odds_decimal", "odds_estimated", "bet_quality_score",
            "combo_type", "combo_group_id", "source_page", "snapshot_id", "status", "created_at",
        ]
        values = [bet.get(c) for c in cols]
        placeholders = ", ".join("?" for _ in cols)
        cur = self._conn.execute(
            f"INSERT INTO paper_betting_bets ({', '.join(cols)}) VALUES ({placeholders})",
            values,
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_bets(
        self,
        user_id: str,
        *,
        status: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        if status:
            rows = self._conn.execute(
                """
                SELECT * FROM paper_betting_bets
                WHERE user_id = ? AND status = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, status, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT * FROM paper_betting_bets
                WHERE user_id = ?
                ORDER BY created_at DESC LIMIT ?
                """,
                (user_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def list_pending_bets(self, *, user_id: str | None = None, limit: int = 500) -> list[dict[str, Any]]:
        if user_id:
            rows = self._conn.execute(
                "SELECT * FROM paper_betting_bets WHERE user_id = ? AND status = 'pending' ORDER BY created_at LIMIT ?",
                (user_id, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM paper_betting_bets WHERE status = 'pending' ORDER BY created_at LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def settle_bet(
        self,
        bet_id: int,
        *,
        user_id: str,
        status: str,
        profit_loss: float | None,
        payout: float | None,
        odds_used: float | None,
        evaluation_source: str,
        reason: str,
    ) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            UPDATE paper_betting_bets
            SET status = ?, profit_loss = ?, settled_at = ?, settlement_reason = ?
            WHERE id = ? AND user_id = ?
            """,
            (status, profit_loss, now, reason, bet_id, user_id),
        )
        self._conn.execute(
            """
            INSERT INTO paper_betting_settlements (
                bet_id, user_id, status, profit_loss, payout, odds_used,
                evaluation_source, settled_at, reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (bet_id, user_id, status, profit_loss, payout, odds_used, evaluation_source, now, reason),
        )
        self._conn.commit()

    def save_monthly_report(self, user_id: str, month: str, report: dict[str, Any]) -> None:
        now = _utc_now()
        self._conn.execute(
            """
            INSERT INTO paper_betting_monthly_reports (user_id, month, report_json, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, month) DO UPDATE SET report_json = excluded.report_json, created_at = excluded.created_at
            """,
            (user_id, month, json.dumps(report, ensure_ascii=False), now),
        )
        self._conn.commit()

    def get_monthly_report(self, user_id: str, month: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT report_json FROM paper_betting_monthly_reports WHERE user_id = ? AND month = ?",
            (user_id, month),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

    def aggregate_stats(self, user_id: str, *, since: str | None = None) -> dict[str, Any]:
        query = "SELECT status, profit_loss, stake, bet_quality_score, market, combo_type FROM paper_betting_bets WHERE user_id = ?"
        params: list[Any] = [user_id]
        if since:
            query += " AND created_at >= ?"
            params.append(since)
        rows = self._conn.execute(query, params).fetchall()
        stats = {
            "total": 0, "pending": 0, "won": 0, "lost": 0, "void": 0, "partial": 0,
            "profit_loss": 0.0, "staked": 0.0, "qualities": [], "markets": {}, "combo_types": {},
        }
        for row in rows:
            r = dict(row)
            stats["total"] += 1
            st = str(r.get("status") or "pending")
            if st in stats:
                stats[st] += 1
            if r.get("profit_loss") is not None:
                stats["profit_loss"] += float(r["profit_loss"])
            if st != "pending":
                stats["staked"] += float(r.get("stake") or 0)
            if r.get("bet_quality_score") is not None:
                stats["qualities"].append(float(r["bet_quality_score"]))
            mk = str(r.get("market") or "unknown")
            stats["markets"].setdefault(mk, {"won": 0, "lost": 0})
            if st == "won":
                stats["markets"][mk]["won"] += 1
            elif st == "lost":
                stats["markets"][mk]["lost"] += 1
            ct = r.get("combo_type")
            if ct:
                stats["combo_types"].setdefault(ct, {"won": 0, "lost": 0})
                if st == "won":
                    stats["combo_types"][ct]["won"] += 1
                elif st == "lost":
                    stats["combo_types"][ct]["lost"] += 1
        return stats

    def admin_aggregate(self) -> dict[str, Any]:
        row = self._conn.execute("SELECT COUNT(DISTINCT user_id) FROM paper_betting_accounts").fetchone()
        users = int(row[0]) if row else 0
        row = self._conn.execute("SELECT COUNT(*) FROM paper_betting_bets").fetchone()
        bets = int(row[0]) if row else 0
        row = self._conn.execute(
            "SELECT COUNT(*) FROM paper_betting_bets WHERE status IN ('won','lost','partial')"
        ).fetchone()
        settled = int(row[0]) if row else 0
        return {"active_users": users, "total_bets": bets, "settled_bets": settled}
