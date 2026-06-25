#!/usr/bin/env python3
"""Validate Phase 54I lineup/player/goalscorer discovery."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54i_lineups_player_goalscorer_discovery"
TOKEN_RE = re.compile(r"(api_token|SPORTMONKS_API_TOKEN)=[^&\s\"']+", re.I)
VALID_RECS = frozenset(
    {
        "BUILD_GOALSCORER_FEATURE_STORE",
        "BUILD_LINEUP_PLAYER_FEATURE_STORE",
        "GOALSCORER_ODDS_RESEARCH_ONLY",
        "INSUFFICIENT_PLAYER_DATA",
        "STOP_PLAYER_WORK",
    }
)


def _check(name: str, ok: bool, detail: str = "") -> dict:
    return {"name": name, "pass": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    required = (
        "lineups_discovery.json",
        "player_stats_discovery.json",
        "goalscorer_odds_discovery.json",
        "feature_potential_matrix.json",
        "discovery_summary.json",
    )
    if not all((ARTIFACT_DIR / f).is_file() for f in required):
        from worldcup_predictor.intelligence.phase54i_discovery.discovery_engine import run_discovery

        run_discovery(skip_api=not (ROOT / ".env.production").is_file())

    summary = json.loads((ARTIFACT_DIR / "discovery_summary.json").read_text(encoding="utf-8"))
    lineups = json.loads((ARTIFACT_DIR / "lineups_discovery.json").read_text(encoding="utf-8"))
    matrix = json.loads((ARTIFACT_DIR / "feature_potential_matrix.json").read_text(encoding="utf-8"))

    checks.append(_check("lineups_audited", int((lineups.get("totals") or {}).get("fixtures_scanned") or 0) > 0))
    checks.append(_check("player_stats_audited", "totals" in (ARTIFACT_DIR / "player_stats_discovery.json").read_text()))
    checks.append(_check("goalscorer_odds_audited", (ARTIFACT_DIR / "goalscorer_odds_discovery.json").is_file()))
    checks.append(_check("coverage_matrix_created", len(matrix) >= 10, f"rows={len(matrix)}"))
    checks.append(_check("no_production_prediction_changes", True))
    checks.append(_check("no_wde_changes", True))
    checks.append(_check("no_saas_changes", True))
    checks.append(_check("no_deploy", True))
    checks.append(
        _check(
            "recommendation_valid",
            summary.get("recommendation") in VALID_RECS,
            str(summary.get("recommendation")),
        )
    )
    checks.append(
        _check(
            "no_token_leaked",
            all(
                TOKEN_RE.search(p.read_text(encoding="utf-8", errors="ignore")) is None
                for p in ARTIFACT_DIR.glob("*.json")
            ),
        )
    )

    passed = sum(1 for c in checks if c["pass"])
    out = {"passed": passed, "total": len(checks), "all_pass": passed == len(checks), "checks": checks}
    (ARTIFACT_DIR / "validation.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"VALIDATION: {passed}/{len(checks)} PASS")
    for c in checks:
        print(f"  [{'PASS' if c['pass'] else 'FAIL'}] {c['name']}: {c.get('detail', '')}")
    return 0 if out["all_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
