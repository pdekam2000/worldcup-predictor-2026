import React from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { Trophy } from "lucide-react";
import {
  getArchiveStatusConfig,
  resolveArchiveStatus,
  pick1x2Label,
  formatShortDate,
} from "@/lib/archiveStatus";
import { SOURCE_BADGES, formatMarketKeys } from "@/lib/archiveFilters";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";
import { TierBadge } from "@/components/terminal";

function actualLabel(value) {
  const v = String(value || "").toLowerCase();
  if (v === "home_win" || v === "home") return "Home win";
  if (v === "draw") return "Draw";
  if (v === "away_win" || v === "away") return "Away win";
  return value || "—";
}

export default function ArchiveCard({ item, index = 0 }) {
  const navigate = useNavigate();
  const statusKey = resolveArchiveStatus(item);
  const cfg = getArchiveStatusConfig(statusKey);
  const Icon = cfg.icon;
  const predicted = item?.predicted_1x2 ?? item?.prediction_1x2 ?? item?.main_prediction;
  const confidence = item?.predicted_confidence ?? item?.confidence;
  const entryPath = item?.entry_id || item?.id ? `/history/${item.entry_id || item.id}` : null;
  const sourceKey = item?.source || "my";
  const sourceBadge = SOURCE_BADGES[sourceKey] || SOURCE_BADGES.global_archive;
  const marketTags = formatMarketKeys(item?.predicted_market_keys);
  const matchDate = item?.match_date || item?.viewed_at || item?.prediction_date;
  const evalDate = item?.evaluated_at;

  const openDetail = () => {
    if (entryPath) navigate(entryPath);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      className={`rounded-xl border p-4 ${cfg.card} ${
        entryPath ? "cursor-pointer hover:border-primary/40 transition-colors" : ""
      }`}
      onClick={entryPath ? openDetail : undefined}
      onKeyDown={
        entryPath
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                openDetail();
              }
            }
          : undefined
      }
      role={entryPath ? "button" : undefined}
      tabIndex={entryPath ? 0 : undefined}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-3 min-w-0 flex-1">
          <MatchTeamsRow
            homeTeam={item.home_team || "Home"}
            awayTeam={item.away_team || "Away"}
            countryHint={item.country || item.league}
            size="md"
          />
          <div className="flex items-start gap-2">
            <div className={`w-1 self-stretch rounded-full ${cfg.dot} shrink-0`} />
            <div className="min-w-0 flex-1">
              <div className="text-xs text-muted-foreground flex flex-wrap items-center gap-x-3 gap-y-1 mt-0">
                <span className="inline-flex items-center gap-1">
                  <Trophy className="w-3 h-3" />
                  {item.league || "World Cup 2026"}
                </span>
                <span>Match: {formatShortDate(matchDate)}</span>
                {evalDate && statusKey !== "pending" && (
                  <span>Evaluated: {formatShortDate(evalDate)}</span>
                )}
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 pl-3">
            <span
              className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold border ${sourceBadge.className}`}
            >
              {sourceBadge.label}
            </span>
            {marketTags.map((tag) => (
              <span
                key={tag}
                className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium bg-muted text-muted-foreground border border-border"
              >
                {tag}
              </span>
            ))}
            {entryPath && (
              <Link
                to={entryPath}
                onClick={(e) => e.stopPropagation()}
                className="text-primary text-[10px] font-medium hover:underline"
              >
                View detail
              </Link>
            )}
          </div>
        </div>

        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold shrink-0 ${cfg.badge}`}
        >
          <Icon className="w-3.5 h-3.5" />
          {cfg.label}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-3 text-sm pl-3">
        <div>
          <div className="text-xs text-muted-foreground">1X2 pick</div>
          <div className="font-semibold mt-0.5">
            <span className="px-2 py-0.5 rounded-md bg-primary/10 text-primary text-xs uppercase">
              {pick1x2Label(predicted)}
            </span>
          </div>
        </div>
        <div>
          <div className="text-xs text-[#94A3B8]">Trust tier</div>
          <div className="font-medium mt-1.5">
            {item.hybrid_confidence?.team?.tier ? (
              <TierBadge tier={item.hybrid_confidence.team.tier} label="Model" compact />
            ) : (
              <span className="text-xs text-[#94A3B8]">—</span>
            )}
          </div>
        </div>
        <div className="hidden sm:block">
          <div className="text-xs text-[#94A3B8]">Legacy conf</div>
          <div className="font-medium mt-0.5 tabular-nums text-[#94A3B8]/70 text-xs">
            {confidence != null && !Number.isNaN(Number(confidence))
              ? `${Math.round(Number(confidence))}%`
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Actual</div>
          <div className="font-medium mt-0.5">{actualLabel(item.actual_result)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Score</div>
          <div className="font-medium mt-0.5">{item.final_score || "—"}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Markets</div>
          <div className="font-medium mt-0.5 tabular-nums">{item.markets_count ?? "—"}</div>
        </div>
      </div>

      {(item.evaluated_markets_count != null || item.correct_markets_count != null) && (
        <div className="mt-3 pt-3 border-t border-border text-xs text-muted-foreground pl-3">
          {item.evaluated_markets_count > 0 ? (
            <span className="tabular-nums">
              Evaluated markets: {item.correct_markets_count ?? 0} correct ·{" "}
              {item.wrong_markets_count ?? 0} wrong · {item.pending_markets_count ?? 0} pending
            </span>
          ) : (
            <span>No settled market evaluations yet for this prediction.</span>
          )}
        </div>
      )}
    </motion.div>
  );
}
