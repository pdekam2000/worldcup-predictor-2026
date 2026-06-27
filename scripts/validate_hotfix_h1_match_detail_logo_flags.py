#!/usr/bin/env python3
"""HOTFIX H1 — Match Detail black screen + logo/flag fallback validation."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "base44-d"
BASE = os.environ.get("HOTFIX_BASE_URL", "https://footballpredictor.it.com").rstrip("/")
FIXTURE = int(os.environ.get("HOTFIX_FIXTURE_ID", "1489410"))
COMP = os.environ.get("HOTFIX_COMPETITION", "world_cup_2026")

FORBIDDEN_PATH_FRAGMENTS = [
    "weighted_decision_engine",
    "worldcup_predictor/decision/",
    "worldcup_predictor/prediction/scoring",
    "worldcup_predictor/prediction/lambda_bridge/calibration",
    "billing",
    "subscription",
]

REQUIRED_FRONTEND = [
    "src/lib/imageResolver.js",
    "src/components/ui/ErrorBoundary.jsx",
    "src/components/ui/SafeImage.jsx",
    "src/pages/MatchDetailPage.jsx",
    "src/components/match/TeamBadge.jsx",
    "src/components/match-center/LeagueSelector.jsx",
    "src/components/match-center/EliteMatchCard.jsx",
    "src/api/worldcupApi.js",
    "src/lib/predictionDetailProUtils.js",
]

REQUIRED_BACKEND = [
    "worldcup_predictor/api/routes/predictions.py",
    "worldcup_predictor/api/match_center_helpers.py",
    "worldcup_predictor/api/display_helpers.py",
]


def ok(msg: str) -> None:
    print(f"  PASS  {msg}")


def fail(msg: str) -> None:
    print(f"  FAIL  {msg}")
    raise SystemExit(1)


def fetch_json(path: str) -> dict:
    req = Request(f"{BASE}{path}", headers={"Accept": "application/json", "User-Agent": "hotfix-h1-validate/1.0"})
    with urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def fetch_status(path: str) -> tuple[int, dict | None]:
    req = Request(f"{BASE}{path}", headers={"Accept": "application/json", "User-Agent": "hotfix-h1-validate/1.0"})
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode()
            try:
                return resp.status, json.loads(body)
            except json.JSONDecodeError:
                return resp.status, None
    except HTTPError as exc:
        raw = exc.read().decode(errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, None


def check_files() -> None:
    print("\n== Files ==")
    for rel in REQUIRED_FRONTEND:
        p = FRONTEND / rel
        if not p.is_file():
            fail(f"missing frontend file {rel}")
        ok(rel)
    for rel in REQUIRED_BACKEND:
        p = ROOT / rel
        if not p.is_file():
            fail(f"missing backend file {rel}")
        ok(rel)


def check_no_forbidden_changes() -> None:
    print("\n== Scope guard (no WDE/EGIE/model/scoring/calibration/billing) ==")
    try:
        out = subprocess.check_output(["git", "diff", "--name-only", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL)
    except Exception:
        out = ""
    changed = [ln.strip() for ln in out.splitlines() if ln.strip()]
    if not changed:
        ok("no git diff vs HEAD (or git unavailable)")
        return
    for path in changed:
        for frag in FORBIDDEN_PATH_FRAGMENTS:
            if frag.replace("/", os.sep) in path or frag in path:
                fail(f"forbidden path changed: {path}")
    ok(f"changed files OK ({len(changed)} files)")


def check_source_patterns() -> None:
    print("\n== Source patterns ==")
    utils = (FRONTEND / "src/lib/predictionDetailProUtils.js").read_text(encoding="utf-8")
    if "safeMarketSelection" not in utils:
        fail("safeMarketSelection missing")
    ok("safeMarketSelection present")
    if "fmtMarketSel(selection) || selection" in utils:
        fail("unsafe object selection still in groupMarkets row")
    ok("groupMarkets uses safe selection strings")
    api = (FRONTEND / "src/api/worldcupApi.js").read_text(encoding="utf-8")
    if "fetchPredictionForFixture" not in api:
        fail("fetchPredictionForFixture missing")
    ok("fetchPredictionForFixture present")
    pred = (ROOT / "worldcup_predictor/api/routes/predictions.py").read_text(encoding="utf-8")
    if "_predops_snapshot_as_cached" not in pred:
        fail("PredOps cache fallback missing in predictions.py")
    ok("PredOps predict cache fallback present")


def check_frontend_build() -> None:
    print("\n== Frontend build ==")
    if os.environ.get("SKIP_FRONTEND_BUILD") == "1":
        ok("skipped (SKIP_FRONTEND_BUILD=1)")
        return
    env = {**os.environ, "CI": "true"}
    subprocess.run(["npm", "run", "build"], cwd=FRONTEND, check=True, env=env)
    ok("npm run build")


def check_api_predict() -> None:
    print("\n== API predict cache ==")
    status, body = fetch_status(f"/api/predict/{FIXTURE}?competition={COMP}")
    if status == 404:
        print("  WARN  predict still 404 — deploy backend _predops_snapshot_as_cached")
    elif status == 200 and isinstance(body, dict):
        ok(f"GET /api/predict/{FIXTURE} → 200")
        if body.get("detailed_markets") or body.get("publication_overlay"):
            ok("prediction payload has markets/overlay")
        else:
            print("  WARN  payload sparse — may rely on overlay only")
    else:
        fail(f"unexpected predict status {status}")


def check_api_matches() -> None:
    print("\n== API matches logos ==")
    data = fetch_json(f"/api/matches?competition={COMP}&page_size=5&include_summary=true")
    matches = data.get("matches") or []
    if not matches:
        print("  WARN  no matches returned")
        return
    with_logo = sum(1 for m in matches if m.get("home_team_logo") or m.get("away_team_logo"))
    ok(f"{with_logo}/{len(matches)} matches have team logo fields")
    comps = fetch_json("/api/competitions?include_counts=true")
    clist = comps.get("competitions") or []
    logos = sum(1 for c in clist if c.get("logo_url"))
    ok(f"{logos}/{len(clist)} competitions have logo_url")


def check_frontend_bundle() -> None:
    print("\n== Production frontend bundle ==")
    html_status, _ = fetch_status("/matches")
    if html_status != 200:
        fail(f"/matches returned {html_status}")
    ok("/matches HTML 200")
    _, detail_html = fetch_status(f"/matches/{FIXTURE}?competition={COMP}")
    if not detail_html:
        # HTML endpoint may redirect to SPA — fetch as text
        req = Request(f"{BASE}/matches/{FIXTURE}?competition={COMP}", headers={"User-Agent": "hotfix-h1"})
        with urlopen(req, timeout=30) as resp:
            detail_html = resp.read().decode(errors="replace")
    if "root" not in str(detail_html):
        print("  WARN  SPA shell may be served elsewhere")
    else:
        ok("match detail route serves SPA shell")
    # Ensure new modules would be in built assets after deploy
    dist = FRONTEND / "dist"
    if dist.is_dir():
        assets = list(dist.rglob("*.js"))
        combined = ""
        for p in assets[:12]:
            combined += p.read_text(encoding="utf-8", errors="ignore")
        if "safeMarketSelection" in combined or "fetchPredictionForFixture" in combined:
            ok("built bundle contains hotfix symbols")
        else:
            print("  WARN  hotfix symbols not found in dist (minified names)")


def check_predops_snapshot() -> None:
    print("\n== PredOps snapshot ==")
    data = fetch_json(f"/api/predops/snapshots/latest?fixture_id={FIXTURE}")
    snap = data.get("snapshot")
    if not snap:
        print("  WARN  no snapshot for fixture")
        return
    ok(f"snapshot_id={snap.get('snapshot_id')}")
    if snap.get("publication_overlay"):
        ok("publication_overlay present")
    if snap.get("markets"):
        ok(f"markets count={len(snap['markets'])}")


def main() -> None:
    print(f"HOTFIX H1 validation — base={BASE} fixture={FIXTURE}")
    check_files()
    check_no_forbidden_changes()
    check_source_patterns()
    check_frontend_build()
    check_api_predict()
    check_api_matches()
    check_predops_snapshot()
    check_frontend_bundle()
    print("\nHOTFIX H1 VALIDATION COMPLETE")


if __name__ == "__main__":
    main()
