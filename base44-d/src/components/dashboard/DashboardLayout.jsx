import React, { useState } from "react";
import { Outlet, Link, useLocation } from "react-router-dom";
import { base44 } from "@/api/base44Client";
import {
  LayoutDashboard, BarChart3, CreditCard, Bell, Settings,
  Zap, Menu, LogOut, ChevronLeft, Shield, Trophy, History,
  Heart, BellRing, Server, Star
} from "lucide-react";
import { Button } from "@/components/ui/button";
import LanguageSwitcher from "@/components/LanguageSwitcher";

const navItems = [
  { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
  { label: "Match Center", path: "/matches", icon: Trophy },
  { label: "Accuracy", path: "/accuracy", icon: BarChart3 },
  { label: "History", path: "/history", icon: History },
  { label: "Favorites", path: "/favorites", icon: Heart },
  { label: "Alerts", path: "/alerts", icon: BellRing },
  { label: "Subscription", path: "/subscription", icon: CreditCard },
  { label: "Notifications", path: "/notifications", icon: Bell },
  { label: "Settings", path: "/settings", icon: Settings },
];

const adminItems = [
  { label: "Admin Panel", path: "/admin", icon: Shield },
  { label: "Super Admin", path: "/super-admin", icon: Star },
  { label: "API Settings", path: "/api-settings", icon: Server },
];

export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [collapsed, setCollapsed] = useState(false);
  const location = useLocation();

  const handleLogout = () => {
    base44.auth.logout("/");
  };

  const SidebarContent = ({ mobile = false }) => (
    <div className="flex flex-col h-full">
      <div className="p-4 flex items-center justify-between border-b border-white/10">
        <Link to="/dashboard" className="flex items-center gap-2" onClick={() => mobile && setSidebarOpen(false)}>
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center flex-shrink-0">
            <Zap className="w-4 h-4 text-primary-foreground" />
          </div>
          {!collapsed && <span className="font-display font-bold text-sm">WCP Pro</span>}
        </Link>
        {!mobile && (
          <button onClick={() => setCollapsed(!collapsed)} className="text-muted-foreground hover:text-foreground">
            <ChevronLeft className={`w-4 h-4 transition-transform ${collapsed ? "rotate-180" : ""}`} />
          </button>
        )}
      </div>

      <nav className="flex-1 p-3 space-y-1">
        {navItems.map((item) => {
          const active = location.pathname === item.path || (item.path !== "/dashboard" && location.pathname.startsWith(item.path));
          return (
            <Link
              key={item.path}
              to={item.path}
              onClick={() => mobile && setSidebarOpen(false)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                active ? "bg-primary/15 text-primary" : "text-muted-foreground hover:text-foreground hover:bg-white/5"
              }`}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {!collapsed && item.label}
            </Link>
          );
        })}
        <div className="border-t border-white/10 my-3" />
        {adminItems.map((item) => {
          const active = location.pathname.startsWith(item.path);
          return (
            <Link
              key={item.path}
              to={item.path}
              onClick={() => mobile && setSidebarOpen(false)}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all ${
                active ? "bg-accent/15 text-accent" : "text-muted-foreground hover:text-foreground hover:bg-white/5"
              }`}
            >
              <item.icon className="w-5 h-5 flex-shrink-0" />
              {!collapsed && item.label}
            </Link>
          );
        })}
      </nav>

      <div className="p-3 border-t border-white/10 space-y-2">
        {!collapsed && <div className="px-1"><LanguageSwitcher /></div>}
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium text-muted-foreground hover:text-foreground hover:bg-white/5 w-full"
        >
          <LogOut className="w-5 h-5 flex-shrink-0" />
          {!collapsed && "Logout"}
        </button>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background flex">
      {/* Desktop sidebar */}
      <aside className={`hidden lg:flex flex-col border-r border-white/10 bg-card/50 backdrop-blur-xl transition-all duration-300 ${collapsed ? "w-16" : "w-60"}`}>
        <SidebarContent />
      </aside>

      {/* Mobile overlay */}
      {sidebarOpen && (
        <div className="lg:hidden fixed inset-0 z-50">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSidebarOpen(false)} />
          <aside className="relative w-64 h-full bg-card border-r border-white/10">
            <SidebarContent mobile />
          </aside>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col min-h-screen">
        <header className="h-14 border-b border-white/10 glass flex items-center justify-between px-4 lg:px-6 sticky top-0 z-40">
          <button className="lg:hidden" onClick={() => setSidebarOpen(true)}>
            <Menu className="w-5 h-5" />
          </button>
          <div className="text-sm font-medium text-muted-foreground">
            {navItems.find(n => location.pathname === n.path || (n.path !== "/dashboard" && location.pathname.startsWith(n.path)))?.label ||
             adminItems.find(n => location.pathname.startsWith(n.path))?.label || "Dashboard"}
          </div>
          <Link to="/notifications" className="relative">
            <Bell className="w-5 h-5 text-muted-foreground hover:text-foreground transition-colors" />
            <span className="absolute -top-1 -right-1 w-2 h-2 bg-primary rounded-full" />
          </Link>
        </header>
        <main className="flex-1 p-4 lg:p-6 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}