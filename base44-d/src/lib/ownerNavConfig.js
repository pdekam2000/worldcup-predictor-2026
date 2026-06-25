import {
  LayoutDashboard,
  Activity,
  Eye,
  FlaskConical,
  Users,
  Server,
  FileText,
  Settings,
  BookOpen,
  Award,
  Cpu,
  Bell,
  Database,
  Zap,
} from "lucide-react";

/** Owner-only navigation — separate from user dashboard. */

export const OWNER_NAV_SECTIONS = [
  {
    id: "command",
    label: "Command Center",
    items: [
      { label: "Overview", path: "/owner", icon: LayoutDashboard, exact: true },
      { label: "Monitoring", path: "/owner/monitoring", icon: Cpu },
      { label: "Notifications", path: "/owner/notifications", icon: Bell },
    ],
  },
  {
    id: "intelligence",
    label: "Intelligence",
    items: [
      { label: "Research", path: "/research/highlights", icon: BookOpen },
      { label: "Performance", path: "/owner/performance", icon: Award },
      { label: "Elite Shadow", path: "/admin/elite-shadow", icon: Eye },
      { label: "Goal Timing", path: "/goal-timing/dashboard", icon: Zap },
    ],
  },
  {
    id: "runtime",
    label: "Autonomous",
    items: [
      { label: "Runtime Control", path: "/owner/autonomous", icon: FlaskConical },
      { label: "System Health", path: "/owner/health", icon: Server },
      { label: "API Usage", path: "/owner/api-usage", icon: Activity },
    ],
  },
  {
    id: "platform",
    label: "Platform",
    items: [
      { label: "Users", path: "/admin", icon: Users },
      { label: "Database", path: "/owner/database", icon: Database },
      { label: "Logs", path: "/owner/logs", icon: FileText },
      { label: "Settings", path: "/settings", icon: Settings },
    ],
  },
];

export function isOwnerNavActive(pathname, item) {
  if (item.exact) return pathname === item.path;
  return pathname === item.path || pathname.startsWith(`${item.path}/`);
}
