import React, { useState } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";
import { Menu, ChevronLeft, LogOut, Crown } from "lucide-react";
import { OWNER_NAV_SECTIONS, isOwnerNavActive } from "@/lib/ownerNavConfig";
import AppVersionBadge from "@/components/layout/AppVersionBadge";

function OwnerSidebar({ sections, collapsed, mobile, onNavigate, onLogout }) {
  const location = useLocation();
  return (
    <>
      <nav className="flex-1 p-3 space-y-4 overflow-y-auto">
        {sections.map((section) => (
          <div key={section.id}>
            {!collapsed && (
              <p className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#FFD166]/80">
                {section.label}
              </p>
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const active = isOwnerNavActive(location.pathname, item);
                const Icon = item.icon;
                return (
                  <Link
                    key={item.path}
                    to={item.path}
                    onClick={mobile ? onNavigate : undefined}
                    className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium border transition-all ${
                      active
                        ? "bg-[#FFD166]/12 text-[#FFD166] border-[#FFD166]/25"
                        : "text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-white/[0.04] border-transparent"
                    }`}
                  >
                    <Icon className="w-[18px] h-[18px] flex-shrink-0" />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
      <div className="p-3 border-t border-white/[0.06]">
        <button
          type="button"
          onClick={onLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-white/[0.04] w-full"
        >
          <LogOut className="w-[18px] h-[18px]" />
          {!collapsed && "Logout"}
        </button>
      </div>
    </>
  );
}

export default function OwnerLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();
  const { logout, user } = useAuth();

  const pageTitle =
    OWNER_NAV_SECTIONS.flatMap((s) => s.items).find((i) => isOwnerNavActive(location.pathname, i))
      ?.label || "Command Center";

  const Shell = ({ mobile = false }) => (
    <div className="flex flex-col h-full bg-[#08060f]">
      <div className="p-4 flex items-center justify-between border-b border-[#FFD166]/10">
        <Link to="/owner" className="flex items-center gap-2.5 min-w-0" onClick={() => mobile && setSidebarOpen(false)}>
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-[#FFD166] to-[#00E676] flex items-center justify-center shadow-lg shadow-[#FFD166]/20">
            <Crown className="w-4 h-4 text-[#08060f]" />
          </div>
          {!collapsed && (
            <div>
              <span className="font-display font-bold text-sm text-[#FFD166] block">Owner Command</span>
              <span className="text-[10px] text-[#94A3B8] uppercase tracking-wider">Enterprise</span>
            </div>
          )}
        </Link>
        {!mobile && (
          <button type="button" onClick={() => setCollapsed(!collapsed)} className="text-[#94A3B8] p-1">
            <ChevronLeft className={`w-4 h-4 transition-transform ${collapsed ? "rotate-180" : ""}`} />
          </button>
        )}
      </div>
      <OwnerSidebar
        sections={OWNER_NAV_SECTIONS}
        collapsed={collapsed}
        mobile={mobile}
        onNavigate={() => setSidebarOpen(false)}
        onLogout={() => logout(true)}
      />
    </div>
  );

  return (
    <div className="min-h-screen flex bg-[#070B14]">
      <aside className={`hidden lg:flex flex-col border-r border-[#FFD166]/10 ${collapsed ? "w-[72px]" : "w-64"}`}>
        <Shell />
      </aside>
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/70" onClick={() => setSidebarOpen(false)} />
          <aside className="relative w-72 h-full border-r border-[#FFD166]/10 shadow-2xl">
            <Shell mobile />
          </aside>
        </div>
      )}
      <div className="flex-1 flex flex-col min-h-screen">
        <header className="h-14 border-b border-white/[0.06] bg-[#101827]/90 backdrop-blur flex items-center justify-between px-4 sticky top-0 z-40">
          <div className="flex items-center gap-3">
            <button type="button" className="lg:hidden" onClick={() => setSidebarOpen(true)}>
              <Menu className="w-5 h-5" />
            </button>
            <div>
              <p className="text-sm font-semibold text-[#FFD166]">{pageTitle}</p>
              <p className="text-[10px] text-[#94A3B8]">Enterprise platform control</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <AppVersionBadge user={user} />
            <span className="intel-badge-gold hidden sm:inline-flex">OWNER</span>
          </div>
        </header>
        <main className="flex-1 p-4 lg:p-6 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
