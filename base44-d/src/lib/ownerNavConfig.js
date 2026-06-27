import {
  LayoutDashboard,
  Trophy,
  Globe2,
  Eye,
  FlaskConical,
  Award,
  BookOpen,
  Server,
  Users,
  Settings,
  Layers,
  Beaker,
  TrendingUp,
  DollarSign,
  CreditCard,
  Activity,
  Database,
} from "lucide-react";

/** Owner-only navigation — Phase 64 product owner upgrade */

export const OWNER_NAV_SECTIONS = [
  {
    id: "command",
    label: "Command",
    items: [
      { label: "Owner Command Center", path: "/owner", icon: LayoutDashboard, exact: true },
      { label: "Model Center", path: "/owner/model-center", icon: Layers },
      { label: "Research Lab", path: "/owner/research-lab", icon: Beaker },
      { label: "Promotion Center", path: "/owner/promotion-center", icon: TrendingUp },
      { label: "Betting Intelligence", path: "/owner/betting-intelligence", icon: DollarSign },
      { label: "Prefetch Coverage", path: "/owner/prefetch-coverage", icon: Database },
      { label: "PredOps Core", path: "/admin/predops", icon: Layers },
    ],
  },
  {
    id: "product",
    label: "Product View",
    items: [
      { label: "Match Center", path: "/matches", icon: Trophy },
      { label: "World Cup", path: "/world-cup", icon: Globe2 },
      { label: "Elite World Cup", path: "/elite/world-cup", icon: Globe2 },
      { label: "Research Highlights", path: "/research/highlights", icon: BookOpen },
    ],
  },
  {
    id: "runtime",
    label: "Autonomous",
    items: [
      { label: "Autonomous Runtime", path: "/owner/autonomous", icon: FlaskConical },
      { label: "Performance Center", path: "/owner/performance", icon: Award },
      { label: "Elite Shadow", path: "/admin/elite-shadow", icon: Eye },
    ],
  },
  {
    id: "platform",
    label: "Platform",
    items: [
      { label: "System Health", path: "/owner/health", icon: Server },
      { label: "Monitoring", path: "/owner/monitoring", icon: Activity },
      { label: "Users", path: "/admin", icon: Users },
      { label: "Subscription", path: "/subscription", icon: CreditCard },
      { label: "Settings", path: "/settings", icon: Settings },
    ],
  },
];

export function isOwnerNavActive(pathname, item) {
  if (item.exact) return pathname === item.path;
  if (item.path === "/matches") {
    return pathname === "/matches" || pathname.startsWith("/matches");
  }
  if (item.path === "/world-cup") {
    return pathname === "/world-cup" || (pathname === "/matches" && pathname.includes("worldcup"));
  }
  return pathname === item.path || pathname.startsWith(`${item.path}/`);
}
