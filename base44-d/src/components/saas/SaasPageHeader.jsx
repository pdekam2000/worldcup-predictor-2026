import React from "react";
import { cn } from "@/lib/utils";

export default function SaasPageHeader({ eyebrow, title, subtitle, className, actions }) {
  return (
    <div className={cn("flex flex-col sm:flex-row sm:items-end sm:justify-between gap-4", className)}>
      <div>
        {eyebrow && (
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-amber-600 mb-1">{eyebrow}</p>
        )}
        <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-slate-500 mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

export function SaasCard({ children, className, ...props }) {
  return (
    <div
      className={cn(
        "rounded-xl border border-slate-200 bg-white shadow-sm",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}
