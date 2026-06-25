import React from "react";
import { Link } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import NotificationBell from "./NotificationBell";
import QuotaChip from "./QuotaChip";

export default function PageHeader({ title, breadcrumbs = [] }) {
  return (
    <header className="h-14 border-b border-white/10 glass flex items-center justify-between px-4 lg:px-6 sticky top-0 z-40 gap-4">
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <nav className="flex items-center gap-1 text-sm min-w-0 overflow-hidden" aria-label="Breadcrumb">
          {breadcrumbs.map((crumb, index) => {
            const isLast = index === breadcrumbs.length - 1;
            return (
              <React.Fragment key={`${crumb.label}-${index}`}>
                {index > 0 && (
                  <ChevronRight className="w-3.5 h-3.5 text-muted-foreground/50 flex-shrink-0" />
                )}
                {crumb.path && !isLast ? (
                  <Link
                    to={crumb.path}
                    className="text-muted-foreground hover:text-foreground truncate transition-colors"
                  >
                    {crumb.label}
                  </Link>
                ) : (
                  <span
                    className={`truncate ${isLast ? "font-medium text-foreground" : "text-muted-foreground"}`}
                  >
                    {crumb.label}
                  </span>
                )}
              </React.Fragment>
            );
          })}
          {!breadcrumbs.length && title && (
            <span className="font-medium text-foreground truncate">{title}</span>
          )}
        </nav>
      </div>
      <div className="flex items-center gap-2 flex-shrink-0">
        <QuotaChip />
        <NotificationBell />
      </div>
    </header>
  );
}
