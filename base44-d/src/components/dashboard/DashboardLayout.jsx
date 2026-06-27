import React, { useState, useMemo } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import RouteErrorBoundary from "@/components/ui/RouteErrorBoundary";
import { useAuth } from "@/lib/AuthContext";
import { Menu, ChevronLeft, Bell, Trophy } from "lucide-react";
import SidebarNav from "@/components/layout/SidebarNav";
import AppVersionBadge from "@/components/layout/AppVersionBadge";
import QuotaChip from "@/components/layout/QuotaChip";
import EmailVerificationBanner from "@/components/auth/EmailVerificationBanner";
import { buildNavSections, resolvePageMeta, isNavItemActive } from "@/lib/navConfig";

function LivePulse({ className = "" }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-400 ${className}`}
    >
      <span className="w-2 h-2 rounded-full bg-emerald-400 animate-live-pulse" />
      Live
    </span>
  );
}

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const { user, logout } = useAuth();

  const sections = useMemo(() => buildNavSections({ user }), [user]);
  const pageMeta = useMemo(
    () => resolvePageMeta(location.pathname),
    [location.pathname]
  );

  const flatItems = sections.flatMap((s) => s.items);
  const activeItem = flatItems.find((item) => isNavItemActive(location.pathname, item));
  const pageTitle = activeItem?.label || pageMeta.title || "Hub";

  const SidebarShell = ({ mobile = false }) => (
    <div className="flex flex-col h-full bg-[#14181f] border-[#2a3140]">
      <div className="p-4 flex items-center justify-between border-b border-[#2a3140]">
        <Link
          to="/dashboard"
          className="flex items-center gap-2.5 min-w-0"
          onClick={() => mobile && setSidebarOpen(false)}
        >
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-amber-400 to-yellow-500 flex items-center justify-center flex-shrink-0 shadow-lg shadow-amber-500/25">
            <Trophy className="w-4 h-4 text-[#14181f]" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <span className="font-display font-bold text-sm text-amber-50 block truncate">
                WorldCup Predictor
              </span>
              <span className="text-[10px] text-amber-200/60 uppercase tracking-wider">
                Premium Analytics
              </span>
            </div>
          )}
        </Link>
        {!mobile && (
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className="text-slate-500 hover:text-slate-200 p-1"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          >
            <ChevronLeft className={`w-4 h-4 transition-transform ${collapsed ? "rotate-180" : ""}`} />
          </button>
        )}
      </div>

      <SidebarNav
        sections={sections}
        collapsed={collapsed}
        mobile={mobile}
        onNavigate={() => setSidebarOpen(false)}
        onLogout={() => logout(true)}
        variant="terminal"
      />
    </div>
  );

  return (
    <div className="min-h-screen flex bg-[#faf8f4] relative theme-pro-analytics theme-wc-premium">
      <aside
        className={`hidden lg:flex flex-col border-r border-[#2a3140] transition-all duration-300 relative z-10 ${
          collapsed ? "w-[72px]" : "w-64"
        }`}
      >
        <SidebarShell />
      </aside>

      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={() => setSidebarOpen(false)}
          />
          <aside className="relative w-72 h-full border-r border-[#2a3140] shadow-2xl">
            <SidebarShell mobile />
          </aside>
        </div>
      )}

      <div className="flex-1 flex flex-col min-h-screen relative z-10">
        <header className="h-14 border-b border-amber-200/60 bg-white/95 backdrop-blur-xl flex items-center justify-between px-4 lg:px-6 sticky top-0 z-40">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              className="lg:hidden text-slate-800"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-slate-900 truncate">{pageTitle}</p>
              <p className="text-[10px] text-amber-800/60 hidden sm:block truncate">
                {pageMeta.breadcrumbs?.map((b) => b.label).join(" · ") || "Football prediction intelligence"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 sm:gap-3">
            <QuotaChip />
            <AppVersionBadge user={user} />
            <LivePulse className="hidden sm:inline-flex" />
            <Link to="/notifications" className="relative p-2 rounded-lg hover:bg-white/5">
              <Bell className="w-5 h-5 text-slate-400 hover:text-slate-100" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-amber-400 rounded-full" />
            </Link>
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-6 overflow-y-auto bg-[#faf8f4]">
          <EmailVerificationBanner />
          <RouteErrorBoundary resetKey={location.pathname} label="dashboard-outlet" title="Page error" showDetail>
            <Outlet />
          </RouteErrorBoundary>
        </main>
      </div>
    </div>
  );
}
