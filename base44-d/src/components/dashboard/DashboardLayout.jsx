import React, { useState, useMemo } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import { Menu, ChevronLeft, Bell, Zap } from "lucide-react";
import SidebarNav from "@/components/layout/SidebarNav";
import { buildNavSections, resolvePageMeta, isNavItemActive } from "@/lib/navConfig";

function LivePulse({ className = "" }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wider text-[#00E676] ${className}`}
    >
      <span className="w-2 h-2 rounded-full bg-[#00E676] animate-live-pulse" />
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
  const pageTitle = activeItem?.label || pageMeta.title || "Dashboard";

  const shellClass = "bg-[#0a0f1a] border-white/[0.06]";

  const SidebarShell = ({ mobile = false }) => (
    <div className={`flex flex-col h-full ${shellClass}`}>
      <div className="p-4 flex items-center justify-between border-b border-white/[0.06]">
        <Link
          to="/dashboard"
          className="flex items-center gap-2.5 min-w-0"
          onClick={() => mobile && setSidebarOpen(false)}
        >
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#00E676] to-[#3B82F6] flex items-center justify-center flex-shrink-0 shadow-lg shadow-[#00E676]/20">
            <Zap className="w-4 h-4 text-[#070B14]" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <span className="font-display font-bold text-sm text-[#F8FAFC] block truncate">
                WCP Intelligence
              </span>
              <span className="text-[10px] text-[#94A3B8] uppercase tracking-wider">
                Premium Terminal
              </span>
            </div>
          )}
        </Link>
        {!mobile && (
          <button
            type="button"
            onClick={() => setCollapsed(!collapsed)}
            className="text-[#94A3B8] hover:text-[#F8FAFC] p-1"
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
    <div className="min-h-screen flex bg-[#070B14] relative">
      <div className="fixed inset-0 scanline-overlay pointer-events-none z-0" aria-hidden />

      <aside
        className={`hidden lg:flex flex-col border-r border-white/[0.06] transition-all duration-300 relative z-10 ${
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
          <aside className="relative w-72 h-full border-r border-white/[0.06] shadow-2xl">
            <SidebarShell mobile />
          </aside>
        </div>
      )}

      <div className="flex-1 flex flex-col min-h-screen relative z-10">
        <header className="h-14 border-b border-white/[0.06] bg-[#101827]/80 backdrop-blur-xl flex items-center justify-between px-4 lg:px-6 sticky top-0 z-40">
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              className="lg:hidden text-[#F8FAFC]"
              onClick={() => setSidebarOpen(true)}
              aria-label="Open menu"
            >
              <Menu className="w-5 h-5" />
            </button>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-[#F8FAFC] truncate">{pageTitle}</p>
              <p className="text-[10px] text-[#94A3B8] hidden sm:block truncate">
                {pageMeta.breadcrumbs?.map((b) => b.label).join(" · ") || "Football intelligence platform"}
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <LivePulse className="hidden sm:inline-flex" />
            <Link to="/notifications" className="relative p-2 rounded-lg hover:bg-white/5">
              <Bell className="w-5 h-5 text-[#94A3B8] hover:text-[#F8FAFC]" />
              <span className="absolute top-1.5 right-1.5 w-2 h-2 bg-[#00E676] rounded-full" />
            </Link>
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-6 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
