"""PHASE ECSE-X2-M7 — Pre-enable safety backups."""

from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.research.ecse_x2_m6.constants import EVAL_ARTIFACT, SHADOW_ARTIFACT
from worldcup_predictor.research.ecse_x2_m7.constants import BACKUP_ROOT


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def create_pre_enable_backup() -> dict[str, Any]:
    root = _repo_root()
    stamp = _utc_stamp()
    backup_dir = root / BACKUP_ROOT / stamp
    backup_dir.mkdir(parents=True, exist_ok=True)

    commit = ""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        commit = "unknown"

    manifest: dict[str, Any] = {
        "phase": "ECSE-X2-M7",
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "git_commit": commit,
        "backup_dir": str(backup_dir.relative_to(root)).replace("\\", "/"),
        "files": [],
    }

    for rel in (
        SHADOW_ARTIFACT,
        EVAL_ARTIFACT,
        "deployment/.env.production.example",
        ".env.production.example",
    ):
        src = root / rel
        if src.is_file():
            dest = backup_dir / Path(rel).name
            shutil.copy2(src, dest)
            manifest["files"].append({"source": rel, "backup": str(dest.relative_to(root)).replace("\\", "/")})

    env_candidates = [
        root / "deployment" / ".env.production",
        root / ".env.production",
        Path("/opt/worldcup-predictor/.env.production"),
    ]
    for env_path in env_candidates:
        if env_path.is_file():
            dest = backup_dir / f"env_backup_{env_path.name}"
            shutil.copy2(env_path, dest)
            manifest["files"].append(
                {
                    "source": str(env_path),
                    "backup": str(dest.relative_to(root)).replace("\\", "/"),
                    "note": "production env copy",
                }
            )
            break
    else:
        manifest["env_note"] = "no production .env found locally; backed up .env.production.example only"

    (backup_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    manifest["manifest_path"] = str((backup_dir / "manifest.json").relative_to(root)).replace("\\", "/")
    return manifest
