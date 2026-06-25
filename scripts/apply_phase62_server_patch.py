#!/usr/bin/env python3
"""Apply Phase 62 surgical patches on production (routes + owner login; no full App replace)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "base44-d" / "src" / "App.jsx"


def _insert_after(text: str, needle: str, block: str) -> str:
    if block.strip() in text:
        return text
    if needle not in text:
        return text
    return text.replace(needle, needle + block, 1)


def patch_app_jsx(path: Path) -> None:
    text = path.read_text(encoding="utf-8")

    text = _insert_after(
        text,
        "import ResetPassword from './pages/ResetPassword';",
        "\nimport OwnerLogin from './pages/OwnerLogin';",
    )

    pages_dir = path.parent / "pages"
    if (pages_dir / "ResearchHighlights.jsx").is_file():
        text = _insert_after(
            text,
            "import ImprintPage from './pages/legal/ImprintPage';",
            "\nimport ResearchHighlights from './pages/ResearchHighlights';",
        )

    if (ROOT / "base44-d" / "src" / "components" / "AdminRoute.jsx").is_file():
        text = _insert_after(
            text,
            "import ProtectedRoute from '@/components/ProtectedRoute';",
            "\nimport AdminRoute from '@/components/AdminRoute';",
        )

    for mod, name in [
        ("GoalTimingAccuracyPage", "goalTiming/GoalTimingAccuracyPage"),
        ("GoalTimingPerformancePage", "goalTiming/GoalTimingPerformancePage"),
        ("AdminPerformancePage", "AdminPerformancePage"),
    ]:
        if (pages_dir / f"{mod}.jsx").is_file() and f"import {mod}" not in text:
            text = _insert_after(
                text,
                "import GoalTimingInsightsPage from './pages/goalTiming/GoalTimingInsightsPage';",
                f"\nimport {mod} from './pages/{name}';",
            )

    owner_routes = (
        '\n      <Route path="/owner-login" element={<OwnerLogin />} />\n'
        '      <Route path="/system/owner-access" element={<Navigate to="/owner-login" replace />} />\n'
    )
    text = _insert_after(
        text,
        '      <Route path="/reset-password" element={<ResetPassword />} />\n',
        owner_routes,
    )

    if "ResearchHighlights" in text and 'path="/research/highlights"' not in text:
        text = _insert_after(
            text,
            '      <Route path="/imprint" element={<ImprintPage />} />\n',
            '\n      <Route path="/research/highlights" element={<ResearchHighlights />} />\n',
        )

    if 'path="/admin/dashboard"' not in text:
        text = _insert_after(
            text,
            '      <Route element={<ProtectedRoute unauthenticatedElement={<Navigate to="/login" replace />} />}>',
            '\n      <Route path="/admin/dashboard" element={<Navigate to="/admin" replace />} />\n',
        )

    if "GoalTimingAccuracyPage" in text and 'path="/goal-timing/accuracy"' not in text:
        text = _insert_after(
            text,
            '          <Route path="/goal-timing/history" element={<GoalTimingHistoryPage />} />\n',
            '          <Route path="/goal-timing/accuracy" element={<GoalTimingAccuracyPage />} />\n',
        )

    if "GoalTimingPerformancePage" in text and 'path="/goal-timing/performance"' not in text:
        text = _insert_after(
            text,
            '          <Route path="/goal-timing/accuracy" element={<GoalTimingAccuracyPage />} />\n',
            '          <Route path="/goal-timing/performance" element={<GoalTimingPerformancePage />} />\n',
        )

    if "AdminPerformancePage" in text and 'path="/admin/performance"' not in text:
        text = _insert_after(
            text,
            '          <Route path="/admin/elite-shadow" element={<SuperAdminRoute><EliteShadowPreview /></SuperAdminRoute>} />\n',
            '          <Route path="/admin/performance" element={<SuperAdminRoute><AdminPerformancePage /></SuperAdminRoute>} />\n',
        )

    if "AdminRoute" in text and "<AdminRoute>" not in text and 'path="/admin" element={<AdminPanel />}' in text:
        text = text.replace(
            '          <Route path="/admin" element={<AdminPanel />} />',
            '          <Route path="/admin" element={<AdminRoute><AdminPanel /></AdminRoute>} />',
        )

    path.write_text(text, encoding="utf-8")


def patch_saas_api(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "fetchAdminPerformanceCertification" in text:
        return
    needle = "export async function fetchGoalTimingStatus()"
    block = (
        "export async function fetchAdminPerformanceCertification() {\n"
        "  return saasFetch(\"/api/admin/performance/certification\", { superAdminGate: true });\n"
        "}\n\n"
    )
    if needle in text:
        path.write_text(text.replace(needle, block + needle), encoding="utf-8")


def main() -> None:
    patch_app_jsx(APP)
    patch_saas_api(ROOT / "base44-d" / "src" / "api" / "saasApi.js")
    print("PHASE62_PATCH_OK")


if __name__ == "__main__":
    main()
