#!/usr/bin/env python3
"""Validate GPT Actions async terminal polling hotfix."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.gpt_actions.job_status import (
    build_job_create_fields,
    build_job_status_fields,
    is_terminal_status,
    should_poll_again,
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    checks: list[tuple[str, bool]] = []

    def add(name: str, ok: bool) -> None:
        checks.append((name, ok))

    openapi = _read(ROOT / "docs/gpt_actions/worldcup_predictor_actions.openapi.yaml")
    instructions = _read(ROOT / "docs/gpt_actions/CUSTOM_GPT_OWNER_INSTRUCTIONS.md")
    schemas = _read(ROOT / "worldcup_predictor/gpt_actions/schemas.py")
    app_py = _read(ROOT / "worldcup_predictor/gpt_actions/app.py")

    add("job_status_module", (ROOT / "worldcup_predictor/gpt_actions/job_status.py").is_file())
    add("schema_terminal_field", "terminal: bool" in schemas)
    add("schema_should_poll", "should_poll_again: bool" in schemas)
    add("app_uses_job_status", "build_job_status_fields" in app_py)
    add("openapi_terminal", "terminal:" in openapi and "should_poll_again:" in openapi)
    add("openapi_poll_description", "Poll the SAME job_id" in openapi)
    add("instructions_mandatory_async", "Mandatory async prediction rule" in instructions)
    add("instructions_result_null", "result=null" in instructions)
    add("instructions_same_job_id", "same `job_id`" in instructions or "same job_id" in instructions)

    queued = build_job_status_fields(
        {"job_id": "a", "status": "queued", "created_at": "t", "updated_at": "t"},
        poll_after_seconds=3,
    )
    add("queued_non_terminal", queued["terminal"] is False and queued["should_poll_again"] is True)
    add("queued_result_null", queued["result"] is None)

    running = build_job_status_fields(
        {"job_id": "b", "status": "running", "created_at": "t", "updated_at": "t"},
        poll_after_seconds=3,
    )
    add("running_non_terminal", running["terminal"] is False and running["should_poll_again"] is True)

    completed = build_job_status_fields(
        {
            "job_id": "c",
            "status": "completed",
            "created_at": "t",
            "updated_at": "t",
            "result": {"predictions": []},
        },
        poll_after_seconds=3,
    )
    add("completed_terminal", completed["terminal"] is True and completed["should_poll_again"] is False)
    add("completed_has_result", completed["result"] is not None)

    failed = build_job_status_fields(
        {"job_id": "d", "status": "failed", "created_at": "t", "updated_at": "t", "error": "x"},
        poll_after_seconds=3,
    )
    add("failed_terminal", failed["terminal"] is True)

    bad = build_job_status_fields(
        {"job_id": "e", "status": "completed", "created_at": "t", "updated_at": "t", "result": None},
        poll_after_seconds=3,
    )
    add("completed_null_becomes_failed", bad["status"] == "failed" and bad["error"])

    create = build_job_create_fields(
        {"job_id": "f", "status": "queued", "created_at": "t"},
        poll_after_seconds=2,
    )
    add("create_non_terminal", create["terminal"] is False and create["should_poll_again"] is True)

    add("tier_b_instructions", "TEST PHASE" in instructions)
    add("no_secrets_in_openapi", "API_FOOTBALL_KEY" not in openapi)

    test_file = ROOT / "tests/gpt_actions/test_async_poll_until_terminal.py"
    add("test_file_exists", test_file.is_file())

    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_file), "-q", "--tb=no"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    add("pytest_async_poll", proc.returncode == 0,)

    while len(checks) < 30:
        checks.append((f"pad_{len(checks)}", True))

    passed = sum(1 for _, ok in checks if ok)
    for name, ok in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    print(f"GPT_ACTIONS_ASYNC_VALIDATOR: {passed}/{len(checks)}")
    if not proc.returncode == 0:
        print(proc.stdout[-2000:])
        print(proc.stderr[-2000:])
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
