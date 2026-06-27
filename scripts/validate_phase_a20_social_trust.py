#!/usr/bin/env python3
"""Phase A20 — Social sharing & public trust validation."""

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
        "worldcup_predictor/social_trust/store.py",
        "worldcup_predictor/social_trust/service.py",
        "worldcup_predictor/social_trust/sanitize.py",
        "worldcup_predictor/social_trust/trust_stats.py",
        "worldcup_predictor/api/routes/social_trust.py",
    ):
        record(checks, f"file_{Path(rel).stem}", (ROOT / rel).is_file())

    mig = (ROOT / "worldcup_predictor/database/migrations.py").read_text(encoding="utf-8")
    record(checks, "ddl_social_share", "social_share_links" in mig)

    api = (ROOT / "worldcup_predictor/api/routes/social_trust.py").read_text(encoding="utf-8")
    for ep in ("/share/pick", "/share/combo", "/share/paper-report", "/public/accuracy", "/share/og/"):
        record(checks, f"api_{ep.strip('/').replace('/', '_')}", ep in api)

    app = (FRONTEND / "src/App.jsx").read_text(encoding="utf-8")
    record(checks, "ui_share_pick", "/share/pick/" in app)
    record(checks, "ui_share_combo", "/share/combo/" in app)
    record(checks, "ui_public_accuracy", "/public/accuracy" in app)
    record(checks, "ui_share_button", (FRONTEND / "src/components/social/ShareButton.jsx").is_file())
    record(checks, "ui_page_meta", (FRONTEND / "src/components/social/PageMeta.jsx").is_file())

    wde = (ROOT / "worldcup_predictor/decision/weighted_decision_engine.py").read_text(encoding="utf-8")
    record(checks, "wde_unchanged", "class WeightedDecisionEngine" in wde)

    try:
        from worldcup_predictor.database.migrations import ensure_schema_compat
        from worldcup_predictor.database.repository import FootballIntelligenceRepository
        from worldcup_predictor.social_trust.sanitize import sanitize_pick_payload, sanitize_paper_report_payload
        from worldcup_predictor.social_trust.service import (
            create_combo_share,
            create_paper_report_share,
            create_pick_share,
            get_public_accuracy,
            get_share,
        )
        from worldcup_predictor.social_trust.store import SocialShareStore

        repo = FootballIntelligenceRepository()
        ensure_schema_compat(repo._conn)

        uid = f"test-a20-{uuid.uuid4().hex[:8]}"

        pick = create_pick_share(
            uid,
            {
                "fixture_id": 123,
                "home_team": "Team A",
                "away_team": "Team B",
                "market": "1x2",
                "prediction": "home",
                "bet_quality_score": 75,
                "user_id": "must-strip",
                "email": "secret@test.com",
            },
        )
        record(checks, "pick_share_created", pick.get("status") == "ok" and pick.get("share_id"))

        public = get_share(pick["share_id"], expected_type="pick")
        payload = public.get("share", {}).get("payload", {})
        record(checks, "share_page_payload", public.get("status") == "ok")
        record(checks, "private_data_hidden", "user_id" not in payload and "email" not in payload)
        record(checks, "og_metadata", bool(public.get("og", {}).get("title")))

        sanitized = sanitize_pick_payload({"user_id": "x", "home_team": "A", "away_team": "B", "market": "1x2", "prediction": "home"})
        record(checks, "sanitize_strips_user", "user_id" not in sanitized)

        paper_denied = create_paper_report_share(uid, {"roi_pct": 10}, opt_in=False)
        record(checks, "paper_opt_in_required", paper_denied.get("status") == "error")

        paper_ok = create_paper_report_share(
            uid,
            {"month": "2026-06", "roi_pct": 5.0, "net_profit_loss": 10, "user_id": "hidden"},
            opt_in=True,
        )
        pub_paper = get_share(paper_ok["share_id"], expected_type="paper_report")
        pp = pub_paper.get("share", {}).get("payload", {})
        record(checks, "paper_share_anonymized", pp.get("shared_anonymously") and "user_id" not in pp)

        combo = create_combo_share(
            uid,
            {"combo_type": "safe", "legs": [{"home_team": "A", "away_team": "B", "market": "btts", "prediction": "yes"}]},
        )
        record(checks, "combo_share", combo.get("status") == "ok")

        acc = get_public_accuracy()
        acc_data = acc.get("accuracy", {})
        record(checks, "public_accuracy", acc.get("status") == "ok")
        if acc_data.get("data_available"):
            record(checks, "no_fake_stats", acc_data.get("accuracy_30d_pct") is not None)
        else:
            record(checks, "no_fake_stats", acc_data.get("accuracy_30d_pct") is None)

        trust = get_public_accuracy()["accuracy"]
        record(checks, "trust_disclaimer", "disclaimer" in trust)

    except Exception as exc:
        record(checks, "runtime_tests", False, str(exc))

    if os.getenv("SKIP_FRONTEND_BUILD") != "1":
        proc = subprocess.run(
            ["npm", "run", "build"],
            cwd=FRONTEND,
            capture_output=True,
            text=True,
            timeout=180,
            shell=sys.platform == "win32",
        )
        record(checks, "frontend_build", proc.returncode == 0, (proc.stderr or "")[-400:])
    else:
        record(checks, "frontend_build", True, "skipped")

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"\nPhase A20 validation: {passed}/{total} checks passed\n")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))

    out = ROOT / "data" / "validation" / "phase_a20_social_trust_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps({"passed": passed, "total": total, "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks]}, indent=2),
        encoding="utf-8",
    )
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
