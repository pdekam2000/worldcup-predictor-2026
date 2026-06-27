"""Production deploy status reader — Phase A21B."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def deploy_log_dir() -> Path:
    app = Path(os.getenv("DEPLOY_APP", "/opt/worldcup-predictor"))
    return Path(os.getenv("DEPLOY_LOG_DIR", str(app / "logs" / "deploy")))


def latest_session_file() -> Path:
    return deploy_log_dir() / ".latest_session"


@dataclass
class DeployStatusView:
    session_id: str | None
    state: str
    current_step: str
    message: str
    pid: int | None
    started_at: str | None
    updated_at: str | None
    log_file: str | None
    checkpoint_file: str | None
    rollback: str | None
    deploy_label: str | None
    lock_held: bool
    lock_info: str | None
    log_tail: list[str]
    status_path: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "current_step": self.current_step,
            "message": self.message,
            "pid": self.pid,
            "started_at": self.started_at,
            "updated_at": self.updated_at,
            "log_file": self.log_file,
            "checkpoint_file": self.checkpoint_file,
            "rollback": self.rollback,
            "deploy_label": self.deploy_label,
            "lock_held": self.lock_held,
            "lock_info": self.lock_info,
            "log_tail": self.log_tail,
            "status_path": self.status_path,
        }


def _read_lock_info(lock_path: Path) -> tuple[bool, str | None]:
    if not lock_path.is_file():
        return False, None
    try:
        content = lock_path.read_text(encoding="utf-8", errors="replace").strip()
        return bool(content), content or None
    except OSError:
        return True, "unreadable"


def _load_status_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _tail_lines(path: Path, n: int = 25) -> list[str]:
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except OSError:
        return []


def resolve_session_id(session_id: str | None = None) -> str | None:
    if session_id:
        return session_id
    latest = latest_session_file()
    if latest.is_file():
        sid = latest.read_text(encoding="utf-8", errors="replace").strip()
        if sid:
            return sid
    log_dir = deploy_log_dir()
    if not log_dir.is_dir():
        return None
    statuses = sorted(log_dir.glob("deploy_*.status.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not statuses:
        return None
    name = statuses[0].name
    if name.startswith("deploy_") and name.endswith(".status.json"):
        return name[len("deploy_") : -len(".status.json")]
    return None


def read_deploy_status(*, session_id: str | None = None, log_lines: int = 25) -> DeployStatusView:
    log_dir = deploy_log_dir()
    lock_path = Path(os.getenv("DEPLOY_LOCK_FILE", str(log_dir / ".deploy.lock")))
    lock_held, lock_info = _read_lock_info(lock_path)

    sid = resolve_session_id(session_id)
    status_path: Path | None = None
    payload: dict[str, Any] = {}

    if sid:
        candidate = log_dir / f"deploy_{sid}.status.json"
        if candidate.is_file():
            status_path = candidate
            payload = _load_status_json(candidate)

    log_file = payload.get("log_file")
    log_path = Path(log_file) if log_file else (log_dir / f"deploy_{sid}.log" if sid else None)
    tail = _tail_lines(log_path, log_lines) if log_path else []

    if not payload and sid:
        return DeployStatusView(
            session_id=sid,
            state="unknown",
            current_step="",
            message="No status file yet; deploy may still be starting",
            pid=None,
            started_at=None,
            updated_at=None,
            log_file=str(log_path) if log_path else None,
            checkpoint_file=str(log_dir / f"deploy_{sid}.checkpoint") if sid else None,
            rollback=None,
            deploy_label=None,
            lock_held=lock_held,
            lock_info=lock_info,
            log_tail=tail,
            status_path=str(status_path) if status_path else None,
        )

    if not sid:
        return DeployStatusView(
            session_id=None,
            state="idle",
            current_step="",
            message="No deploy sessions found",
            pid=None,
            started_at=None,
            updated_at=None,
            log_file=None,
            checkpoint_file=None,
            rollback=None,
            deploy_label=None,
            lock_held=lock_held,
            lock_info=lock_info,
            log_tail=[],
            status_path=None,
        )

    return DeployStatusView(
        session_id=payload.get("session_id", sid),
        state=str(payload.get("state", "unknown")),
        current_step=str(payload.get("current_step", "")),
        message=str(payload.get("message", "")),
        pid=payload.get("pid"),
        started_at=payload.get("started_at"),
        updated_at=payload.get("updated_at"),
        log_file=payload.get("log_file"),
        checkpoint_file=payload.get("checkpoint_file"),
        rollback=payload.get("rollback"),
        deploy_label=payload.get("deploy_label"),
        lock_held=lock_held,
        lock_info=lock_info,
        log_tail=tail,
        status_path=str(status_path) if status_path else None,
    )


def format_deploy_status_text(view: DeployStatusView) -> str:
    lines = [
        f"Deploy session: {view.session_id or '—'}",
        f"State: {view.state}",
        f"Step: {view.current_step or '—'}",
        f"Message: {view.message or '—'}",
        f"PID: {view.pid if view.pid is not None else '—'}",
        f"Started: {view.started_at or '—'}",
        f"Updated: {view.updated_at or '—'}",
        f"Lock held: {view.lock_held}" + (f" ({view.lock_info})" if view.lock_info else ""),
        f"Log: {view.log_file or '—'}",
        f"Status file: {view.status_path or '—'}",
    ]
    if view.rollback:
        lines.append(f"Rollback: {view.rollback}")
    if view.log_tail:
        lines.append("")
        lines.append("--- log tail ---")
        lines.extend(view.log_tail)
    return "\n".join(lines)


def run_deploy_status_command(
    *,
    session_id: str | None = None,
    json_output: bool = False,
    log_lines: int = 25,
) -> int:
    view = read_deploy_status(session_id=session_id, log_lines=log_lines)
    if json_output:
        print(json.dumps(view.to_dict(), indent=2))
    else:
        print(format_deploy_status_text(view))
    if view.state == "failed":
        return 2
    if view.state in ("running", "blocked"):
        return 1
    return 0
