import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { History, RefreshCw, AlertCircle, Search } from "lucide-react";
import { fetchHistoryArchive } from "@/api/saasApi";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import ArchiveCard from "@/components/archive/ArchiveCard";
import {
  STATUS_FILTERS,
  SCOPE_TABS,
  MARKET_FILTERS,
  SORT_OPTIONS,
  filterArchiveItems,
  needsClientFiltering,
} from "@/lib/archiveFilters";

const PAGE_SIZE = 50;
const CLIENT_FETCH_LIMIT = 500;

export default function PredictionHistoryPage() {
  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState({ total: 0, correct: 0, wrong: 0, pending: 0, partial: 0, accuracy: 0 });
  const [totalCount, setTotalCount] = useState(0);
  const [globalTotal, setGlobalTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [statusFilter, setStatusFilter] = useState("all");
  const [marketFilter, setMarketFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [scope, setScope] = useState("all");
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);

  const clientMode = needsClientFiltering({ search, marketFilter });

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
      setGlobalTotal(data.sources_included?.global_archive_total ?? 0);
    } catch (err) {
      setHistory([]);
      setError(err instanceof Error ? err.message : "Failed to load prediction archive");
    } finally {
      setLoading(false);
    }
  }, [statusFilter, scope, sort, page, clientMode]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [statusFilter, marketFilter, search, scope, sort]);

  const filteredHistory = useMemo(
    () => filterArchiveItems(history, { search, marketFilter }),
    [history, search, marketFilter]
  );

  const displayItems = useMemo(() => {
    if (!clientMode) return filteredHistory;
    const start = (page - 1) * PAGE_SIZE;
    return filteredHistory.slice(start, start + PAGE_SIZE);
  }, [clientMode, filteredHistory, page]);

  const effectiveTotal = clientMode ? filteredHistory.length : totalCount;
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / PAGE_SIZE));

  const summaryCards = useMemo(
    () => [
      { label: "Total", value: stats.total, color: "text-[#F8FAFC]" },
      { label: "Correct", value: stats.correct ?? 0, color: "text-[#00E676]" },
      { label: "Wrong", value: stats.wrong ?? 0, color: "text-[#FF4D4D]" },
      { label: "Partial", value: stats.partial ?? 0, color: "text-violet-400" },
      { label: "Pending", value: stats.pending ?? 0, color: "text-[#FFD166]" },
      { label: "Accuracy", value: stats.correct || stats.wrong ? `${stats.accuracy}%` : "—", color: "text-[#3B82F6]" },
    ],
    [stats]
  );

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-display font-bold flex items-center gap-2 text-[#F8FAFC]">
            <History className="w-6 h-6 text-[#00E676]" /> Prediction Archive
          </h1>
          <p className="text-sm text-[#94A3B8] mt-1">
            Evaluated and pending predictions from your account and the global system archive.
            Settled rows reflect production evaluation (including evaluated_markets_count).
          </p>
          {!loading && (
            <p className="text-xs text-muted-foreground mt-1">
              {globalTotal || effectiveTotal} stored globally
              {clientMode && filteredHistory.length !== history.length
                ? ` · ${filteredHistory.length} match current filters`
                : ` · showing ${displayItems.length} of ${effectiveTotal}`}
            </p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading} className="gap-2">
          <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {error && (
        <div className="glass rounded-xl p-4 border border-red-500/30 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-start gap-2 text-sm text-red-200">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            <span>{error}</span>
          </div>
          <Button variant="secondary" size="sm" onClick={load}>
            Retry
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {summaryCards.map((s) => (
          <div key={s.label} className="terminal-card p-4 text-center">
            <div className={`text-2xl font-display font-bold tabular-nums ${s.color}`}>
              {loading ? "…" : s.value}
            </div>
            <div className="text-xs text-muted-foreground mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="glass rounded-xl p-4 space-y-4">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by team name…"
            className="pl-9 bg-white/5 border-white/10"
          />
        </div>

        <div>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">Scope</p>
          <div className="flex flex-wrap gap-2">
            {SCOPE_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setScope(tab.id)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  scope === tab.id
                    ? "bg-accent text-accent-foreground"
                    : "bg-white/5 text-muted-foreground hover:bg-white/10"
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">Status</p>
          <div className="flex flex-wrap gap-2">
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setStatusFilter(f.id)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  statusFilter === f.id
                    ? "bg-primary text-primary-foreground"
                    : "bg-white/5 text-muted-foreground hover:bg-white/10"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div>
          <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-2">Market</p>
          <div className="flex flex-wrap gap-2">
            {MARKET_FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                onClick={() => setMarketFilter(f.id)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  marketFilter === f.id
                    ? "bg-violet-500/20 text-violet-200 border border-violet-500/30"
                    : "bg-white/5 text-muted-foreground hover:bg-white/10"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">Sort:</span>
          {SORT_OPTIONS.map((opt) => (
            <button
              key={opt.id}
              type="button"
              onClick={() => setSort(opt.id)}
              className={`px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
                sort === opt.id ? "bg-white/15 text-foreground" : "bg-white/5 text-muted-foreground hover:bg-white/10"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      ) : displayItems.length === 0 ? (
        <div className="text-center py-16 glass rounded-2xl text-muted-foreground space-y-3 px-4">
          <History className="w-10 h-10 mx-auto opacity-40" />
          <p className="font-medium text-foreground">No predictions match your filters</p>
          <p className="text-sm max-w-md mx-auto">
            {search || marketFilter !== "all" || statusFilter !== "all"
              ? "Try clearing search or filters to see more archive entries."
              : scope === "my"
                ? "You have no personal predictions yet. Switch to Global Archive or run a prediction from Match Center."
                : "The archive is empty for this scope."}
          </p>
          {(search || marketFilter !== "all") && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSearch("");
                setMarketFilter("all");
              }}
            >
              Clear search & market filters
            </Button>
          )}
          <p className="text-sm">
            <Link to="/matches" className="text-primary hover:underline">
              Open Match Center
            </Link>
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {displayItems.map((item, index) => (
            <ArchiveCard key={item.entry_id || item.id || item.fixture_id || index} item={item} index={index} />
          ))}
        </div>
      )}

      {!loading && !error && effectiveTotal > PAGE_SIZE && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
            Previous
          </Button>
          <span className="text-sm text-muted-foreground tabular-nums">
            Page {page} of {totalPages}
          </span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)}>
            Next
          </Button>
        </div>
      )}
    </div>
  );
}
