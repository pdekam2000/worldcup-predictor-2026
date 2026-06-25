import React from "react";
import { Link } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { cn } from "@/lib/utils";

export default function SectionHeader({
  eyebrow,
  title,
  subtitle,
  actionLabel,
  actionTo,
  onAction,
  className,
}) {
  return (
    <div className={cn("flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between", className)}>
      <div>
        {eyebrow && <p className="terminal-section-title mb-1">{eyebrow}</p>}
        <h2 className="text-xl sm:text-2xl font-display font-bold text-[#F8FAFC]">{title}</h2>
        {subtitle && <p className="text-sm text-[#94A3B8] mt-1 max-w-2xl">{subtitle}</p>}
      </div>
      {(actionLabel && actionTo) && (
        <Link
          to={actionTo}
          className="inline-flex items-center gap-1 text-sm font-medium text-[#00E676] hover:text-[#00E676]/80 transition-colors shrink-0"
        >
          {actionLabel}
          <ArrowRight className="w-4 h-4" />
        </Link>
      )}
      {actionLabel && onAction && !actionTo && (
        <button
          type="button"
          onClick={onAction}
          className="inline-flex items-center gap-1 text-sm font-medium text-[#00E676] hover:text-[#00E676]/80"
        >
          {actionLabel}
          <ArrowRight className="w-4 h-4" />
        </button>
      )}
    </div>
  );
}
