"""GPT Actions bridge server entrypoint."""

from __future__ import annotations

import argparse
import json

import uvicorn

from worldcup_predictor.gpt_actions.app import create_app
from worldcup_predictor.gpt_actions.config import load_gpt_actions_config
from worldcup_predictor.gpt_actions.policies import APPROVED_OPERATION_IDS, APPROVED_ROUTES


def dry_test() -> dict[str, object]:
    config = load_gpt_actions_config()
    return {
        "service": "worldcup-gpt-actions",
        "host": config.host,
        "port": config.port,
        "bind_localhost_only": config.bind_localhost_only,
        "approved_routes": sorted(APPROVED_ROUTES),
        "approved_operation_ids": sorted(APPROVED_OPERATION_IDS),
        "route_count": len(APPROVED_ROUTES),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="WorldCup GPT Actions bridge")
    parser.add_argument("--dry-test", action="store_true", help="Print route manifest and exit")
    args = parser.parse_args(argv)

    if args.dry_test:
        print(json.dumps(dry_test(), indent=2))
        return 0

    config = load_gpt_actions_config()
    if not config.bind_localhost_only:
        raise SystemExit("GPT Actions bridge must bind to localhost only")
    app = create_app(config)
    uvicorn.run(app, host=config.host, port=config.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
