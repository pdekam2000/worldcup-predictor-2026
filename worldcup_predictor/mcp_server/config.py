"""MCP server configuration from environment (no secrets in repo)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal

TransportMode = Literal["stdio", "sse", "streamable-http"]


@dataclass(frozen=True)
class McpServerConfig:
    transport: TransportMode
    host: str
    port: int
    audit_log_path: str
    auth_token: str | None
    caller_mode: str
    dry_test: bool

    @property
    def bind_localhost_only(self) -> bool:
        return self.host in ("127.0.0.1", "localhost", "::1")


def load_mcp_config(*, dry_test: bool = False, transport: str | None = None) -> McpServerConfig:
    mode = (transport or os.environ.get("MCP_TRANSPORT") or "stdio").strip().lower()
    if mode not in ("stdio", "sse", "streamable-http"):
        mode = "stdio"
    host = (os.environ.get("MCP_HOST") or "127.0.0.1").strip()
    port = int(os.environ.get("MCP_PORT") or "8765")
    audit = os.environ.get("MCP_AUDIT_LOG_PATH") or "/var/log/worldcup-mcp/audit.jsonl"
    token = os.environ.get("MCP_AUTH_TOKEN") or None
    caller = os.environ.get("MCP_CALLER_MODE") or ("stdio" if mode == "stdio" else "remote")
    return McpServerConfig(
        transport=mode,  # type: ignore[arg-type]
        host=host,
        port=port,
        audit_log_path=audit,
        auth_token=token,
        caller_mode=caller,
        dry_test=dry_test,
    )
