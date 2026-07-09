"""Resolve live deployment Git SHA for MCP health reporting."""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Any, Literal

GitShaSource = Literal["deployment_env", "git_head", "unavailable"]

_SHA_RE = re.compile(r"^[0-9a-fA-F]{7,40}$")
_DEPLOY_ENV_KEYS = ("DEPLOY_COMMIT", "GIT_COMMIT", "DEPLOYMENT_SHA")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _normalize_sha(value: str) -> str | None:
    candidate = value.strip().lower()
    if not candidate or not _SHA_RE.fullmatch(candidate):
        return None
    return candidate


def _read_git_head(repo_root: Path) -> str | None:
    if not (repo_root / ".git").exists():
        return None
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return _normalize_sha(out.strip())


def _read_deployment_env_sha() -> str | None:
    for key in _DEPLOY_ENV_KEYS:
        raw = os.getenv(key, "").strip()
        if not raw:
            continue
        normalized = _normalize_sha(raw)
        if normalized:
            return normalized
    return None


def resolve_current_git_sha(*, repo_root: Path | None = None) -> dict[str, Any]:
    """Return live Git SHA with explicit source attribution.

    Priority:
    1. Validated deployment env SHA (DEPLOY_COMMIT / GIT_COMMIT / DEPLOYMENT_SHA)
    2. Repository Git HEAD (fixed internal path; no MCP/user input)
    3. unavailable
    """
    root = repo_root or _repo_root()
    env_sha = _read_deployment_env_sha()
    if env_sha:
        return {"current_git_sha": env_sha, "git_sha_source": "deployment_env"}

    git_sha = _read_git_head(root)
    if git_sha:
        return {"current_git_sha": git_sha, "git_sha_source": "git_head"}

    return {"current_git_sha": None, "git_sha_source": "unavailable"}
