#!/usr/bin/env python3
"""Phase A18 — Paper betting simulator validation."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for rel in (
        "worldcup_predictor/paper_betting/store.py",
        "worldcup_predictor/paper_betting/service.py",
        "worldcup_predictor/paper_betting/settlement.py",
        "worldcup_predictor/paper_betting/analytics.py",
        "worldcup_predictor/api/routes/paper_betting.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file())

    mig = (ROOT / "worldcup_predictor/database/migrations.py").read_text(encoding="utf-8")
    record(checks, "ddl_accounts", "paper_betting_accounts" in mig)
    record(checks, "ddl_bets", "paper_betting_bets" in mig)
    record(checks, "ddl_settlements", "paper_betting_settlements" in mig)
    record(checks, "ddl_reports", "paper_betting_monthly_reports" in mig)

    api = (ROOT / "worldcup_predictor/api/routes/paper_betting.py").read_text(encoding="utf-8")
    for ep in ("/account", "/bets", "/summary", "/monthly-report", "/strategy-comparison", "settle-pending"):
        record(checks, f"api_{ep.strip('/')}", ep in api)

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    record(checks, "ui_route", "/paper-betting" in app)
    record(checks, "ui_nav", "Paper Betting" in (FRONTEND / "src/lib/navConfig.js").read_text(encoding="utf-8"))
    record(checks, "disclaimer_ui", "Virtual betting is for analysis" in (FRONTEND / "src/pages/PaperBettingPage.jsx").read_text(encoding="utf-8"))

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    scoring = (ROOT / "worldcup_predictor/prediction/scoring_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "WeightedDecision" in wde)
    record(checks, "scoring_unchanged", "class ScoringEngine" in scoring)

    try:
        from worldcup_predictor.database.migrations import ensure_schema_compat
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.paper_betting.analytics import build_monthly_report, build_strategy_comparison, build_summary
        from worldcup_predictor.paper_betting.service import create_or_update_account, get_summary, list_bets, place_bet, place_combo_bets
        from worldcup_predictor.paper_betting.settlement import compute_profit_loss, settle_pending_bets
        from worldcup_predictor.paper_betting.store import PaperBettingStore

        repo = FootballIntelligenceRepository()
        ensure_schema_compat(repo._conn)

        uid_a = f"test-a18-{uuid.uuid4().hex[:8]}"
        uid_b = f"test-a18-{uuid.uuid4().hex[:8]}"

        acc = create_or_update_account(uid_a, starting_bankroll=100.0, currency="EUR", risk_profile="balanced")
        record(checks, "account_creation", acc.get("status") == "ok" and acc.get("account"))

        bet = place_bet(
            uid_a,
            fixture_id=99999001,
            market="btts",
            prediction="yes",
            stake=5.0,
            odds_decimal=1.85,
            bet_quality_score=72.0,
            plan="pro",
        )
        record(checks, "add_single_bet", bet.get("status") == "ok")

        combo = place_combo_bets(
            uid_a,
            legs=[
                {"fixture_id": 99999002, "market": "1x2", "prediction": "home", "bet_quality_score": 80, "odds_decimal": 2.1},
                {"fixture_id": 99999003, "market": "btts", "prediction": "yes", "bet_quality_score": 75, "odds_decimal": 1.7},
            ],
            combo_type="balanced",
            plan="pro",
        )
        record(checks, "add_combo_bet", combo.get("status") == "ok")

        store = PaperBettingStore()
        account = store.get_account(uid_a)
        record(checks, "bankroll_deducted", float(account["current_bankroll"]) < 100.0)

        profit, payout, reason = compute_profit_loss(bet_status="won", stake=10.0, odds_decimal=2.0)
        record(checks, "won_settlement_math", profit == 10.0 and payout == 20.0)
        profit_l, _, _ = compute_profit_loss(bet_status="lost", stake=10.0, odds_decimal=2.0)
        record(checks, "lost_settlement_math", profit_l == -10.0)

        roi_summary = get_summary(uid_a, period="all", plan="pro")
        record(checks, "roi_summary", "roi_pct" in roi_summary)

        strat = build_strategy_comparison(store, uid_a, bankroll=100.0)
        record(checks, "strategy_comparison_shape", "available" in strat)

        report = build_monthly_report(store, uid_a)
        record(checks, "monthly_report", "headline" in report and "disclaimer" in report)

        # user isolation
        create_or_update_account(uid_b, starting_bankroll=50.0)
        bets_b = list_bets(uid_b)["bets"]
        record(checks, "user_isolation", len(bets_b) == 0)

        settle = settle_pending_bets(store=store, user_id=uid_a)
        record(checks, "pending_settlement_runs", settle.get("status") == "ok")

        record(checks, "no_bookmaker_refs", "bookmaker" not in api.lower() or "no real" in (FRONTEND / "src/pages/PaperBettingPage.jsx").read_text(encoding="utf-8"))

        # cleanup test rows
        store._conn.execute("DELETE FROM paper_betting_bets WHERE user_id IN (?, ?)", (uid_a, uid_b))
        store._conn.execute("DELETE FROM paper_betting_accounts WHERE user_id IN (?, ?)", (uid_a, uid_b))
        store._conn.commit()

    except Exception as exc:
        record(checks, "runtime_checks", False, str(exc))

    try:
        env = os.environ.copy()
        env.setdefault("CI", "true")
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=str(FRONTEND),
            capture_output=True,
            text=True,
            timeout=300,
            shell=sys.platform == "win32",
            env=env,
        )
        record(checks, "frontend_build", proc.returncode == 0, (proc.stderr or proc.stdout)[-400:])
    except Exception as exc:
        record(checks, "frontend_build", False, str(exc))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A18 validation: {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        status = "PASS" if ok else "FAIL"
        line = f"  [{status}] {name}"
        if detail and not ok:
            line += f" — {detail[:200]}"
        print(line)

    out_path = ROOT / "data" / "validation" / "phase_a18_paper_betting_validation.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
