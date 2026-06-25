import React from "react";
import { cn } from "@/lib/utils";
import TeamBadge from "@/components/match/TeamBadge";

export function IntelligenceCard({ children, className = "", glow = false }) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/[0.06] bg-[#101827]/90 backdrop-blur-xl p-4 sm:p-5 shadow-[0_8px_32px_rgba(0,0,0,0.35)]",
        glow && "terminal-card-glow",
        className
      )}
    >
      {children}
    </div>
  );
}

export function LoadingSkeleton({ lines = 3, className = "" }) {
  return (
    <div className={cn("space-y-3 animate-pulse", className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="h-4 rounded-lg bg-white/[0.06]" style={{ width: `${90 - i * 12}%` }} />
      ))}
    </div>
  );
}

export function EmptyState({ title, message, action }) {
  return (
    <IntelligenceCard className="text-center py-10">
      <p className="text-sm font-semibold text-[#F8FAFC]">{title}</p>
      {message && <p className="text-sm text-[#94A3B8] mt-2 max-w-md mx-auto">{message}</p>}
      {action && <div className="mt-4">{action}</div>}
    </IntelligenceCard>
  );
}

export function ErrorState({ message, onRetry, type = "error" }) {
  const tones = {
    auth_required: "border-yellow-500/30 bg-yellow-500/5 text-yellow-100",
    forbidden: "border-orange-500/30 bg-orange-500/5 text-orange-100",
    not_found: "border-slate-500/30 bg-slate-500/5 text-slate-200",
    server_error: "border-red-500/30 bg-red-500/5 text-red-100",
    error: "border-red-500/30 bg-red-500/5 text-red-100",
  };
  return (
    <IntelligenceCard className={cn("border", tones[type] || tones.error)}>
      <p className="text-sm">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 text-xs font-semibold uppercase tracking-wide text-[#00E676] hover:underline"
        >
          Retry
        </button>
      )}
    </IntelligenceCard>
  );
}

export function FixtureCard({
  homeTeam,
  awayTeam,
  kickoff,
  competition,
  status,
  homeLogo,
  awayLogo,
  children,
  className = "",
}) {
  return (
    <IntelligenceCard className={cn("space-y-4", className)} glow>
      <div className="flex items-center justify-between gap-2 text-[10px] uppercase tracking-wider text-[#94A3B8]">
        <span className="truncate">{competition || "Fixture"}</span>
        {status && <StatusBadge status={status} />}
      </div>
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="text-center space-y-2">
          <TeamBadge teamName={homeTeam} logoUrl={homeLogo} size="md" />
          <p className="text-sm font-semibold text-[#F8FAFC] truncate">{homeTeam}</p>
        </div>
        <div className="text-center px-2">
          <p className="text-[10px] text-[#94A3B8] uppercase">vs</p>
          {kickoff && <p className="text-xs text-[#00E676] mt-1 font-mono">{kickoff}</p>}
        </div>
        <div className="text-center space-y-2">
          <TeamBadge teamName={awayTeam} logoUrl={awayLogo} size="md" />
          <p className="text-sm font-semibold text-[#F8FAFC] truncate">{awayTeam}</p>
        </div>
      </div>
      {children}
    </IntelligenceCard>
  );
}

export function MarketBadge({ market }) {
  const label = String(market || "").replace(/_/g, " ").toUpperCase();
  return (
    <span className="terminal-chip border-[#3B82F6]/30 bg-[#3B82F6]/10 text-[#93C5FD]">
      {label || "MARKET"}
    </span>
  );
}

export function ConfidenceTierBadge({ tier }) {
  if (!tier) return null;
  const tone =
    tier === "elite"
      ? "border-[#FFD166]/30 bg-[#FFD166]/10 text-[#FFD166]"
      : "border-[#00E676]/30 bg-[#00E676]/10 text-[#00E676]";
  return <span className={cn("terminal-chip border", tone)}>{String(tier).toUpperCase()}</span>;
}

export function StatusBadge({ status }) {
  const s = String(status || "").toLowerCase();
  const tone =
    s === "live"
      ? "border-[#00E676]/30 bg-[#00E676]/10 text-[#00E676]"
      : s === "finished" || s === "ft"
        ? "border-slate-500/30 bg-slate-500/10 text-slate-300"
        : "border-[#22D3EE]/30 bg-[#22D3EE]/10 text-[#67E8F9]";
  return <span className={cn("terminal-chip border", tone)}>{status || "—"}</span>;
}

export { TeamBadge };
