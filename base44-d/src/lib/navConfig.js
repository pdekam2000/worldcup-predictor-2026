import {
  LayoutDashboard,
  Trophy,
  Globe2,
  Sparkles,
  BookOpen,
  Timer,
  CreditCard,
  Settings,
  Shield,
  Eye,
  Star,
  Server,
  Activity,
  Award,
  GitCompare,
  Cpu,
  FlaskConical,
  Beaker,
  Layers,
  Ticket,
} from "lucide-react";

/** Phase 62/64 — unified navigation architecture */

export const MAIN_NAV_SECTION = {
  id: "main",
  label: "Main",
  items: [
    { label: "Dashboard", path: "/dashboard", icon: LayoutDashboard },
    { label: "Match Center", path: "/matches", icon: Trophy },
    { label: "Combo Tips", path: "/combo-tips", icon: Ticket },
    { label: "World Cup", path: "/world-cup", icon: Globe2 },
    { label: "Predictions", path: "/dashboard", icon: Sparkles, matchPath: "/prediction" },
    { label: "Goal Timing", path: "/goal-timing/dashboard", icon: Timer },
    { label: "Research Highlights", path: "/research/highlights", icon: BookOpen },
    { label: "Subscription", path: "/subscription", icon: CreditCard },
    { label: "Settings", path: "/settings", icon: Settings },
  ],
};

export const INTELLIGENCE_NAV_SECTION = {
  id: "intelligence",
  label: "Intelligence",
  items: [
    { label: "Accuracy Center", path: "/accuracy", icon: Activity },
    { label: "Performance Center", path: "/admin/performance", icon: Award, roles: ["super_admin"] },
  ],
};

export const ACCOUNT_NAV_SECTION = {
  id: "account",
  label: "Account",
  items: [],
};

export const ADMIN_NAV_SECTION = {
  id: "admin",
  label: "Command Center",
  items: [
    { label: "Admin Dashboard", path: "/admin", icon: Shield, roles: ["admin", "super_admin"] },
    { label: "Elite Shadow", path: "/admin/elite-shadow", icon: Eye, roles: ["super_admin"] },
    { label: "Shadow vs Production", path: "/admin/elite-shadow", icon: GitCompare, roles: ["super_admin"], matchPath: "/admin/elite-shadow" },
    { label: "Performance Certification", path: "/admin/performance", icon: Award, roles: ["super_admin"] },
    { label: "System Health", path: "/api-settings", icon: Server, roles: ["admin", "super_admin"] },
    { label: "Super Admin", path: "/super-admin", icon: Star, roles: ["super_admin"] },
  ],
};

/** @deprecated use buildNavSections */
export const NAV_SECTIONS = [MAIN_NAV_SECTION, INTELLIGENCE_NAV_SECTION, ACCOUNT_NAV_SECTION];

export const LEGACY_USER_ROUTES = {
  archive: "/history",
  accuracy: "/analytics/accuracy",
};

export const LEGACY_ROUTE_ALIASES = {
  "/accuracy": "/analytics/accuracy",
  "/account/settings": "/settings",
};

function itemVisible(item, { isAdmin, isSuperAdmin }) {
  const roles = item.roles;
  if (!roles?.length) return true;
  if (roles.includes("super_admin") && isSuperAdmin) return true;
  if (roles.includes("admin") && isAdmin) return true;
  return false;
}

function dedupeItems(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item.matchPath || item.path;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function buildNavSections({ user, showEliteWcPublic = false } = {}) {
  const role = user?.role;
  const isOwner = role === "owner";
  const isSuperAdmin = role === "super_admin" && !isOwner;
  const isAdmin = (role === "admin" || isSuperAdmin) && !isOwner;
  const ctx = { isAdmin, isSuperAdmin };

  const mainItems = MAIN_NAV_SECTION.items.filter((item) => itemVisible(item, ctx));

  const intelligenceItems = INTELLIGENCE_NAV_SECTION.items.filter((item) => itemVisible(item, ctx));
  const accountItems = ACCOUNT_NAV_SECTION.items.filter((item) => itemVisible(item, ctx));

  const sections = [
    { ...MAIN_NAV_SECTION, items: dedupeItems(mainItems) },
    { ...INTELLIGENCE_NAV_SECTION, items: dedupeItems(intelligenceItems) },
  ];

  if (accountItems.length) {
    sections.push({ ...ACCOUNT_NAV_SECTION, items: accountItems });
  }

  const adminItems = ADMIN_NAV_SECTION.items.filter((item) => itemVisible(item, ctx));
  if (adminItems.length && !isOwner) {
    sections.push({ ...ADMIN_NAV_SECTION, items: dedupeItems(adminItems) });
  }

  return sections;
}

export function flattenNavItems(sections) {
  return (sections || []).flatMap((section) =>
    section.items.map((item) => ({ ...item, sectionLabel: section.label }))
  );
}

export function isNavItemActive(pathname, item) {
  const target = item.matchPath || item.path.split("?")[0];
  if (target === "/dashboard") {
    return pathname === "/dashboard" || pathname.startsWith("/prediction/");
  }
  if (target === "/matches" || target === "/world-cup") {
    return pathname === "/matches" || pathname.startsWith("/matches") || pathname === "/world-cup";
  }
  return pathname === target || pathname.startsWith(`${target}/`);
}

export function resolvePageMeta(pathname) {
  const normalized = LEGACY_ROUTE_ALIASES[pathname] || pathname;

  if (normalized.startsWith("/prediction/")) {
    return {
      title: "Prediction",
      breadcrumbs: [{ label: "Matches", path: "/matches" }, { label: "Prediction" }],
    };
  }

  if (normalized.startsWith("/goal-timing/")) {
    const segment = normalized.replace("/goal-timing/", "").split("/")[0] || "dashboard";
    const labels = {
      dashboard: "Goal Timing",
      picks: "Today's Picks",
      history: "History",
      accuracy: "Accuracy",
      performance: "Performance",
      backtest: "Backtest",
      insights: "Model Insights",
    };
    const label = labels[segment] || "Goal Timing";
    return {
      title: label,
      breadcrumbs: [{ label: "Intelligence" }, { label, path: `/goal-timing/${segment}` }],
    };
  }

  const allItems = flattenNavItems([
    MAIN_NAV_SECTION,
    INTELLIGENCE_NAV_SECTION,
    ACCOUNT_NAV_SECTION,
    ADMIN_NAV_SECTION,
  ]);
  const match = allItems.find((item) => isNavItemActive(normalized, item));
  if (match) {
    return {
      title: match.label,
      breadcrumbs: [{ label: match.sectionLabel || "App" }, { label: match.label, path: match.path }],
    };
  }

  return { title: "Dashboard", breadcrumbs: [{ label: "Main" }, { label: "Dashboard" }] };
}

/** @deprecated */
export function buildAdminSection({ showAdminNav, showSuperAdminNav, showApiSettings }) {
  const items = ADMIN_NAV_SECTION.items.filter((item) => {
    if (item.path === "/super-admin") return showSuperAdminNav;
    if (item.path === "/admin/elite-shadow") return showSuperAdminNav;
    if (item.path === "/elite/world-cup") return showSuperAdminNav;
    if (item.path === "/admin/performance") return showSuperAdminNav;
    if (item.path === "/api-settings") return showApiSettings;
    return showAdminNav;
  });
  if (!items.length) return null;
  return { ...ADMIN_NAV_SECTION, items };
}
