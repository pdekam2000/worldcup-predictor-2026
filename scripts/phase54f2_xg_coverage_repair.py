#!/usr/bin/env python3
"""Phase 54F-2 orchestrator — metric repair, re-import, audit, optional 54F rerun."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f2_xg_coverage_repair"
PY = sys.executable


def _run(cmd: list[str], label: str) -> dict:
    print(f"\n=== {label} ===")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)
    return {"label": label, "returncode": proc.returncode, "stdout_tail": proc.stdout[-2000:]}


def main() -> int:
    steps: list[dict] = []

    # UEFA cache re-import (leagues 2, 5, 2286) — cache-only, force reimport
    for league_id in (2, 5, 2286):
        steps.append(
            _run(
                [
                    PY,
                    str(ROOT / "scripts" / "phase54e_sportmonks_xg_backfill.py"),
                    "--cache-only",
                    "--league-id",
                    str(league_id),
                    "--force-reimport",
                    "--metric-key",
                    "xg",
                    "--job-key",
                    f"phase54f2_uefa_l{league_id}",
                ],
                f"UEFA cache re-import league {league_id}",
            )
        )

    # WC 732 — live backfill if token configured, else note cache-only skip
    from worldcup_predictor.config.settings import get_settings
    from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

    provider = SportmonksProvider(get_settings())
    if provider.is_configured:
        steps.append(
            _run(
                [
                    PY,
                    str(ROOT / "scripts" / "phase54e_sportmonks_xg_backfill.py"),
                    "--league-id",
                    "732",
                    "--max-calls",
                    "80",
                    "--metric-key",
                    "xg",
                    "--force-reimport",
                    "--job-key",
                    "phase54f2_wc732",
                ],
                "WC 732 live backfill",
            )
        )
    else:
        steps.append({"label": "WC 732 live backfill", "returncode": 0, "stdout_tail": "skipped:no_token_locally"})

    # Coverage audit
    steps.append(_run([PY, str(ROOT / "scripts" / "audit_phase54f2_xg_coverage_repair.py")], "Coverage audit"))

    audit_path = ARTIFACT_DIR / "coverage_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.is_file() else {}
    threshold_met = bool(audit.get("threshold_met"))

    if threshold_met:
        steps.append(_run([PY, str(ROOT / "scripts" / "phase54f_egie_xg_backtest.py")], "54F A/B backtest rerun"))
    else:
        steps.append({"label": "54F A/B backtest rerun", "returncode": 0, "stdout_tail": "skipped:coverage_below_30pct"})

    steps.append(_run([PY, str(ROOT / "scripts" / "validate_phase54f2_xg_coverage_repair.py")], "Validation"))

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "orchestrator.json").write_text(json.dumps({"steps": steps, "threshold_met": threshold_met}, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
