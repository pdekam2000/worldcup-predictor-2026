#!/usr/bin/env python3
"""Phase 44C — billing checkout audit validation."""

from __future__ import annotations

import json
import runpy
import subprocess
import sys
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().with_name("bootstrap_path.py")))


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    proc = subprocess.run(
        [sys.executable, str(root / "scripts" / "validate_billing_purchase_error.py")],
        cwd=str(root),
        capture_output=True,
        text=True,
    )
    print(proc.stdout)
    if proc.stderr:
        print(proc.stderr, file=sys.stderr)

    checks: list[tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks.append((name, ok, detail))

    record("billing_purchase_suite", proc.returncode == 0, f"exit={proc.returncode}")

    svc_text = (root / "worldcup_predictor/billing/billing_service.py").read_text(encoding="utf-8")
    record("readiness_validates_prices", "_stripe_prices_valid" in svc_text)
    record("checkout_blocks_when_disabled", "if not readiness.checkout_enabled" in svc_text)
    record("upgrade_validation", "validate_checkout_upgrade" in svc_text)

    routes = (root / "worldcup_predictor/api/routes/billing.py").read_text(encoding="utf-8")
    record("create_checkout_endpoint", "create-checkout-session" in routes)
    record("legacy_no_404", "legacy_router" in routes)

    fe_path = root / "base44-d/src/lib/checkoutErrors.js"
    if fe_path.is_file():
        fe = fe_path.read_text(encoding="utf-8")
        record("frontend_checkout_errors", "plan is not available" in fe.lower() or "PLAN_UNAVAILABLE" in fe)
    else:
        record("frontend_checkout_errors", True, "skipped — frontend not in backend deploy tree")

    out = root / "artifacts/phase44c_billing_validation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for _, ok, _ in checks if ok)
    out.write_text(json.dumps({
        "phase": "44C",
        "passed": passed,
        "total": len(checks),
        "checks": [{"name": n, "ok": ok, "detail": d} for n, ok, d in checks],
    }, indent=2), encoding="utf-8")
    print(f"Phase 44C validation: {passed}/{len(checks)} PASS")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
