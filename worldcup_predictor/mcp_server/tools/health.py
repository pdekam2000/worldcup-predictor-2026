"""MCP health tools."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from worldcup_predictor.config.app_version import build_version_payload
from worldcup_predictor.config.settings import get_settings
from worldcup_predictor.mcp_server.policies import MCP_VERSION


def _service_active(name: str) -> str:
    try:
        out = subprocess.check_output(
            ["systemctl", "is-active", name],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        ).strip()
        return out or "unknown"
    except (OSError, subprocess.SubprocessError, FileNotFoundError):
        return "unknown"


def _cpu_snapshot() -> dict[str, Any]:
    try:
        load = os.getloadavg()
        return {"load_1m": load[0], "load_5m": load[1], "load_15m": load[2]}
    except (AttributeError, OSError):
        return {}


def _memory_snapshot() -> dict[str, Any]:
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        return {
            "total_bytes": vm.total,
            "available_bytes": vm.available,
            "percent_used": vm.percent,
        }
    except Exception:
        proc = Path("/proc/meminfo")
        if proc.is_file():
            data = {}
            for line in proc.read_text(encoding="utf-8").splitlines()[:5]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    data[k.strip()] = v.strip()
            return {"meminfo": data}
        return {}


def server_health() -> dict[str, Any]:
    settings = get_settings()
    db_path = settings.sqlite_path
    db_size = 0
    db_exists = False
    if db_path and Path(db_path).exists():
        db_exists = True
        db_size = Path(db_path).stat().st_size

    root = Path(db_path).parent if db_path else Path(".")
    disk = shutil.disk_usage(root if root.exists() else Path("."))

    version = build_version_payload()
    app_health: dict[str, Any] = {"status": "ok"}
    try:
        import httpx

        resp = httpx.get("http://127.0.0.1:8000/api/health", timeout=2.0)
        app_health = {"status": "ok" if resp.status_code == 200 else "degraded", "http_status": resp.status_code}
    except Exception:
        app_health = {"status": "unreachable"}

    return {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "hostname": socket.gethostname(),
        "service_worldcup_api": _service_active("worldcup-api"),
        "application_health": app_health,
        "cpu": _cpu_snapshot(),
        "memory": _memory_snapshot(),
        "disk": {
            "total_bytes": disk.total,
            "used_bytes": disk.used,
            "free_bytes": disk.free,
        },
        "database": {"exists": db_exists, "size_bytes": db_size},
        "current_git_sha": version.get("commit") or version.get("git_sha"),
        "mcp_version": MCP_VERSION,
    }
