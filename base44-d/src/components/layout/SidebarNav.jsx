import React from "react";
import { Link, useLocation } from "react-router-dom";
import { LogOut } from "lucide-react";
import LanguageSwitcher from "@/components/LanguageSwitcher";
import { isNavItemActive } from "@/lib/navConfig";
import { cn } from "@/lib/utils";

export default function SidebarNav({
  sections,
  collapsed,
  mobile = false,
  onNavigate,
  onLogout,
  variant = "default",
}) {
  const location = useLocation();
  const terminal = variant === "terminal";

  const handleClick = () => {
    if (mobile && onNavigate) onNavigate();
  };

  return (
    <>
      <nav className="flex-1 p-3 space-y-4 overflow-y-auto">
        {sections.map((section) => (
          <div key={section.id}>
            {!collapsed && (
              <p
                className={cn(
                  "px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em]",
                  terminal ? "text-[#94A3B8]/80" : "text-muted-foreground/70"
                )}
              >
                {section.label}
              </p>
            )}
            {collapsed && section.items.length > 0 && (
              <div className={cn("border-t my-2 first:border-0 first:mt-0", terminal ? "border-white/[0.06]" : "border-border")} />
            )}
            <div className="space-y-0.5">
              {section.items.map((item) => {
                const active = isNavItemActive(location.pathname, item);
                const Icon = item.icon;
                const isAdmin = section.id === "admin";
                return (
                  <Link
                    key={`${section.id}-${item.path}-${item.label}`}
                    to={item.path}
                    onClick={handleClick}
                    title={collapsed ? item.label : undefined}
                    className={cn(
                      "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all border",
                      active
                        ? isAdmin
                          ? "bg-[#FFD166]/12 text-[#FFD166] border-[#FFD166]/20"
                          : "bg-[#00E676]/12 text-[#00E676] border-[#00E676]/20"
                        : terminal
                          ? "text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-white/[0.04] border-transparent"
                          : "text-muted-foreground hover:text-foreground hover:bg-muted/60 border-transparent"
                    )}
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

      <div className={cn("p-3 border-t space-y-2", terminal ? "border-white/[0.06]" : "border-border")}>
        {!collapsed && (
          <div className="px-1">
            <LanguageSwitcher />
          </div>
        )}
        <button
          type="button"
          onClick={onLogout}
          className={cn(
            "flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium w-full",
            terminal
              ? "text-[#94A3B8] hover:text-[#F8FAFC] hover:bg-white/[0.04]"
              : "text-muted-foreground hover:text-foreground hover:bg-white/5"
          )}
        >
          <LogOut className="w-[18px] h-[18px] flex-shrink-0" />
          {!collapsed && "Logout"}
        </button>
      </div>
    </>
  );
}
