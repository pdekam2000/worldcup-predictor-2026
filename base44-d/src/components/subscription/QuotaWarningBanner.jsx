import React from "react";
import { AlertTriangle, AlertCircle } from "lucide-react";

export default function QuotaWarningBanner({ warning, percent, remaining }) {
  if (!warning) return null;
  const config = {
    warning: {
      icon: AlertTriangle,
      className: "border-yellow-500/40 bg-yellow-500/10 text-yellow-200",
      title: "75% of monthly quota used",
      text: `${percent}% used · ${remaining} predictions remaining`,
    },
    critical: {
      icon: AlertCircle,
      className: "border-orange-500/40 bg-orange-500/10 text-orange-200",
      title: "90% of monthly quota used",
      text: `${percent}% used · ${remaining} remaining — consider upgrading`,
    },
    exhausted: {
      icon: AlertCircle,
      className: "border-red-500/40 bg-red-500/10 text-red-200",
      title: "Monthly quota exhausted",
      text: "Upgrade your plan or wait until the next billing cycle reset.",
    },
  };
  const c = config[warning] || config.warning;
  const Icon = c.icon;
  return (
    <div className={`rounded-xl p-4 border flex gap-3 items-start ${c.className}`}>
      <Icon className="w-5 h-5 flex-shrink-0 mt-0.5" />
      <div>
        <p className="font-semibold text-sm">{c.title}</p>
        <p className="text-xs opacity-90 mt-0.5">{c.text}</p>
      </div>
    </div>
  );
}
