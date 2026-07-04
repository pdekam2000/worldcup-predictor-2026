import React, { useEffect, useMemo, useState } from "react";
import { ChevronDown, ChevronUp, FlaskConical, Info, TrendingUp } from "lucide-react";
import { fetchEcseForFixture } from "@/api/worldcupApi";
import { useAuth } from "@/lib/AuthContext";
import { isAdminUser, isOwnerUser, hasMinimumRole } from "@/lib/rbac";
import { canViewEndResultTop5 } from "@/lib/planGating";
import {
  END_RESULT_CANDIDATES_DISCLAIMER,
  END_RESULT_CANDIDATES_TITLE,
  TRUST_RESEARCH_ONLY,
} from "@/lib/trustCopy";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

function tierClass(tier) {
  if (tier === "A") return "bg-[#00E676]/15 text-[#00E676] border-[#00E676]/30";
  if (tier === "B") return "bg-[#7DD3FC]/15 text-[#7DD3FC] border-[#7DD3FC]/30";
  return "bg-white/5 text-[#94A3B8] border-white/10";
}

function freshnessBadgeClass(flag) {
  if (flag === "FRESH_ODDS") return "bg-[#00E676]/15 text-[#00E676] border-[#00E676]/30";
  if (flag === "STALE_ODDS" || flag === "REQUIRES_FRESH_ODDS") return "bg-[#FFD166]/15 text-[#FFD166] border-[#FFD166]/30";
  return "bg-[#FB923C]/15 text-[#FB923C] border-[#FB923C]/30";
}

function freshnessLabel(freshness) {
  const flag = freshness?.freshness_flag || freshness?.recommendation_flag;
  if (flag === "FRESH_ODDS" || flag === "FRESH_ODDS_OK") return "Fresh odds";
  if (flag === "STALE_ODDS") return "Stale odds";
  if (flag === "REQUIRES_FRESH_ODDS") return "Requires fresh odds";
  if (flag === "ODDS_FRESHNESS_UNKNOWN") return "Odds age unknown";
  return null;
}

const ODDS_FRESHNESS_TOOLTIP =
  "Odds age can affect exact-score ranking. Fresh odds are recommended for knockout matches.";

function OddsFreshnessBadge({ freshness, ownerOnlyUnknown = false }) {
  if (!freshness) return null;
  const flag = freshness.freshness_flag || freshness.recommendation_flag;
  if (ownerOnlyUnknown && flag === "ODDS_FRESHNESS_UNKNOWN") return null;
  const label = freshnessLabel(freshness);
  if (!label) return null;
  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <span
            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-semibold cursor-help ${freshnessBadgeClass(flag)}`}
          >
            <Info className="w-3 h-3" />
            {label}
          </span>
        </TooltipTrigger>
        <TooltipContent side="top" className="max-w-xs text-xs">
          {ODDS_FRESHNESS_TOOLTIP}
          {freshness.odds_age_hours != null && (
            <span className="block mt-1 text-muted-foreground">
              Age: {freshness.odds_age_hours}h
            </span>
          )}
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
}

function ScoreChip({ scoreline, rank, probabilityPct, maxPct, compact }) {
  const width = maxPct > 0 ? Math.min(100, (probabilityPct / maxPct) * 100) : 0;
  if (compact) {
    return (
      <div className="flex items-center gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-2">
        <span className="text-[10px] font-bold text-[#64748B]">#{rank}</span>
        <span className="text-sm font-semibold text-[#F8FAFC] tabular-nums">{scoreline}</span>
        <span className="ml-auto text-xs text-[#94A3B8] tabular-nums">{probabilityPct.toFixed(1)}%</span>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="font-semibold text-[#F8FAFC] tabular-nums">
          <span className="inline-flex items-center justify-center w-5 h-5 mr-1.5 rounded-full bg-white/10 text-[10px] text-[#94A3B8]">
            {rank}
          </span>
          {scoreline}
        </span>
        <span className="text-[#94A3B8] tabular-nums">{probabilityPct.toFixed(1)}%</span>
      </div>
      <Progress value={width} className="h-2 bg-white/10" />
    </div>
  );
}

function ConsistencyNotes({ notes }) {
  if (!notes?.length) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {notes.map((n) => (
        <span
          key={n.key + n.label}
          className={`px-2 py-0.5 rounded-full border text-[10px] font-medium ${
            n.status === "aligned"
              ? "bg-[#00E676]/10 text-[#00E676] border-[#00E676]/25"
              : n.status === "warning"
                ? "bg-[#FFD166]/10 text-[#FFD166] border-[#FFD166]/25"
                : "bg-[#FB923C]/10 text-[#FB923C] border-[#FB923C]/25"
          }`}
        >
          {n.label}
        </span>
      ))}
    </div>
  );
}

function ShadowPreviewBlock({ preview }) {
  if (!preview) return null;
  return (
    <div className="rounded-lg border border-dashed border-[#FB923C]/40 bg-[#FB923C]/5 p-3 space-y-2">
      <p className="text-[10px] uppercase tracking-wide text-[#FB923C] font-semibold">
        Shadow Re-rank Preview
      </p>
      <p className="text-[11px] text-[#FB923C]/90 italic">
        {preview.label || "Shadow advisory only — not production prediction."}
      </p>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <p className="text-[#64748B]">Production Top 1</p>
          <p className="text-[#F8FAFC] font-semibold">{preview.baseline_top_1 || "—"}</p>
        </div>
        <div>
          <p className="text-[#64748B]">Shadow Top 1</p>
          <p className="text-[#F8FAFC] font-semibold">{preview.shadow_top_1 || "—"}</p>
        </div>
      </div>
      {Array.isArray(preview.shadow_top_3) && preview.shadow_top_3.length > 0 && (
        <p className="text-[11px] text-[#94A3B8]">
          Shadow Top 3: {preview.shadow_top_3.join(" · ")}
        </p>
      )}
    </div>
  );
}

function BestValueBlock({ bestValue, topScoreline }) {
  if (!bestValue) return null;
  const edge = bestValue.value_score;
  const positive = edge > 0;
  return (
    <div
      className={`rounded-lg border p-3 space-y-1 ${
        positive ? "border-[#00E676]/25 bg-[#00E676]/5" : "border-white/10 bg-white/[0.02]"
      }`}
    >
      <div className="flex items-center gap-2">
        <TrendingUp className={`w-4 h-4 ${positive ? "text-[#00E676]" : "text-[#94A3B8]"}`} />
        <p className="text-[10px] uppercase tracking-wide text-[#94A3B8]">Best value — {topScoreline}</p>
      </div>
      <p className="text-sm text-[#F8FAFC]">
        Model {(bestValue.model_probability * 100).toFixed(1)}% vs market {(bestValue.implied_probability * 100).toFixed(1)}%
      </p>
    </div>
  );
}

export default function EndResultCandidatesPanel({
  fixtureId,
  compact = false,
  className = "",
  subscription = null,
  showTop5Default = false,
}) {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showTop5, setShowTop5] = useState(showTop5Default);

  const canTop5 = useMemo(() => {
    if (data?.access?.can_view_top5) return true;
    return (
      isOwnerUser(user) ||
      isAdminUser(user) ||
      hasMinimumRole(user, "pro") ||
      canViewEndResultTop5(subscription)
    );
  }, [user, subscription, data]);

  const canShadow = useMemo(() => {
    if (data?.access?.can_view_shadow_preview && data?.shadow_preview) return true;
    return (isOwnerUser(user) || isAdminUser(user)) && Boolean(data?.shadow_preview);
  }, [user, data]);

  useEffect(() => {
    if (!fixtureId) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEcseForFixture(fixtureId)
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Failed to load score candidates");
          setData(null);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [fixtureId, user?.role]);

  if (loading) {
    return (
      <div className={`rounded-lg border border-white/[0.06] bg-white/[0.02] p-3 ${className}`}>
        <p className="text-xs text-[#64748B]">Loading end result candidates…</p>
      </div>
    );
  }

  if (error) return null;

  if (!data?.available) {
    if (compact) return null;
    return (
      <div className={`rounded-lg border border-dashed border-white/[0.08] bg-white/[0.02] p-4 ${className}`}>
        <div className="flex items-center gap-2 mb-2">
          <FlaskConical className="w-4 h-4 text-[#64748B]" />
          <p className="text-sm font-medium text-[#94A3B8]">{END_RESULT_CANDIDATES_TITLE}</p>
        </div>
        <p className="text-xs text-[#64748B]">
          {data?.unavailable_reason === "no_registry_mapping"
            ? "Score candidates not available for this fixture yet."
            : "End result distribution not available for this fixture."}
        </p>
      </div>
    );
  }

  const top3 = (data.top_3?.length ? data.top_3 : (data.top_scores || []).slice(0, 3));
  const top5 = data.top_5?.length ? data.top_5 : (data.top_scores || []).slice(0, 5);
  const fallbackSingle = top3[0] || (data.top_scores || [])[0];
  const displayScores = showTop5 && canTop5 ? top5 : top3;
  const maxPct = displayScores.length ? Math.max(...displayScores.map((s) => s.probability_pct)) : 0;
  const showOwnerMeta = (isOwnerUser(user) || isAdminUser(user)) && data.engine_meta;

  return (
    <div className={`rounded-lg border border-[#A78BFA]/20 bg-[#A78BFA]/5 p-4 space-y-3 ${className}`}>
      <div className="flex flex-wrap items-center gap-2">
        <FlaskConical className="w-4 h-4 text-[#A78BFA]" />
        <p className="text-sm font-semibold text-[#F8FAFC]">
          {data.end_result_title || END_RESULT_CANDIDATES_TITLE}
        </p>
        {data.confidence_tier && (
          <span className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold ${tierClass(data.confidence_tier)}`}>
            Tier {data.confidence_tier}
          </span>
        )}
        <OddsFreshnessBadge
          freshness={data.odds_freshness}
          ownerOnlyUnknown={!isOwnerUser(user) && !isAdminUser(user)}
        />
      </div>

      {top3.length === 0 && fallbackSingle ? (
        <div className="rounded-lg border border-[#FFD166]/30 bg-[#FFD166]/5 p-3 space-y-2">
          <p className="text-[11px] text-[#FFD166]">Limited data — showing best available candidate only.</p>
          <ScoreChip
            scoreline={fallbackSingle.scoreline}
            rank={1}
            probabilityPct={fallbackSingle.probability_pct}
            maxPct={fallbackSingle.probability_pct}
            compact={compact}
          />
        </div>
      ) : (
        <div className={compact ? "space-y-2" : "space-y-3"}>
          {displayScores.map((s) => (
            <ScoreChip
              key={s.scoreline}
              scoreline={s.scoreline}
              rank={s.rank}
              probabilityPct={s.probability_pct}
              maxPct={maxPct}
              compact={compact}
            />
          ))}
        </div>
      )}

      <p className="text-[11px] text-[#94A3B8] leading-relaxed">
        {data.end_result_disclaimer || END_RESULT_CANDIDATES_DISCLAIMER}
      </p>

      {canTop5 && top5.length > top3.length && (
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-8 px-2 text-[#94A3B8] hover:text-[#F8FAFC]"
          onClick={() => setShowTop5((v) => !v)}
        >
          {showTop5 ? (
            <>
              <ChevronUp className="w-4 h-4 mr-1" /> Show Top 3
            </>
          ) : (
            <>
              <ChevronDown className="w-4 h-4 mr-1" /> Show Top 5
            </>
          )}
        </Button>
      )}

      {!compact && data.consistency_notes?.length > 0 && canTop5 && (
        <ConsistencyNotes notes={data.consistency_notes} />
      )}

      {!compact && showOwnerMeta && (
        <div className="rounded-lg border border-white/[0.08] bg-white/[0.02] p-3 text-[11px] text-[#64748B] space-y-1">
          <p className="text-[10px] uppercase tracking-wide text-[#94A3B8]">Engine metadata</p>
          {data.engine_meta.cache_source && <p>Cache: {data.engine_meta.cache_source}</p>}
          {data.engine_meta.prediction_engine_version && (
            <p>Engine: {data.engine_meta.prediction_engine_version}</p>
          )}
          {data.engine_meta.generated_at && <p>Generated: {data.engine_meta.generated_at}</p>}
        </div>
      )}

      {canShadow && !compact && <ShadowPreviewBlock preview={data.shadow_preview} />}

      {!compact && <BestValueBlock bestValue={data.best_value} topScoreline={top3[0]?.scoreline} />}

      <p className="text-[10px] text-[#475569] italic">{data.disclaimer || TRUST_RESEARCH_ONLY}</p>
    </div>
  );
}
