#!/usr/bin/env python3
"""Phase 54F-4 — targeted recent-season xG backfill orchestrator."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f4_xg_parser_and_backfill"
PY = sys.executable

# Leagues/seasons with proven xG coverage (Phase 54F-3)
TARGETS: list[tuple[int, str, int]] = [
    (732, "2026", 100),
    (2, "2024/2025", 100),
    (2, "2025/2026", 100),
    (5, "2024/2025", 100),
    (5, "2025/2026", 100),
    (2286, "2025/2026", 100),
]


def _run(cmd: list[str], label: str) -> dict:
    print(f"\n=== {label} ===")
    proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout[-3000:])
    if proc.stderr:
        print(proc.stderr[-1000:], file=sys.stderr)
    return {"label": label, "returncode": proc.returncode, "stdout_tail": proc.stdout[-1500:]}


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []

    # Parser proof on cached 54F-3 fixture
    proof_path = ROOT / "artifacts" / "phase54f3_xg_discovery" / "raw"
    if proof_path.is_dir():
        from worldcup_predictor.feature_store.xg_discovery.xg_fixture_parser import parse_proof_fixture

        for raw_file in proof_path.glob("fixtures_19609127_*.json"):
            blob = json.loads(raw_file.read_text(encoding="utf-8"))
            data = (blob.get("payload") or {}).get("data")
            if isinstance(data, dict):
                proof = parse_proof_fixture(data)
                (ARTIFACT_DIR / "parser_proof.json").write_text(json.dumps(proof, indent=2))
                steps.append({"label": "parser_proof", "proof": proof})
                break

    for league_id, season_label, max_calls in TARGETS:
        steps.append(
            _run(
                [
                    PY,
                    str(ROOT / "scripts" / "phase54e_sportmonks_xg_backfill.py"),
                    "--league-id",
                    str(league_id),
                    "--season-label",
                    season_label,
                    "--metric-key",
                    "xg",
                    "--max-calls",
                    str(max_calls),
                    "--force-reimport",
                    "--cache-first",
                ],
                f"Backfill L{league_id} {season_label}",
            )
        )

    steps.append(_run([PY, str(ROOT / "scripts" / "audit_phase54f4_targeted_xg_backfill.py")], "Coverage audit"))

    audit_path = ARTIFACT_DIR / "coverage_audit.json"
    audit = json.loads(audit_path.read_text(encoding="utf-8")) if audit_path.is_file() else {}
    threshold_met = bool(audit.get("threshold_met"))

    if threshold_met:
        steps.append(_run([PY, str(ROOT / "scripts" / "phase54f_egie_xg_backtest.py")], "Phase 54F A/B rerun"))
    else:
        steps.append({"label": "Phase 54F A/B rerun", "returncode": 0, "stdout_tail": "skipped:coverage_below_30pct"})

    steps.append(_run([PY, str(ROOT / "scripts" / "validate_phase54f4_xg_parser_and_backfill.py")], "Validation"))

    (ARTIFACT_DIR / "orchestrator.json").write_text(
        json.dumps({"steps": steps, "threshold_met": threshold_met, "audit": audit.get("summary")}, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
