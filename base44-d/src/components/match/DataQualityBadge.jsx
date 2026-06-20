import React from "react";
import { Badge } from "@/components/ui/badge";
import { Database, AlertTriangle, Activity, TrendingUp, Clock } from "lucide-react";

const TIER_STYLES = {
  high: "bg-green-500/15 text-green-400 border-green-500/30",
  medium: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  low: "bg-red-500/15 text-red-400 border-red-500/30",
  unknown: "bg-white/5 text-muted-foreground border-white/10",
};

const TIER_LABELS = {
  high: "High data",
  medium: "Medium data",
  low: "Low data",
  unknown: "Data quality unknown",
};

export default function DataQualityBadge({ dataSignals, dataQualityPct = null, compact = false }) {
  const signals = dataSignals || {};
  const tier = signals.tier || "unknown";
  const pct = signals.data_quality_pct ?? dataQualityPct;

  if (compact && tier === "unknown" && pct == null) return null;

  return (
    <div className={`flex flex-wrap gap-1.5 ${compact ? "" : "mb-4"}`}>
      <Badge variant="outline" className={`text-xs font-medium border ${TIER_STYLES[tier] || TIER_STYLES.unknown}`}>
        <Database className="w-3 h-3 mr-1" />
        {TIER_LABELS[tier] || TIER_LABELS.unknown}
        {pct != null ? ` · ${Math.round(pct)}%` : ""}
      </Badge>
      {signals.official_lineup_pending && !signals.missing_lineups && (
        <Badge variant="outline" className="text-xs border-sky-500/30 text-sky-400 bg-sky-500/10">
          <Clock className="w-3 h-3 mr-1" />
          Official lineup pending
        </Badge>
      )}
      {signals.missing_lineups && (
        <Badge variant="outline" className="text-xs border-amber-500/30 text-amber-400 bg-amber-500/10">
          <AlertTriangle className="w-3 h-3 mr-1" />
          Missing lineups
        </Badge>
      )}
      {signals.missing_injuries && (
        <Badge variant="outline" className="text-xs border-amber-500/30 text-amber-400 bg-amber-500/10">
          <AlertTriangle className="w-3 h-3 mr-1" />
          Missing injuries
        </Badge>
      )}
      {signals.odds_available && (
        <Badge variant="outline" className="text-xs border-green-500/30 text-green-400 bg-green-500/10">
          <TrendingUp className="w-3 h-3 mr-1" />
          Odds available
        </Badge>
      )}
      {!signals.odds_available && tier !== "unknown" && (
        <Badge variant="outline" className="text-xs border-white/10 text-muted-foreground bg-white/5">
          <Activity className="w-3 h-3 mr-1" />
          No odds data
        </Badge>
      )}
    </div>
  );
}
