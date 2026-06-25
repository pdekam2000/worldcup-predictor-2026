import React, { useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
import { getArchiveStatusConfig } from "@/lib/archiveStatus";

export default function ArchiveSection({ title, description, children, defaultOpen = true }) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className="glass rounded-2xl overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 p-5 text-left hover:bg-white/[0.02] transition-colors"
      >
        <div>
          <h2 className="text-lg font-display font-semibold">{title}</h2>
          {description && <p className="text-xs text-muted-foreground mt-0.5">{description}</p>}
        </div>
        {open ? <ChevronDown className="w-5 h-5 text-muted-foreground" /> : <ChevronRight className="w-5 h-5 text-muted-foreground" />}
      </button>
      {open && <div className="px-5 pb-5 pt-0 space-y-3 border-t border-white/5">{children}</div>}
    </section>
  );
}

export function MarketResultRow({ market }) {
  const status = market.result_status || "pending";
  const cfg = getArchiveStatusConfig(status);
  const Icon = cfg.icon;

  return (
    <div className="rounded-xl border border-white/10 bg-white/[0.02] p-4 space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="font-medium">{market.label}</div>
          <div className="text-sm text-muted-foreground mt-0.5">
            Pick: <span className="text-foreground">{market.display_selection || "—"}</span>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold shrink-0 ${cfg.badge}`}>
          <Icon className="w-3.5 h-3.5" />
          {market.withheld ? "Withheld" : cfg.label}
        </span>
      </div>

      {(market.confidence != null || Object.keys(market.probabilities || {}).length > 0) && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
          {market.confidence != null && (
            <div>
              <span className="text-muted-foreground">Confidence</span>
              <div className="font-medium tabular-nums">{Math.round(Number(market.confidence))}%</div>
            </div>
          )}
          {Object.entries(market.probabilities || {}).slice(0, 3).map(([k, v]) => (
            <div key={k}>
              <span className="text-muted-foreground">{k.replace(/_/g, " ")}</span>
              <div className="font-medium tabular-nums">{v != null ? `${Math.round(Number(v))}%` : "—"}</div>
            </div>
          ))}
        </div>
      )}

      {market.actual && (
        <p className="text-xs text-muted-foreground border-t border-white/5 pt-2">
          Actual: <span className="text-foreground">{market.actual}</span>
        </p>
      )}

      {market.eval_reason && <p className="text-xs text-muted-foreground">{market.eval_reason}</p>}

      {market.withheld && market.withheld_reason && (
        <p className="text-xs text-yellow-200/80 border-t border-white/5 pt-2">{market.withheld_reason}</p>
      )}
    </div>
  );
}

export function JsonBlock({ data }) {
  if (data == null) return null;
  return (
    <pre className="text-[11px] leading-relaxed overflow-x-auto rounded-lg bg-black/30 border border-white/10 p-3 text-muted-foreground">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}
