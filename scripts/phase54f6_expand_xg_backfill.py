#!/usr/bin/env python3
"""Phase 54F-6 — expanded xG backfill orchestrator (cache-first, high page limits)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54f6_expanded_dataset"
PY = sys.executable

# (league_id, season_label, season_id, max_calls, max_pages)
EXPANSION_TARGETS: list[tuple[int, str, int, int, int]] = [
    (732, "2026", 26618, 350, 25),
    (2, "2024/2025", 23619, 350, 25),
    (2, "2025/2026", 25580, 350, 25),
    (5, "2024/2025", 23620, 350, 25),
    (5, "2025/2026", 25582, 350, 25),
    (2286, "2025/2026", 25581, 350, 25),
]


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    steps: list[dict] = []

    for league_id, season_label, season_id, max_calls, max_pages in EXPANSION_TARGETS:
        cmd = [
            PY,
            str(ROOT / "scripts" / "phase54e_sportmonks_xg_backfill.py"),
            "--league-id",
            str(league_id),
            "--season-id",
            str(season_id),
            "--metric-key",
            "xg",
            "--max-calls",
            str(max_calls),
            "--max-pages",
            str(max_pages),
            "--force-reimport",
            "--cache-first",
            "--job-key",
            f"phase54f6_l{league_id}_s{season_id}",
        ]
        label = f"L{league_id} {season_label}"
        print(f"\n=== Backfill {label} ===")
        proc = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
        tail = proc.stdout[-2000:] if proc.stdout else ""
        if proc.stderr:
            print(proc.stderr[-500:], file=sys.stderr)
        step: dict = {"label": label, "returncode": proc.returncode, "stdout_tail": tail}
        try:
            if proc.stdout and "{" in proc.stdout:
                step["result"] = json.loads(proc.stdout[proc.stdout.index("{") :])
        except json.JSONDecodeError:
            pass
        steps.append(step)

    print("\n=== Cache re-import ===")
    proc = subprocess.run(
        [PY, str(ROOT / "scripts" / "phase54f4_import_server_xg_cache.py"), "--force-reimport"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    steps.append({"label": "cache_reimport", "returncode": proc.returncode, "stdout_tail": proc.stdout[-1500:]})

    (ARTIFACT_DIR / "backfill_orchestrator.json").write_text(json.dumps(steps, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
