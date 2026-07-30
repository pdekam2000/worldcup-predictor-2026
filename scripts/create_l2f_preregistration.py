#!/usr/bin/env python3
"""Create immutable L2-F preregistration artifact (never overwrites prior versions)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from worldcup_predictor.research.infra_l2f_forward.preregistration import write_preregistration


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", default="artifacts/l2f_preregistration")
    args = ap.parse_args()
    result = write_preregistration(Path(args.out_dir))
    print(json.dumps({k: result[k] for k in ("path", "content_hash", "schema_version")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
