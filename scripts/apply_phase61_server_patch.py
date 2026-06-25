#!/usr/bin/env python3
"""Surgical Phase 61 patch — register admin performance API on production main.py."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_main_py(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "admin_performance_router" in text:
        return
    if "from worldcup_predictor.api.routes.admin_performance import router as admin_performance_router" not in text:
        text = text.replace(
            "from worldcup_predictor.api.routes.admin_elite_shadow import router as admin_elite_shadow_router",
            "from worldcup_predictor.api.routes.admin_elite_shadow import router as admin_elite_shadow_router\n"
            "from worldcup_predictor.api.routes.admin_performance import router as admin_performance_router",
        )
    if "app.include_router(admin_performance_router" not in text:
        text = text.replace(
            "app.include_router(admin_elite_shadow_router, prefix=\"/api\")",
            "app.include_router(admin_elite_shadow_router, prefix=\"/api\")\n"
            "app.include_router(admin_performance_router, prefix=\"/api\")",
        )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    patch_main_py(ROOT / "worldcup_predictor/api/main.py")
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
