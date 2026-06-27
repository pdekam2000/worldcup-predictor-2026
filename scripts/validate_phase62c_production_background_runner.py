#!/usr/bin/env python3
"""Validate Phase 62C production background runner artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> int:
    checks: list[tuple[str, bool, str]] = []

    for name in (
        "scripts/phase62c_production_background_runner.sh",
        "scripts/phase62c_finalize_and_validate.sh",
        "worldcup_predictor/egie/world_cup/progress_checkpoint.py",
        "worldcup_predictor/egie/world_cup/progress_log.py",
    ):
        checks.append((name, (ROOT / name).is_file(), "present"))

    try:
        from worldcup_predictor.egie.world_cup.progress_checkpoint import load_checkpoint, save_checkpoint

        ck = load_checkpoint()
        save_checkpoint({**ck, "status": "test"})
        checks.append(("checkpoint:rw", True, "ok"))
    except Exception as exc:
        checks.append(("checkpoint:rw", False, str(exc)[:120]))

    phase62b = ROOT / "scripts" / "phase62b_sportmonks_wc_xg_lineups_completion.py"
    text = phase62b.read_text(encoding="utf-8") if phase62b.is_file() else ""
    checks.append(("phase62b:--no-resume", "--no-resume" in text, "flag"))
    checks.append(("phase62b:progress-every", "--progress-every" in text, "flag"))

    import re

    sm = (ROOT / "worldcup_predictor" / "egie" / "world_cup" / "sportmonks_wc_import.py").read_text(
        encoding="utf-8"
    )
    checks.append(("import:resume", "resume: bool" in sm, "param"))
    checks.append(("import:checkpoint", "save_checkpoint" in sm, "calls"))

    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    print(f"Phase 62C validation: {passed}/{total}")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} — {detail}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
