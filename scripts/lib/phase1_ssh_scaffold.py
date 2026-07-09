"""Pure helpers for Phase 1 SSH scaffold (local validation only, no network)."""

from __future__ import annotations

import re
from typing import Iterable

SSH_HOST_BLOCK_MARKER = "# BEGIN worldcup-prod (managed by setup_hetzner_ssh_windows.ps1)"
SSH_HOST_BLOCK_END = "# END worldcup-prod"

FORBIDDEN_SUDO_PATTERNS = (
    r"NOPASSWD:\s*ALL",
    r"ALL=\(ALL\)\s+NOPASSWD:\s*ALL",
    r"systemctl\s+restart\s+\*",
    r"journalctl\s+\*",
    r"\b/usr/bin/bash\b",
    r"\b/bin/bash\b",
    r"\b/usr/bin/sh\b",
    r"\bsudo\s+-i\b",
    r"\bsu\s+-",
)

SECRET_PATTERNS = (
    r"-----BEGIN (?:OPENSSH |RSA |EC )?PRIVATE KEY-----",
    r"PasswordAuthentication\s+yes\s*#.*password\s*=",
    r"HETZNER_PASSWORD\s*=",
    r"root@[0-9]{1,3}(?:\.[0-9]{1,3}){3}",
)


def build_ssh_host_block(hostname: str, *, user: str = "deploy", port: int = 22) -> str:
    host = hostname.strip()
    if not host:
        raise ValueError("hostname is required")
    return (
        f"{SSH_HOST_BLOCK_MARKER}\n"
        f"Host worldcup-prod\n"
        f"    HostName {host}\n"
        f"    User {user}\n"
        f"    Port {port}\n"
        f"    IdentityFile ~/.ssh/worldcup_hetzner_ed25519\n"
        f"    IdentitiesOnly yes\n"
        f"    ServerAliveInterval 30\n"
        f"    ServerAliveCountMax 3\n"
        f"{SSH_HOST_BLOCK_END}\n"
    )


def merge_ssh_config(existing: str, hostname: str, *, user: str = "deploy", port: int = 22) -> str:
    block = build_ssh_host_block(hostname, user=user, port=port)
    if SSH_HOST_BLOCK_MARKER in existing:
        pattern = re.compile(
            rf"{re.escape(SSH_HOST_BLOCK_MARKER)}.*?{re.escape(SSH_HOST_BLOCK_END)}\n?",
            re.DOTALL,
        )
        return pattern.sub(block, existing).rstrip() + "\n"
    if "Host worldcup-prod" in existing and SSH_HOST_BLOCK_MARKER not in existing:
        # Legacy unmanaged block — replace first worldcup-prod stanza conservatively.
        pattern = re.compile(r"Host worldcup-prod\b.*?(?=\nHost |\Z)", re.DOTALL)
        replaced, n = pattern.subn(block.rstrip() + "\n", existing, count=1)
        if n:
            return replaced.rstrip() + "\n"
    sep = "\n" if existing and not existing.endswith("\n") else ""
    return (existing + sep + block).rstrip() + "\n"


def append_authorized_key_if_missing(authorized_keys: str, public_key: str) -> tuple[str, bool]:
    key = public_key.strip()
    if not key:
        raise ValueError("public key is empty")
    if " " not in key:
        raise ValueError("public key must look like: <type> <base64> [comment]")
    lines = [ln.strip() for ln in authorized_keys.splitlines() if ln.strip()]
    key_body = key.split()[1]
    for ln in lines:
        parts = ln.split()
        if len(parts) >= 2 and parts[1] == key_body:
            return authorized_keys.rstrip() + ("\n" if authorized_keys else ""), False
    out = (authorized_keys.rstrip() + "\n" + key + "\n") if authorized_keys.strip() else (key + "\n")
    return out, True


def normalize_log_lines(value: str | int, *, default: int = 100, maximum: int = 500) -> int:
    if isinstance(value, int):
        n = value
    else:
        text = str(value).strip()
        if not text.isdigit():
            raise ValueError("log lines must be a positive integer")
        n = int(text)
    if n < 1:
        raise ValueError("log lines must be at least 1")
    if n > maximum:
        raise ValueError(f"log lines must not exceed {maximum}")
    return n


def _strip_sudo_comments(content: str) -> str:
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line.split("#", 1)[0]
        lines.append(line)
    return "\n".join(lines)


def validate_sudoers_content(content: str) -> list[str]:
    violations: list[str] = []
    active = _strip_sudo_comments(content)
    for pat in FORBIDDEN_SUDO_PATTERNS:
        if re.search(pat, active, re.IGNORECASE):
            violations.append(pat)
    if "NOPASSWD" in active:
        if "worldcup-api" not in active and "scripts/ops/" not in active:
            violations.append("NOPASSWD without scoped commands")
    return violations


def scan_text_for_secrets(text: str) -> list[str]:
    hits: list[str] = []
    for pat in SECRET_PATTERNS:
        if re.search(pat, text, re.IGNORECASE | re.MULTILINE):
            hits.append(pat)
    return hits


def scan_files_for_secrets(paths: Iterable[str], reader) -> list[tuple[str, str]]:
    """reader: callable(path) -> str"""
    found: list[tuple[str, str]] = []
    for path in paths:
        try:
            text = reader(path)
        except OSError:
            continue
        for pat in scan_text_for_secrets(text):
            found.append((path, pat))
    return found
