#!/usr/bin/env python3
"""Phase 54H-3 live pressure backfill plan + safe access test (max 5 API calls)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ARTIFACT_DIR = ROOT / "artifacts" / "phase54h3_live_pressure_backfill_plan"


def _parse_server_probe(stdout: str) -> dict:
    out: dict = {"raw_lines": stdout.strip().splitlines()}
    for line in out["raw_lines"]:
        if "=" in line and line.startswith("SERVER_"):
            k, v = line.split("=", 1)
            out[k.lower()] = v
        elif line.startswith("SERVER_"):
            parts = line.split()
            if len(parts) >= 2:
                out[parts[0].lower()] = parts[1]
    out["token_present"] = out.get("server_token_present") == "1"
    rows_raw = out.get("server_pressure_rows") or "0"
    try:
        rows = int(str(rows_raw).strip())
    except ValueError:
        rows = 0
    out["pressure_rows"] = rows
    out["pressure_probe_ok"] = out.get("server_http_status") == "200" and rows > 0
    return out


def _run_server_probe(server_host: str) -> dict:
    script_path = ROOT / "scripts" / "_phase54h3_server_probe_run.sh"
    remote = "/tmp/phase54h3_probe.sh"
    subprocess.run(
        ["scp", str(script_path), f"{server_host}:{remote}"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    proc = subprocess.run(
        [
            "ssh",
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=15",
            server_host,
            f"sed -i 's/\\r$//' {remote} && bash {remote} && rm -f {remote}",
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    info = _parse_server_probe(proc.stdout)
    info["checked"] = True
    info["exit_code"] = proc.returncode
    if proc.stderr.strip():
        info["stderr_redacted"] = proc.stderr.strip()[:200]
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase 54H-3 pressure backfill plan")
    parser.add_argument("--skip-live-probes", action="store_true")
    parser.add_argument("--max-probe-calls", type=int, default=5)
    parser.add_argument("--server-probe", action="store_true", help="SSH server probe (no token printed)")
    parser.add_argument("--server-host", default="root@91.107.188.229")
    args = parser.parse_args()

    from worldcup_predictor.feature_store.pressure_store.backfill_plan import (
        check_token_readiness,
        design_backfill_targets,
        estimate_api_calls,
        recommend_go,
        run_live_probes,
    )

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    local = check_token_readiness(scope="local")
    target = design_backfill_targets()
    estimate = estimate_api_calls(target)

    server_info: dict = {"checked": False}
    if args.server_probe:
        server_info = _run_server_probe(args.server_host)

    probes = []
    if not args.skip_live_probes:
        probes = run_live_probes(max_calls=args.max_probe_calls)

    recommendation = recommend_go(local, server_info if server_info.get("checked") else None, probes, target)

    out = {
        "phase": "54H-3",
        "token_readiness": {"local": local.to_dict(), "server": server_info},
        "target_design": target,
        "api_estimate": estimate,
        "live_probes": [p.to_dict() for p in probes],
        "recommendation": recommendation,
    }
    (ARTIFACT_DIR / "plan.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(json.dumps({"recommendation": recommendation, "local_status": local.pressure_probe_status}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
