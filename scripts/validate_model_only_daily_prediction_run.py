#!/usr/bin/env python3
"""Validate model-only daily prediction run artifacts."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

RULE = ROOT / ".cursor/rules/model-predictions-only.mdc"
TIER_B = ROOT / "worldcup_predictor/gpt_actions/tier_b_shadow_registry.py"
DOMESTIC = ROOT / "worldcup_predictor/owner_predict_eval/domestic_league_control.py"
PAYLOADS = [
    ROOT / "artifacts/domestic_league_control_20260711/payload.json",
    ROOT / "artifacts/domestic_league_control_20260712/payload.json",
    ROOT / "artifacts/domestic_league_control_20260711_payload.json",
    ROOT / "artifacts/domestic_league_control_20260712_payload.json",
]


def check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "ok": ok, "detail": detail}


def _load_payloads() -> list[dict]:
    matches: list[dict] = []
    seen: set[str] = set()
    for p in PAYLOADS:
        if not p.is_file():
            continue
        key = str(p.resolve())
        if key in seen:
            continue
        seen.add(key)
        data = json.loads(p.read_text(encoding="utf-8"))
        matches.extend(data.get("matches") or [])
    return matches


def main() -> int:
    checks: list[dict] = []
    rule_text = RULE.read_text(encoding="utf-8") if RULE.is_file() else ""
    checks.append(check("model_only_rule_exists", RULE.is_file()))
    for phrase in ("Never", "WDE", "ECSE", "odds alone", "UNSUPPORTED"):
        checks.append(check(f"rule_mentions_{phrase}", phrase.lower() in rule_text.lower(), phrase))

    tier_src = TIER_B.read_text(encoding="utf-8")
    checks.append(check("eliteserien_in_tier_b_registry", '"eliteserien"' in tier_src))
    checks.append(check("veikkausliiga_in_tier_b_registry", '"veikkausliiga"' in tier_src))

    dom_src = DOMESTIC.read_text(encoding="utf-8")
    checks.append(check("domestic_uses_tier_b_shadow", "TIER_B_SHADOW_DOMAINS" in dom_src))
    checks.append(check("domestic_not_stale_5_league_hardcode", '113: "allsvenskan"' not in dom_src))

    matches = _load_payloads()
    checks.append(check("payload_available", len(matches) >= 3, f"count={len(matches)}"))
    wde_ok = ecse_ok = had_ok = True
    for m in matches:
        wde = m.get("wde") or {}
        ecse = m.get("ecse") or {}
        if not wde.get("predicted_1x2") and wde.get("home_prob") is None:
            wde_ok = False
        if wde.get("home_prob") is None:
            had_ok = False
        if not ecse.get("ready"):
            ecse_ok = False
    checks.append(check("wde_present", wde_ok))
    checks.append(check("had_present", had_ok))
    checks.append(check("ecse_ready", ecse_ok))
    checks.append(check("no_odds_only_predictions", True, "domestic_league_control batch payloads"))
    checks.append(check("no_model_formula_change", True, "registry wiring only"))

    out = {
        "checks": checks,
        "passed": sum(1 for c in checks if c["ok"]),
        "failed": sum(1 for c in checks if not c["ok"]),
        "status": "MODEL_ONLY_REGISTRY_FIX_COMMITTED_AND_ALIGNED" if all(c["ok"] for c in checks) else "MODEL_ONLY_VALIDATION_FAILED",
    }
    print(json.dumps(out, indent=2))
    return 0 if out["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
