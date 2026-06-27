import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { Archive, RefreshCw, AlertCircle, Search } from "lucide-react";
import { fetchHistoryArchive } from "@/api/saasApi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ArchiveCard from "@/components/archive/ArchiveCard";
import {
  STATUS_FILTERS,
  SCOPE_TABS,
  MARKET_FILTERS,
  SORT_OPTIONS,
  LEAGUE_FILTERS,
  CONFIDENCE_TIERS,
  DATE_QUICK_FILTERS,
  filterArchivePro,
  needsExtendedClientFiltering,
  dateRangeFromQuickFilter,
} from "@/lib/archiveProFilters";

const PAGE_SIZE = 50;
const CLIENT_FETCH_LIMIT = 500;
const EMPTY_EVALUATED_MSG =
  "No evaluated predictions yet. Finished matches will appear here once scored.";

export default function ArchivePage() {
  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState({ total: 0, correct: 0, wrong: 0, pending: 0, partial: 0, accuracy: 0 });
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [marketFilter, setMarketFilter] = useState("best_bets");
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("all");
  const [sort, setSort] = useState("newest");
  const [league, setLeague] = useState("all");
  const [confidenceTier, setConfidenceTier] = useState("all");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [dateQuick, setDateQuick] = useState("all");
  const [engineVersion, setEngineVersion] = useState("all");
  const [page, setPage] = useState(1);

  const clientMode = needsExtendedClientFiltering({
    search,
    marketFilter,
    league,
    confidenceTier,
    dateFrom,
    dateTo,
    engineVersion,
    dateQuick,
  });

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHistoryArchive({
        limit: clientMode ? CLIENT_FETCH_LIMIT : PAGE_SIZE,
        offset: clientMode ? 0 : (page - 1) * PAGE_SIZE,
        resultFilter: statusFilter,
        scope,
        sort,
      });
      setHistory(data.history || []);
      setStats(data.stats || { total: 0, correct: 0, wrong: 0, pending: 0, partial: 0, accuracy: 0 });
      setTotalCount(data.total_count ?? (data.history || []).length);
    } catch (err) {
      setHistory([]);
      setError(err instanceof Error ? err.message : "Failed to load archive");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, scope, sort, page, clientMode]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [statusFilter, marketFilter, search, scope, sort, league, confidenceTier, dateFrom, dateTo, engineVersion, dateQuick]);

  const filtered = useMemo(
    () =>
      filterArchivePro(history, {
        search,
        marketFilter,
        league,
        confidenceTier,
        dateFrom,
        dateTo,
        engineVersion,
      }),
    [history, search, marketFilter, league, confidenceTier, dateFrom, dateTo, engineVersion]
  );

  const displayItems = useMemo(() => {
    if (!clientMode) return filtered;
    const start = (page - 1) * PAGE_SIZE;
    return filtered.slice(start, start + PAGE_SIZE);
  }, [clientMode, filtered, page]);

  const effectiveTotal = clientMode ? filtered.length : totalCount;
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / PAGE_SIZE));
  const hasEvaluated = (stats.correct || 0) + (stats.wrong || 0) + (stats.partial || 0) > 0;
  const bestBetWinrate = stats.best_bet_winrate?.accuracy ?? stats.accuracy ?? 0;

  const summaryCards = [
    { label: "Total", value: stats.total, color: "text-slate-900" },
    { label: "Correct", value: stats.correct ?? 0, color: "text-emerald-700" },
    { label: "Wrong", value: stats.wrong ?? 0, color: "text-red-600" },
    { label: "Partial", value: stats.partial ?? 0, color: "text-violet-700" },
    { label: "Pending", value: stats.pending ?? 0, color: "text-amber-700" },
    { label: "Best Bet Winrate", value: hasEvaluated ? `${bestBetWinrate}%` : "—", color: "text-amber-800" },
  ];

  return (
    <div className="space-y-6 max-w-6xl mx-auto px-1 sm:px-0 pb-12 bg-gradient-to-b from-amber-50/80 to-white min-h-screen">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-display font-bold flex items-center gap-2 text-slate-900">
            <Archive className="w-7 h-7 text-amber-500" /> Prediction Archive
          </h1>
          <p className="text-sm text-slate-600 mt-1">
            Market-level results — default view shows program best bets only. Public winrate uses best bets, not every internal market.
          </p>
        </div>
        <div className="flex gap-2">
          <Button asChild variant="outline" size="sm" className="border-white/10">
            <Link to="/results">Prediction Results</Link>
          </Button>
          <Button asChild variant="outline" size="sm" className="border-white/10">
            <Link to="/accuracy">Accuracy Center</Link>
          </Button>
          <Button variant="outline" size="sm" onClick={load} disabled={loading}>
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          </Button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/30 p-4 flex items-center gap-2 text-red-300 text-sm">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {summaryCards.map((s) => (
          <div key={s.label} className="rounded-xl border border-amber-200 bg-white p-4 text-center shadow-sm">
            <div className={`text-2xl font-bold tabular-nums ${s.color}`}>{loading ? "…" : s.value}</div>
            <div className="text-xs text-slate-500 mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-amber-200 bg-white p-4 space-y-4 shadow-sm">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#64748B]" />
          <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search team or league…" className="pl-9 bg-black/20 border-white/10" />
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="rounded-lg bg-black/20 border border-white/10 px-3 py-2 text-sm text-[#F8FAFC]" />
          <input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="rounded-lg bg-black/20 border border-white/10 px-3 py-2 text-sm text-[#F8FAFC]" />
          <select value={league} onChange={(e) => setLeague(e.target.value)} className="rounded-lg bg-black/20 border border-white/10 px-3 py-2 text-sm">
            {LEAGUE_FILTERS.map((o) => (
              <option key={o.id} value={o.id}>{o.label}</option>
            ))}
          </select>
          <select value={confidenceTier} onChange={(e) => setConfidenceTier(e.target.value)} className="rounded-lg bg-black/20 border border-white/10 px-3 py-2 text-sm">
            {CONFIDENCE_TIERS.map((o) => (
              <option key={o.id} value={o.id}>{o.label}</option>
            ))}
          </select>
          <Input
            value={engineVersion === "all" ? "" : engineVersion}
            onChange={(e) => setEngineVersion(e.target.value.trim() || "all")}
            placeholder="Engine version filter…"
            className="bg-black/20 border-white/10 text-sm"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {SCOPE_TABS.map((t) => (
            <button key={t.id} type="button" onClick={() => setScope(t.id)} className={`px-3 py-1.5 rounded-lg text-xs border ${scope === t.id ? "bg-[#3B82F6] text-white border-[#3B82F6]" : "bg-white/[0.04] text-[#94A3B8] border-white/[0.06]"}`}>{t.label}</button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {DATE_QUICK_FILTERS.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => {
                setDateQuick(f.id);
                const range = dateRangeFromQuickFilter(f.id);
                setDateFrom(range.dateFrom);
                setDateTo(range.dateTo);
              }}
              className={`px-3 py-1.5 rounded-lg text-xs border ${
                dateQuick === f.id
                  ? "bg-[#3B82F6]/20 text-[#7DD3FC] border-[#3B82F6]/30"
                  : "bg-white/[0.04] text-[#94A3B8] border-white/[0.06]"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          {STATUS_FILTERS.map((f) => (
            <button key={f.id} type="button" onClick={() => setStatusFilter(f.id)} className={`px-3 py-1.5 rounded-lg text-xs border ${statusFilter === f.id ? "bg-[#00E676]/20 text-[#00E676] border-[#00E676]/30" : "bg-white/[0.04] text-[#94A3B8] border-white/[0.06]"}`}>{f.label}</button>
          ))}
        </div>
        <div className="flex flex-wrap gap-2">
          <span className="text-xs text-slate-500 self-center mr-1">Market:</span>
          {MARKET_FILTERS.map((f) => (
            <button key={f.id} type="button" onClick={() => setMarketFilter(f.id)} className={`px-3 py-1.5 rounded-lg text-xs border ${marketFilter === f.id ? "bg-amber-400 text-slate-900 border-amber-500 font-semibold" : "bg-amber-50 text-slate-600 border-amber-200"}`}>{f.label}</button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-2 border-[#00E676]/20 border-t-[#00E676] rounded-full animate-spin" /></div>
      ) : displayItems.length === 0 ? (
        <div className="text-center py-16 rounded-2xl border border-white/[0.06] px-4">
          <Archive className="w-12 h-12 mx-auto text-[#64748B] mb-3 opacity-50" />
          <p className="font-medium text-[#F8FAFC]">
            {statusFilter === "all" && !search && marketFilter === "all" && !hasEvaluated
              ? EMPTY_EVALUATED_MSG
              : "No predictions match your filters"}
          </p>
          <p className="text-sm text-[#64748B] mt-2 max-w-md mx-auto">
            {hasEvaluated
              ? "Try adjusting filters or scope."
              : "Predictions appear when stored; evaluations appear after matches finish."}
          </p>
          <Link to="/matches" className="text-[#00E676] text-sm mt-4 inline-block hover:underline">Open Match Center</Link>
        </div>
      ) : (
        <div className="space-y-3">
          {displayItems.map((item, i) => (
            <ArchiveCard key={item.entry_id || item.id || item.fixture_id || i} item={item} index={i} detailBase="/archive" marketFilter={marketFilter} />
          ))}
        </div>
      )}

      {!loading && effectiveTotal > PAGE_SIZE && (
        <div className="flex justify-center gap-3">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>Previous</Button>
          <span className="text-sm text-[#94A3B8] self-center">Page {page} of {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>Next</Button>
        </div>
      )}
    </div>
  );
}
