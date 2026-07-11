#!/usr/bin/env python3
"""Validate best-3 ECSE Top5 extraction artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
JSON_PATH = ROOT / "artifacts" / "model_only_best3_exact_score_top5_20260712.json"
MD_PATH = ROOT / "BEST_3_EXACT_SCORE_TOP5_MODEL_OUTPUT_2026_07_12.md"
EXPECTED = (1494695, 1494204, 1494205)


def check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "ok": ok, "detail": detail}


def main() -> int:
    checks: list[dict] = []
    checks.append(check("json_exists", JSON_PATH.is_file()))
    checks.append(check("md_exists", MD_PATH.is_file()))
    if not JSON_PATH.is_file():
        print(json.dumps({"checks": checks, "status": "BEST3_EXACT_SCORE_TOP5_VALIDATION_FAILED"}))
        return 1

    data = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    picks = data.get("picks") or []
    checks.append(check("three_matches", len(picks) == 3, str(len(picks))))
    ids = [p.get("fixture_id") for p in picks]
    checks.append(check("fixture_ids", ids == list(EXPECTED), str(ids)))

    for i, p in enumerate(picks):
        prefix = f"pick{i+1}"
        checks.append(check(f"{prefix}_wde", bool(p.get("wde_end_result"))))
        tops = p.get("ecse_top1_top5") or {}
        for n in ("top1", "top2", "top3", "top4", "top5"):
            checks.append(check(f"{prefix}_{n}", n in tops and "scoreline" in tops[n]))
        checks.append(check(f"{prefix}_model_only_source", "model_only" in data.get("policy", "")))

    checks.append(check("no_friendlies", all(p.get("competition_key") != "international_friendlies" for p in picks)))
    failed = sum(1 for c in checks if not c["ok"])
    status = "BEST3_EXACT_SCORE_TOP5_EXTRACTED" if failed == 0 else "BEST3_EXACT_SCORE_TOP5_VALIDATION_FAILED"
    print(json.dumps({"checks": checks, "passed": sum(1 for c in checks if c["ok"]), "failed": failed, "status": status}, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
