"""Read-only production Sportmonks configuration audit — no secrets printed."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ENV_PATH = Path("/opt/worldcup-predictor/.env.production")


def _var_presence(name: str) -> tuple[bool, bool]:
    if not ENV_PATH.is_file():
        return False, False
    text = ENV_PATH.read_text(encoding="utf-8", errors="replace")
    in_file = bool(re.search(rf"^{re.escape(name)}=", text, re.MULTILINE))
    if not in_file:
        return False, False
    for line in text.splitlines():
        if line.startswith(f"{name}="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            return True, bool(val)
    return True, False


def main() -> int:
    print("=== PRODUCTION SPORTMONKS ENV AUDIT ===")
    print(f"env_file_exists: {ENV_PATH.is_file()}")
    for var in ("SPORTMONKS_API_TOKEN", "SPORTMONKS_API_KEY", "SPORTMONKS_BASE_URL"):
        in_file, non_empty = _var_presence(var)
        print(f"{var}_in_file: {in_file}")
        print(f"{var}_non_empty: {non_empty}")

    from worldcup_predictor.config.settings import Settings
    from worldcup_predictor.providers.sportmonks_provider import SportmonksProvider

    s = Settings(_env_file=str(ENV_PATH) if ENV_PATH.is_file() else None)
    if s.sportmonks_api_token.strip():
        src = "SPORTMONKS_API_TOKEN"
    elif s.sportmonks_api_key.strip():
        src = "SPORTMONKS_API_KEY"
    else:
        src = "none"
    print(f"runtime_sportmonks_configured: {s.sportmonks_configured}")
    print(f"runtime_token_source: {src}")
    print(f"runtime_token_length: {len(s.sportmonks_effective_token)}")
    print(f"runtime_base_url: {s.sportmonks_base_url}")

    test = SportmonksProvider(s).run_world_cup_connectivity_test()
    print(f"connectivity_configured: {test.configured}")
    print(f"connectivity_connected: {test.connected}")
    print(f"connectivity_status_code: {test.status_code}")
    print(f"connectivity_endpoint: {test.endpoint_path}")
    print(f"connectivity_message: {test.message[:160]}")
    return 0


if __name__ == "__main__":
    sys.path.insert(0, "/opt/worldcup-predictor")
    raise SystemExit(main())
