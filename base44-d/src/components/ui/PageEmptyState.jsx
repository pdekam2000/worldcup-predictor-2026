import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export default function PageEmptyState({
  icon: Icon,
  title,
  description,
  actionLabel,
  actionTo,
  onAction,
  className = "",
}) {
  return (
    <div className={`wc-premium-card p-8 text-center ${className}`}>
      {Icon && <Icon className="w-10 h-10 text-amber-600/70 mx-auto mb-3" />}
      <p className="font-semibold text-slate-900">{title}</p>
      {description && <p className="text-sm text-slate-600 mt-2 max-w-md mx-auto">{description}</p>}
      {actionLabel && actionTo && (
        <Button asChild className="mt-4" variant="outline">
          <Link to={actionTo}>{actionLabel}</Link>
        </Button>
      )}
      {actionLabel && onAction && !actionTo && (
        <Button type="button" className="mt-4" variant="outline" onClick={onAction}>
          {actionLabel}
        </Button>
      )}
    </div>
  );
}
