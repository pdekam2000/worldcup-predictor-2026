"""Authentication boundary for remote MCP transports."""

from __future__ import annotations

from worldcup_predictor.mcp_server.config import McpServerConfig


class McpAuthError(PermissionError):
    """Raised when remote MCP auth fails."""


def assert_remote_authorized(config: McpServerConfig, *, authorization_header: str | None = None) -> None:
    """STDIO inherits SSH auth; remote modes require MCP_AUTH_TOKEN."""
    if config.transport == "stdio":
        return
    expected = config.auth_token
    if not expected:
        raise McpAuthError("remote MCP requires MCP_AUTH_TOKEN to be configured")
    if not authorization_header:
        raise McpAuthError("missing Authorization header")
    prefix = "Bearer "
    if not authorization_header.startswith(prefix):
        raise McpAuthError("Authorization must use Bearer token")
    provided = authorization_header[len(prefix) :].strip()
    if provided != expected:
        raise McpAuthError("invalid MCP auth token")
