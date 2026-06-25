#!/usr/bin/env python3
"""Apply Phase 63 surgical patches on production."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "base44-d" / "src" / "App.jsx"
LOGIN = ROOT / "base44-d" / "src" / "pages" / "Login.jsx"
SAAS = ROOT / "base44-d" / "src" / "api" / "saasApi.js"


def patch_login(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "postLoginPath" in text:
        return
    if 'navigate("/dashboard"' in text:
        text = text.replace(
            'navigate("/dashboard", { replace: true });',
            'navigate((payload?.user?.role === "owner" ? "/owner" : "/dashboard"), { replace: true });',
        )
        path.write_text(text, encoding="utf-8")


def patch_saas(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if "fetchOwnerOverview" in text:
        return
    needle = "export async function fetchAdminPerformanceCertification()"
    block = """/** Phase 63 — Owner command center */
export async function fetchOwnerOverview() {
  return saasFetch("/api/owner/overview");
}
export async function fetchOwnerMonitoring() {
  return saasFetch("/api/owner/monitoring");
}
export async function fetchOwnerAutonomousStatus() {
  return saasFetch("/api/owner/autonomous/status");
}
export async function fetchOwnerNotifications() {
  return saasFetch("/api/owner/notifications");
}
export async function ownerRunAutonomousOnce() {
  return saasFetch("/api/owner/autonomous/run-once", { method: "POST" });
}
export async function ownerRunAutonomousEvaluation() {
  return saasFetch("/api/owner/autonomous/evaluation", { method: "POST" });
}
export async function ownerRunAutonomousCertification() {
  return saasFetch("/api/owner/autonomous/certification", { method: "POST" });
}
export async function ownerEnableScheduler() {
  return saasFetch("/api/owner/autonomous/scheduler/enable", { method: "POST" });
}
export async function ownerDisableScheduler() {
  return saasFetch("/api/owner/autonomous/scheduler/disable", { method: "POST" });
}

"""
    if needle in text:
        path.write_text(text.replace(needle, block + needle), encoding="utf-8")


def patch_app(path: Path) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    if 'path="/owner"' in text and "OwnerCommandCenter" in text:
        return
    # Minimal owner route block injection before protected routes
    owner_imports = (
        "import OwnerRoute from './components/OwnerRoute';\n"
        "import OwnerLayout from './components/owner/OwnerLayout';\n"
        "import OwnerCommandCenter from './pages/owner/OwnerCommandCenter';\n"
        "import OwnerAutonomousPage from './pages/owner/OwnerAutonomousPage';\n"
    )
    if "OwnerRoute" not in text and "import AdminPerformancePage" in text:
        text = text.replace(
            "import AdminPerformancePage",
            owner_imports + "import AdminPerformancePage",
        )
    block = (
        '\n      <Route element={<OwnerRoute />}>\n'
        '        <Route element={<OwnerLayout />}>\n'
        '          <Route path="/owner" element={<OwnerCommandCenter />} />\n'
        '          <Route path="/owner/autonomous" element={<OwnerAutonomousPage />} />\n'
        '        </Route>\n'
        '      </Route>\n\n'
    )
    if 'path="/owner"' not in text:
        text = text.replace(
            '      <Route element={<ProtectedRoute unauthenticatedElement={<Navigate to="/login" replace />} />}>',
            block + '      <Route element={<ProtectedRoute unauthenticatedElement={<Navigate to="/login" replace />} />}>',
        )
    path.write_text(text, encoding="utf-8")


def main() -> None:
    patch_login(LOGIN)
    patch_saas(SAAS)
    patch_app(APP)
    print("PHASE63_PATCH_OK")


if __name__ == "__main__":
    main()
