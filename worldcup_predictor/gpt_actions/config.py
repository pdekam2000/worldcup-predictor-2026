"""GPT Actions bridge configuration (secrets from environment only)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GptActionsConfig:
    host: str
    port: int
    api_key: str | None
    audit_log_path: str
    job_store_dir: str
    max_jobs_retained: int
    rate_limit_per_minute: int
    max_fixture_ids_per_job: int
    max_response_chars: int
    poll_after_seconds: int

    @property
    def bind_localhost_only(self) -> bool:
        return self.host in ("127.0.0.1", "localhost", "::1")


def load_gpt_actions_config() -> GptActionsConfig:
    root = Path(os.environ.get("APP_ROOT", "/opt/worldcup-predictor"))
    job_dir = os.environ.get("GPT_ACTIONS_JOB_DIR") or str(root / "artifacts" / "gpt_actions_jobs")
    audit = os.environ.get("GPT_ACTIONS_AUDIT_LOG_PATH") or "/var/log/worldcup-gpt-actions/audit.jsonl"
    return GptActionsConfig(
        host=(os.environ.get("GPT_ACTIONS_HOST") or "127.0.0.1").strip(),
        port=int(os.environ.get("GPT_ACTIONS_PORT") or "8770"),
        api_key=(os.environ.get("GPT_ACTIONS_API_KEY") or "").strip() or None,
        audit_log_path=audit,
        job_store_dir=job_dir,
        max_jobs_retained=int(os.environ.get("GPT_ACTIONS_MAX_JOBS_RETAINED") or "50"),
        rate_limit_per_minute=int(os.environ.get("GPT_ACTIONS_RATE_LIMIT_PER_MIN") or "60"),
        max_fixture_ids_per_job=int(os.environ.get("GPT_ACTIONS_MAX_FIXTURES_PER_JOB") or "20"),
        max_response_chars=int(os.environ.get("GPT_ACTIONS_MAX_RESPONSE_CHARS") or "95000"),
        poll_after_seconds=int(os.environ.get("GPT_ACTIONS_POLL_AFTER_SECONDS") or "3"),
    )
