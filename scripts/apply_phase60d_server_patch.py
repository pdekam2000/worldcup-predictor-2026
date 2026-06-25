#!/usr/bin/env python3
"""Apply Phase 60D surgical patches on production (App/nav — no full App.jsx replace)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch_app_jsx(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "EliteWorldCupPage" in text and "/elite/world-cup" in text:
        if 'path="/account/settings"' in text and 'Navigate to="/settings"' in text:
            return
    if "import EliteWorldCupPage" not in text:
        text = text.replace(
            "import EliteShadowPreview from './pages/EliteShadowPreview';",
            "import EliteShadowPreview from './pages/EliteShadowPreview';\nimport EliteWorldCupPage from './pages/EliteWorldCupPage';",
        )
    if "/elite/world-cup" not in text:
        text = text.replace(
            '          <Route path="/admin/elite-shadow" element={<SuperAdminRoute><EliteShadowPreview /></SuperAdminRoute>} />',
            '          <Route path="/admin/elite-shadow" element={<SuperAdminRoute><EliteShadowPreview /></SuperAdminRoute>} />\n'
            '          <Route path="/elite/world-cup" element={<SuperAdminRoute><EliteWorldCupPage /></SuperAdminRoute>} />',
        )
    if 'path="/account/settings"' not in text:
        text = text.replace(
            '          <Route path="/settings"',
            '          <Route path="/account/settings" element={<Navigate to="/settings" replace />} />\n'
            '          <Route path="/settings"',
        )
    if 'path="/analytics/accuracy"' not in text:
        text = text.replace(
            '          <Route path="/accuracy"',
            '          <Route path="/analytics/accuracy" element={<Navigate to="/accuracy" replace />} />\n'
            '          <Route path="/accuracy"',
        )
    if "SuperAdminRoute><SuperAdminPanel" not in text:
        text = text.replace(
            '          <Route path="/super-admin" element={<SuperAdminPanel />} />',
            '          <Route path="/super-admin" element={<SuperAdminRoute><SuperAdminPanel /></SuperAdminRoute>} />',
        )
    path.write_text(text, encoding="utf-8")


def patch_nav(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "/elite/world-cup" in text:
        if 'path: "/settings"' in text:
            return
    text = text.replace('path: "/account/settings"', 'path: "/settings"')
    if '"/account/settings": "/settings"' not in text:
        text = text.replace(
            'export const LEGACY_PATH_ALIASES = {',
            'export const LEGACY_PATH_ALIASES = {\n\n  "/account/settings": "/settings",',
        )
    if 'label: "Elite World Cup"' not in text:
        text = text.replace(
            '    { label: "Elite Shadow", path: "/admin/elite-shadow", icon: Eye, roles: ["super_admin"] },',
            '    { label: "Elite Shadow", path: "/admin/elite-shadow", icon: Eye, roles: ["super_admin"] },\n\n'
            '    { label: "Elite World Cup", path: "/elite/world-cup", icon: Trophy, roles: ["super_admin"] },',
        )
    if 'item.path === "/elite/world-cup"' not in text:
        text = text.replace(
            '    if (item.path === "/admin/elite-shadow") return showSuperAdminNav;',
            '    if (item.path === "/admin/elite-shadow") return showSuperAdminNav;\n\n'
            '    if (item.path === "/elite/world-cup") return showSuperAdminNav;',
        )
    path.write_text(text, encoding="utf-8")


def patch_dashboard_layout(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "/elite/world-cup" in text:
        return
    if "Eye," not in text and " Eye" not in text:
        text = text.replace(
            "  Star, Timer, Target\n} from \"lucide-react\";",
            "  Star, Timer, Target, Eye\n} from \"lucide-react\";",
        )
        text = text.replace(
            "  Star, Timer, Target\n} from 'lucide-react';",
            "  Star, Timer, Target, Eye\n} from 'lucide-react';",
        )
        text = text.replace(
            "Heart, BellRing, Server, Star, Timer, Target\n} from \"lucide-react\";",
            "Heart, BellRing, Server, Star, Timer, Target, Eye\n} from \"lucide-react\";",
        )
    marker = '  { label: "Super Admin", path: "/super-admin", icon: Star },'
    if marker in text:
        text = text.replace(
            marker,
            '  { label: "Elite World Cup", path: "/elite/world-cup", icon: Trophy },\n'
            '  { label: "Elite Shadow", path: "/admin/elite-shadow", icon: Eye },\n'
            + marker,
        )
    elif 'path: "/super-admin"' in text:
        text = text.replace(
            '{ label: "Super Admin", path: "/super-admin", icon: Star }',
            '{ label: "Elite World Cup", path: "/elite/world-cup", icon: Trophy },\n'
            '  { label: "Elite Shadow", path: "/admin/elite-shadow", icon: Eye },\n'
            '  { label: "Super Admin", path: "/super-admin", icon: Star }',
        )
    path.write_text(text, encoding="utf-8")


def patch_saas_api(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    if "extractApiErrorMessage" not in text:
        text = text.replace(
            'import { buildApiUrl } from "@/lib/config";',
            'import { buildApiUrl } from "@/lib/config";\nimport { extractApiErrorMessage } from "@/lib/apiError";',
        )
    text = text.replace(
        """    const detail = payload?.detail;
    const message =
      typeof detail === "string"
        ? detail
        : payload?.message || `Request failed (${response.status})`;
    throw new Error(message);""",
        "    throw new Error(extractApiErrorMessage(payload, response.status));",
    )
    text = text.replace(
        "throw new Error(`Request failed (${response.status})`);",
        "throw new Error(extractApiErrorMessage(payload, response.status));",
    )
    if "fetchEliteWorldCupPredictions" not in text:
        marker = "/** Phase 51 — Elite Goal Timing engine */"
        block = """/** Phase 60D — Elite World Cup experimental predictions */
export async function fetchEliteWorldCupPredictions(params = {}) {
  const qs = new URLSearchParams({
    market: params.market || "all",
    tier: params.tier || "all",
    status: params.status || "all",
    limit: String(params.limit ?? 50),
    offset: String(params.offset ?? 0),
  });
  return saasFetch(`/api/elite/world-cup/predictions?${qs}`, { superAdminGate: true });
}

"""
        if marker in text:
            text = text.replace(marker, block + marker)
        else:
            text += "\n" + block
    path.write_text(text, encoding="utf-8")


def patch_main_py(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "elite_world_cup_router" not in text:
        text = text.replace(
            "from worldcup_predictor.api.routes.predictions import router as predictions_router",
            "from worldcup_predictor.api.routes.predictions import router as predictions_router\n"
            "from worldcup_predictor.api.routes.elite_world_cup import router as elite_world_cup_router",
        )
        text = text.replace(
            'app.include_router(goal_timing_router, prefix="/api")',
            'app.include_router(goal_timing_router, prefix="/api")\n'
            'app.include_router(elite_world_cup_router, prefix="/api")',
        )
    if "research_highlights_router" not in text and (
        ROOT / "worldcup_predictor/api/routes/research_highlights.py"
    ).is_file():
        text = text.replace(
            "from worldcup_predictor.api.routes.predictions import router as predictions_router",
            "from worldcup_predictor.api.routes.predictions import router as predictions_router\n"
            "from worldcup_predictor.api.routes.research_highlights import router as research_highlights_router",
        )
        anchor = 'app.include_router(elite_world_cup_router, prefix="/api")'
        if anchor in text:
            text = text.replace(
                anchor,
                anchor + '\napp.include_router(research_highlights_router, prefix="/api")',
            )
        else:
            text = text.replace(
                'app.include_router(goal_timing_router, prefix="/api")',
                'app.include_router(goal_timing_router, prefix="/api")\n'
                'app.include_router(research_highlights_router, prefix="/api")',
            )
    path.write_text(text, encoding="utf-8")


def main() -> int:
    patch_app_jsx(ROOT / "base44-d/src/App.jsx")
    patch_nav(ROOT / "base44-d/src/lib/navConfig.js")
    patch_dashboard_layout(ROOT / "base44-d/src/components/dashboard/DashboardLayout.jsx")
    patch_main_py(ROOT / "worldcup_predictor/api/main.py")
    saas_path = ROOT / "base44-d/src/api/saasApi.js"
    if saas_path.is_file() and "fetchEliteWorldCupPredictions" not in saas_path.read_text(encoding="utf-8"):
        patch_saas_api(saas_path)
    print("PATCH_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
