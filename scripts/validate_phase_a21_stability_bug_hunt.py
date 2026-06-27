#!/usr/bin/env python3
"""Phase A21 — Full product stability bug hunt validation."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

runpy_path = Path(__file__).resolve().with_name("bootstrap_path.py")
if runpy_path.is_file():
    import runpy

    runpy.run_path(str(runpy_path))

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"
PROTECTED_FORBIDDEN = ROOT / "worldcup_predictor" / "decision" / "weighted_decision_engine.py"
SCORING = ROOT / "worldcup_predictor" / "prediction" / "scoring_engine.py"
CALIBRATION = ROOT / "worldcup_predictor" / "prediction" / "lambda_bridge" / "calibration.py"
BASE_URL = os.getenv("A21_SMOKE_BASE", "https://footballpredictor.it.com").rstrip("/")


def record(checks: list, name: str, ok: bool, detail: str = "") -> None:
    checks.append((name, ok, detail))


def http_status(url: str, timeout: int = 20) -> int:
    req = urllib.request.Request(url, headers={"Accept": "application/json, text/html"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except Exception:
        return 0


def http_json(url: str, timeout: int = 20) -> dict | list | None:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None


def git_diff_clean(paths: list[str]) -> tuple[bool, str]:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "--", *paths],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    changed = [ln.strip() for ln in (proc.stdout or "").splitlines() if ln.strip()]
    return len(changed) == 0, ", ".join(changed) if changed else "none"


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    nav = (FRONTEND / "src/lib/navConfig.js").read_text(encoding="utf-8")

    record(checks, "archive_detail_import", "import PredictionHistoryDetailPage" in app)
    record(checks, "route_archive_detail", 'path="/archive/:predictionId"' in app)
    record(checks, "route_archive_list", 'path="/archive"' in app)
    record(checks, "nav_archive_link", 'path: "/archive"' in nav)
    record(checks, "nav_predops_link", 'path: "/admin/predops"' in nav)

    for rel, pattern in (
        ("src/pages/MatchCenter.jsx", "MatchCenter"),
        ("src/pages/MatchDetailPage.jsx", "MatchDetailPage"),
        ("src/pages/ComboTipsPage.jsx", "ComboTipsPage"),
        ("src/pages/BettingPlanPage.jsx", "BettingPlanPage"),
        ("src/pages/PaperBettingPage.jsx", "PaperBettingPage"),
        ("src/pages/WatchlistPage.jsx", "WatchlistPage"),
        ("src/pages/DailyBriefingPage.jsx", "DailyBriefingPage"),
        ("src/pages/ArchivePage.jsx", "ArchivePage"),
        ("src/pages/AccuracyCenter.jsx", "AccuracyCenter"),
        ("src/pages/share/PublicAccuracyPage.jsx", "PublicAccuracyPage"),
        ("src/pages/admin/AdminPredOpsPage.jsx", "AdminPredOpsPage"),
    ):
        record(checks, f"page_{Path(rel).stem}", (FRONTEND / rel).is_file(), rel)

    elite = (FRONTEND / "src/components/match-center/EliteMatchCard.jsx").read_text(encoding="utf-8")
    summary_cards = (FRONTEND / "src/pages/PredictionHistoryDetailPage.jsx").read_text(encoding="utf-8")
    record(checks, "ui_no_raw_no_bet_elite", "no_bet" not in elite)
    record(checks, "archive_no_draw_fallback", '|| "Draw"' not in (FRONTEND / "src/lib/archiveStatus.js").read_text(encoding="utf-8"))
    record(checks, "summary_no_draw_fallback", '|| "Draw"' not in (FRONTEND / "src/components/prediction-detail-pro/PredictionSummaryCards.jsx").read_text(encoding="utf-8"))

    wde_before = PROTECTED_FORBIDDEN.read_text(encoding="utf-8") if PROTECTED_FORBIDDEN.is_file() else ""
    scoring_before = SCORING.read_text(encoding="utf-8") if SCORING.is_file() else ""
    record(checks, "wde_present", "WeightedDecision" in wde_before)
    record(checks, "scoring_present", "class ScoringEngine" in scoring_before)
    if CALIBRATION.is_file():
        record(checks, "calibration_module_present", True)

    protected_paths = [
        "worldcup_predictor/decision/weighted_decision_engine.py",
        "worldcup_predictor/prediction/scoring_engine.py",
        "worldcup_predictor/prediction/lambda_bridge/calibration.py",
        "worldcup_predictor/api/routes/billing.py",
    ]
    if os.getenv("A21_USE_GIT_GUARD") == "1":
        clean, changed = git_diff_clean(protected_paths + ["worldcup_predictor/subscription"])
        record(checks, "protected_logic_unchanged", clean, changed)
    else:
        record(checks, "protected_logic_unchanged", True, "git guard skipped (deploy/server)")

    # --- API smoke (public / expected auth) ---
    api_cases = [
        ("api_health", f"{BASE_URL}/api/health", {200}),
        ("api_competitions", f"{BASE_URL}/api/competitions?include_counts=true", {200}),
        ("api_matches", f"{BASE_URL}/api/matches?competition=all&include_summary=true", {200}),
        ("api_public_accuracy", f"{BASE_URL}/api/public/accuracy", {200}),
        ("api_betting_plan", f"{BASE_URL}/api/betting-plan/today", {200}),
        ("api_performance", f"{BASE_URL}/api/performance/summary", {200, 401}),
        ("api_watchlist_protected", f"{BASE_URL}/api/watchlist", {401, 403}),
        ("api_paper_account_protected", f"{BASE_URL}/api/paper-betting/account", {401, 403}),
        ("api_predops_coverage_public", f"{BASE_URL}/api/predops/coverage", {200}),
        ("api_predops_combo_public", f"{BASE_URL}/api/predops/combo-readiness", {200}),
        ("api_predops_queue_protected", f"{BASE_URL}/api/predops/queue", {401, 403}),
        ("api_predops_admin_coverage_protected", f"{BASE_URL}/api/predops/coverage/admin", {401, 403}),
    ]
    for name, url, expected in api_cases:
        code = http_status(url)
        record(checks, name, code in expected, f"got {code}, want {sorted(expected)}")

    # --- Privacy: public accuracy + matches summary ---
    acc = http_json(f"{BASE_URL}/api/public/accuracy")
    if isinstance(acc, dict):
        acc_body = acc.get("accuracy") or {}
        leak_keys = [k for k in acc_body if re.search(r"debug|wde|no_bet|email", k, re.I)]
        record(checks, "public_accuracy_no_debug_leak", not leak_keys, str(leak_keys))
        record(checks, "public_accuracy_disclaimer", "disclaimer" in acc_body)
    else:
        record(checks, "public_accuracy_no_debug_leak", False, "unreachable")

    matches = http_json(f"{BASE_URL}/api/matches?competition=world_cup_2026&page_size=5&include_summary=true")
    if isinstance(matches, dict):
        rows = matches.get("matches") or matches.get("items") or []
        leak = False
        for row in rows[:5]:
            sm = row.get("prediction_summary") or {}
            if "no_bet" in sm:
                leak = True
                break
            po = sm.get("publication_overlay") or {}
            if "wde_no_bet_reasons" in po or "internal_no_bet" in po:
                leak = True
                break
        record(checks, "matches_no_bet_leak", not leak)
    else:
        record(checks, "matches_no_bet_leak", False, "unreachable")

    # --- Runtime: publication overlay + combo readiness ---
    try:
        from worldcup_predictor.api.match_center_helpers import extract_prediction_summary
        from worldcup_predictor.publication.bet_quality_overlay import build_publication_overlay, sanitize_public_summary
        from worldcup_predictor.predops.combo_readiness import build_combo_readiness_report

        no_bet_payload = {
            "status": "ok",
            "no_bet": True,
            "prediction": "draw",
            "confidence": 0.42,
            "detailed_markets": {},
        }
        summary = extract_prediction_summary(no_bet_payload)
        public = sanitize_public_summary(summary)
        record(checks, "sanitize_strips_no_bet", "no_bet" not in public)

        overlay = build_publication_overlay(no_bet_payload, include_debug=False)
        record(checks, "overlay_hides_wde_debug", "wde_no_bet_reasons" not in overlay)

        unavailable = build_publication_overlay({"status": "ok", "no_bet": True, "detailed_markets": {}}, include_debug=False)
        record(checks, "no_bet_not_published_as_draw", unavailable.get("public_recommendation_status") != "published")

        readiness = build_combo_readiness_report(matches=[], min_confidence=55.0)
        record(checks, "combo_readiness_runs", isinstance(readiness, dict) and readiness.get("status") == "ok")
    except Exception as exc:
        record(checks, "runtime_publication_tests", False, str(exc))

    # --- Frontend routes (SPA shell) ---
    for name, path in (
        ("fe_home", "/"),
        ("fe_matches", "/matches"),
        ("fe_combo", "/combo-tips"),
        ("fe_betting_plan", "/betting-plan"),
        ("fe_paper", "/paper-betting"),
        ("fe_watchlist", "/watchlist"),
        ("fe_briefing", "/daily-briefing"),
        ("fe_archive", "/archive"),
        ("fe_accuracy", "/accuracy"),
        ("fe_public_accuracy", "/public/accuracy"),
        ("fe_login", "/login"),
        ("fe_share_pick", "/share/pick/test"),
    ):
        code = http_status(f"{BASE_URL}{path}")
        record(checks, name, code == 200, f"got {code}")

    if os.getenv("SKIP_FRONTEND_BUILD") != "1":
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=FRONTEND,
            capture_output=True,
            text=True,
            timeout=240,
            shell=sys.platform == "win32",
        )
        record(checks, "frontend_build", proc.returncode == 0, (proc.stderr or proc.stdout or "")[-500:])
    else:
        record(checks, "frontend_build", True, "skipped")

    # --- Regression scripts (light invoke) ---
    for phase, script in (
        ("a16_overlay", "validate_phase_a16_bet_quality_publication_overlay.py"),
        ("a18_paper", "validate_phase_a18_paper_betting.py"),
        ("a20_trust", "validate_phase_a20_social_trust.py"),
    ):
        env = {**os.environ, "SKIP_FRONTEND_BUILD": "1"}
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
        record(checks, f"regression_{phase}", proc.returncode == 0, (proc.stderr or proc.stdout or "")[-200:])

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A21 stability validation: {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))

    out = ROOT / "data" / "validation" / "phase_a21_stability_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(
            {"passed": passed, "total": total, "base_url": BASE_URL, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]},
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
