import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Trophy, ChevronDown, ChevronUp } from "lucide-react";
import {
  getArchiveStatusConfig,
  resolveArchiveStatus,
  pick1x2Label,
  formatShortDate,
} from "@/lib/archiveStatus";
import { SOURCE_BADGES, formatMarketKeys, marketViewForItem } from "@/lib/archiveFilters";
import MatchTeamsRow from "@/components/match/MatchTeamsRow";
import { TierBadge } from "@/components/terminal";
import MarketBreakdownPanel from "@/components/archive/MarketBreakdownPanel";

function actualLabel(value) {
  const v = String(value || "").toLowerCase();
  if (v === "home_win" || v === "home") return "Home win";
  if (v === "draw") return "Draw";
  if (v === "away_win" || v === "away") return "Away win";
  return value || "—";
}

function displayPickForItem(item, marketFilter) {
  const view = marketViewForItem(item, marketFilter);
  if (view?.display_pick) return view.display_pick;
  if (view?.predicted_pick) return view.predicted_pick;
  const predicted = item?.predicted_1x2 ?? item?.prediction_1x2 ?? item?.main_prediction;
  return pick1x2Label(predicted) || predicted || "—";
}

export default function ArchiveCard({ item, index = 0, detailBase = "/archive", marketFilter = "best_bets" }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const statusKey = resolveArchiveStatus(item);
  const cfg = getArchiveStatusConfig(statusKey);
  const Icon = cfg.icon;
  const marketView = marketViewForItem(item, marketFilter);
  const displayPick = displayPickForItem(item, marketFilter);
  const displayStatus = marketView?.status || statusKey;
  const displayCfg = getArchiveStatusConfig(displayStatus);
  const confidence = marketView?.confidence ?? item?.predicted_confidence ?? item?.confidence;
  const entryPath = item?.entry_id || item?.id ? `${detailBase}/${item.entry_id || item.id}` : null;
  const sourceKey = item?.source || "my";
  const sourceBadge = SOURCE_BADGES[sourceKey] || SOURCE_BADGES.global_archive;
  const marketTags = formatMarketKeys(item?.predicted_market_keys);
  const matchDate = item?.match_date || item?.viewed_at || item?.prediction_date;
  const evalDate = item?.evaluated_at;
  const breakdown = item?.market_breakdown || [];

  const openDetail = () => {
    if (entryPath) navigate(entryPath);
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      className={`rounded-xl border p-4 bg-white shadow-sm ${cfg.card.includes("border") ? cfg.card : "border-amber-200"} ${
        entryPath ? "cursor-pointer hover:border-amber-400 transition-colors" : ""
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
              <div className="text-xs text-slate-500 flex flex-wrap items-center gap-x-3 gap-y-1 mt-0">
                <span className="inline-flex items-center gap-1">
                  <Trophy className="w-3 h-3 text-amber-500" />
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
            <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-semibold border ${sourceBadge.className}`}>
              {sourceBadge.label}
            </span>
            {marketTags.map((tag) => (
              <span
                key={tag}
                className="inline-flex px-2 py-0.5 rounded-full text-[10px] font-medium bg-amber-50 text-amber-900 border border-amber-200"
              >
                {tag}
              </span>
            ))}
            {item.limited_historical_payload && (
              <span className="text-[10px] text-slate-500 italic">Limited historical payload</span>
            )}
            {entryPath && (
              <Link
                to={entryPath}
                onClick={(e) => e.stopPropagation()}
                className="text-amber-700 text-[10px] font-medium hover:underline"
              >
                View detail
              </Link>
            )}
          </div>
        </div>

        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold shrink-0 ${displayCfg.badge}`}>
          <Icon className="w-3.5 h-3.5" />
          {displayCfg.label}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-3 text-sm pl-3">
        <div>
          <div className="text-xs text-slate-500">
            {marketView?.market_label || (marketFilter === "best_bets" ? "Best bet" : "Predicted")}
          </div>
          <div className="font-semibold mt-0.5">
            <span className="px-2 py-0.5 rounded-md bg-amber-100 text-amber-900 text-xs">
              {displayPick}
            </span>
          </div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Trust tier</div>
          <div className="font-medium mt-1.5">
            {item.hybrid_confidence?.team?.tier ? (
              <TierBadge tier={item.hybrid_confidence.team.tier} label="Model" compact />
            ) : (
              <span className="text-xs text-slate-400">—</span>
            )}
          </div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Confidence</div>
          <div className="font-medium mt-0.5 tabular-nums text-slate-800">
            {confidence != null && !Number.isNaN(Number(confidence))
              ? `${Math.round(Number(confidence))}%`
              : "—"}
          </div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Actual</div>
          <div className="font-medium mt-0.5 text-slate-800">{actualLabel(item.actual_result)}</div>
        </div>
        <div>
          <div className="text-xs text-slate-500">Score</div>
          <div className="font-medium mt-0.5 font-mono text-slate-900">{item.final_score || "—"}</div>
        </div>
      </div>

      <div className="mt-3 pt-3 border-t border-amber-100 text-xs text-slate-600 pl-3">
        {item.evaluated_markets_count > 0 ? (
          <span className="tabular-nums">
            {item.correct_markets_count ?? 0} correct · {item.wrong_markets_count ?? 0} wrong ·{" "}
            {item.unavailable_markets_count ?? 0} unavailable
          </span>
        ) : (
          <span>No settled market evaluations yet for this prediction.</span>
        )}
      </div>

      {breakdown.length > 0 && (
        <div className="mt-3 border-t border-amber-100 pt-2 pl-3" onClick={(e) => e.stopPropagation()}>
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex items-center gap-2 text-xs text-amber-800 hover:text-amber-900"
          >
            {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            Market breakdown ({breakdown.length})
          </button>
          <AnimatePresence>
            {open && (
              <motion.div initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }} className="overflow-hidden">
                <MarketBreakdownPanel rows={breakdown} compact />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}
    </motion.div>
  );
}
