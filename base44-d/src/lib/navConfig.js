import {
  LayoutDashboard,
  Trophy,
  Layers,
  Target,
  Sparkles,
  Timer,
  TrendingDown,
  Gem,
  Archive,
  Activity,
  Users,
  UserCircle,
  Flag,
  List,
  Server,
  Shield,
  Eye,
  Beaker,
  CreditCard,
  User,
  Settings,
  BarChart3,
  TrendingUp,
} from "lucide-react";

/** Phase 61 — OddAlerts-inspired professional navigation */

export const MAIN_NAV_SECTION = {
  id: "main",
  label: "Main",
  items: [
    { label: "Hub", path: "/dashboard", icon: LayoutDashboard },
    { label: "Match Center", path: "/matches", icon: Trophy, matchPath: "/matches" },
    { label: "Best Tips", path: "/best-tips", icon: Target },
    { label: "Daily Picks", path: "/daily-picks", icon: TrendingUp },
    { label: "Combo Builder", path: "/combo-builder", icon: Layers, matchPath: "/combo-tips" },
  ],
};

export const PREDICTIONS_NAV_SECTION = {
  id: "predictions",
  label: "Predictions",
  items: [
    { label: "Unified Predictions", path: "/unified-predictions", icon: Sparkles, roles: ["super_admin"] },
    { label: "Goal Intelligence", path: "/goal-timing/dashboard", icon: Timer, matchPath: "/goal-timing", roles: ["super_admin"] },
    { label: "Results", path: "/results", icon: Activity, dedupeKey: "results-center" },
    { label: "Odds Movement", path: "/matches?filter=odds", icon: TrendingDown, dedupeKey: "odds-movement" },
    { label: "Value Bets", path: "/best-tips?filter=value", icon: Gem, dedupeKey: "value-bets" },
    { label: "Prediction Archive", path: "/archive", icon: Archive },
    { label: "Accuracy Center", path: "/accuracy", icon: BarChart3, dedupeKey: "accuracy-center" },
  ],
};

export const DATA_NAV_SECTION = {
  id: "data",
  label: "Data",
  items: [
    { label: "Teams", path: "/matches", icon: Users, dedupeKey: "data-teams" },
    { label: "Players", path: "/goal-timing/insights", icon: UserCircle, dedupeKey: "data-players" },
    { label: "Referees", path: "/api-settings", icon: Flag, dedupeKey: "data-referees" },
    { label: "Standings", path: "/matches?competition=world_cup_2026", icon: BarChart3, dedupeKey: "data-standings" },
    { label: "Leagues", path: "/matches", icon: List, dedupeKey: "data-leagues" },
    { label: "API / Data Health", path: "/api-settings", icon: Server },
  ],
};

export const ACCOUNT_NAV_SECTION = {
  id: "account",
  label: "Account",
  items: [
    { label: "Subscription", path: "/subscription", icon: CreditCard },
    { label: "Profile", path: "/settings", icon: User, matchPath: "/settings", dedupeKey: "account-profile" },
    { label: "Settings", path: "/settings", icon: Settings, dedupeKey: "account-settings" },
  ],
};

export const ADMIN_NAV_SECTION = {
  id: "admin",
  label: "Admin",
  items: [
    { label: "Admin Dashboard", path: "/admin", icon: Shield, roles: ["admin", "super_admin"] },
    { label: "Elite Shadow Preview", path: "/admin/elite-shadow", icon: Eye, roles: ["super_admin"] },
    { label: "Learning Center", path: "/admin/learning", icon: Beaker, roles: ["super_admin"] },
    { label: "System Health", path: "/api-settings", icon: Server, roles: ["admin", "super_admin"], dedupeKey: "admin-health" },
  ],
};

/** @deprecated */
export const INTELLIGENCE_NAV_SECTION = PREDICTIONS_NAV_SECTION;

export const LEGACY_USER_ROUTES = {
  archive: "/archive",
  accuracy: "/analytics/accuracy",
  comboTips: "/combo-tips",
  classicPredictions: "/dashboard",
  goalTiming: "/goal-timing/dashboard",
};

export const LEGACY_ROUTE_ALIASES = {
  "/accuracy": "/analytics/accuracy",
  "/account/settings": "/settings",
  "/combo-builder": "/combo-tips",
  "/hub": "/dashboard",
};

function itemVisible(item, { isAdmin, isSuperAdmin }) {
  if (item.hidden) return false;
  const roles = item.roles;
  if (!roles?.length) return true;
  if (roles.includes("super_admin") && isSuperAdmin) return true;
  if (roles.includes("admin") && isAdmin) return true;
  return false;
}

function dedupeItems(items) {
  const seen = new Set();
  return items.filter((item) => {
    const key = item.dedupeKey || item.matchPath || item.path.split("?")[0];
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function buildNavSections({ user } = {}) {
  const role = user?.role;
  const isOwner = role === "owner";
  const isSuperAdmin = role === "super_admin" && !isOwner;
  const isAdmin = (role === "admin" || isSuperAdmin) && !isOwner;
  const ctx = { isAdmin, isSuperAdmin };

  const sections = [
    { ...MAIN_NAV_SECTION, items: dedupeItems(MAIN_NAV_SECTION.items.filter((i) => itemVisible(i, ctx))) },
    {
      ...PREDICTIONS_NAV_SECTION,
      items: dedupeItems(PREDICTIONS_NAV_SECTION.items.filter((i) => itemVisible(i, ctx))),
    },
    { ...DATA_NAV_SECTION, items: dedupeItems(DATA_NAV_SECTION.items.filter((i) => itemVisible(i, ctx))) },
    {
      ...ACCOUNT_NAV_SECTION,
      items: ACCOUNT_NAV_SECTION.items.filter((i) => itemVisible(i, ctx)),
    },
  ];

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
  const search = item.path.includes("?") ? item.path.split("?")[1] : null;

  if (target === "/dashboard") {
    return pathname === "/dashboard" || pathname === "/hub";
  }
  if (target === "/matches" || target === "/world-cup") {
    if (pathname !== "/matches" && !pathname.startsWith("/matches/")) return false;
    if (search && typeof window !== "undefined") {
      return window.location.search.includes(search);
    }
    return pathname === "/matches" || pathname.startsWith("/matches/");
  }
  if (target === "/combo-tips") {
    return pathname === "/combo-tips" || pathname === "/combo-builder";
  }
  if (target === "/goal-timing") {
    return pathname.startsWith("/goal-timing");
  }
  if (target === "/best-tips") {
    return pathname === "/best-tips";
  }
  if (target === "/unified-predictions") {
    return pathname === "/unified-predictions";
  }
  if (target === "/settings") {
    return pathname === "/settings";
  }
  if (target === "/prediction") {
    return pathname.startsWith("/prediction/");
  }
  return pathname === target || pathname.startsWith(`${target}/`);
}

export function resolvePageMeta(pathname) {
  const normalized = LEGACY_ROUTE_ALIASES[pathname] || pathname;

  if (normalized.startsWith("/prediction/")) {
    return {
      title: "Unified Prediction Detail",
      breadcrumbs: [{ label: "Predictions" }, { label: "Detail" }],
    };
  }

  if (normalized.startsWith("/goal-timing/")) {
    const segment = normalized.replace("/goal-timing/", "").split("/")[0] || "dashboard";
    const labels = {
      dashboard: "Goal Intelligence",
      picks: "Goal Timing Picks",
      history: "History",
      accuracy: "Accuracy",
      performance: "Performance",
      backtest: "Backtest",
      insights: "Model Insights",
    };
    return {
      title: labels[segment] || "Goal Intelligence",
      breadcrumbs: [{ label: "Predictions" }, { label: labels[segment] || segment }],
    };
  }

  const allItems = flattenNavItems([
    MAIN_NAV_SECTION,
    PREDICTIONS_NAV_SECTION,
    DATA_NAV_SECTION,
    ACCOUNT_NAV_SECTION,
    ADMIN_NAV_SECTION,
  ]);
  const match = allItems.find((item) => isNavItemActive(normalized, item));
  if (match) {
    return {
      title: match.label,
      breadcrumbs: [{ label: match.sectionLabel || "App" }, { label: match.label }],
    };
  }

  return { title: "Hub", breadcrumbs: [{ label: "Main" }, { label: "Hub" }] };
}

/** @deprecated */
export const NAV_SECTIONS = [MAIN_NAV_SECTION, PREDICTIONS_NAV_SECTION, ACCOUNT_NAV_SECTION];

/** @deprecated */
export function buildAdminSection() {
  return null;
}
