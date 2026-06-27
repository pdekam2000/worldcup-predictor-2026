import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useSearchParams } from "react-router-dom";
import { motion, AnimatePresence } from "framer-motion";
import { AlertCircle, RefreshCw, Trophy, ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { fetchMatches, fetchCompetitions } from "@/api/worldcupApi";
import { fetchFavorites } from "@/api/saasApi";
import SaasPageHeader, { SaasCard } from "@/components/saas/SaasPageHeader";
import LeagueSelector from "@/components/match-center/LeagueSelector";
import MatchCenterFilters from "@/components/match-center/MatchCenterFilters";
import EliteMatchCard from "@/components/match-center/EliteMatchCard";
import BetSlipDrawer from "@/components/match-center/BetSlipDrawer";
import TodaysElitePicks from "@/components/match-center/TodaysElitePicks";
import MatchCenterSkeleton from "@/components/match-center/MatchCenterSkeleton";
import { applyClientFilters } from "@/lib/matchCenterUtils";
import { useAuth } from "@/lib/AuthContext";

const PAGE_SIZE = 30;
const PRIORITY_COMPETITION = "world_cup_2026";

export default function MatchCenter() {
  const [searchParams, setSearchParams] = useSearchParams();
  const competitionParam = searchParams.get("competition") || "all";
  const { isAuthenticated } = useAuth();

  const [competitions, setCompetitions] = useState([]);
  const [totalUpcoming, setTotalUpcoming] = useState(0);
  const [matches, setMatches] = useState([]);
  const [elitePicks, setElitePicks] = useState([]);
  const [search, setSearch] = useState("");
  const [statusTab, setStatusTab] = useState(() => searchParams.get("status") || "upcoming");

  const handleStatusTabChange = (next) => {
    setStatusTab(next);
    const params = new URLSearchParams(searchParams);
    if (!next || next === "upcoming") params.delete("status");
    else params.set("status", next);
    setSearchParams(params, { replace: true });
  };
  const [page, setPage] = useState(1);
  const [totalCount, setTotalCount] = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [predictedCount, setPredictedCount] = useState(0);
  const [sourceLabel, setSourceLabel] = useState(null);
  const [loadMeta, setLoadMeta] = useState({ load_ms: null, cache_hits: null });
  const [loading, setLoading] = useState(true);
  const [backgroundLoading, setBackgroundLoading] = useState(false);
  const [apiError, setApiError] = useState(null);
  const [favoriteTeams, setFavoriteTeams] = useState([]);

  const [datePreset, setDatePreset] = useState("");
  const [highConfidence, setHighConfidence] = useState(false);
  const [eliteOnly, setEliteOnly] = useState(false);
  const [bestValue, setBestValue] = useState(false);
  const [liveOnly, setLiveOnly] = useState(false);
  const [upcomingOnly, setUpcomingOnly] = useState(false);
  const [liveSoon, setLiveSoon] = useState(false);
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [quickCompetition, setQuickCompetition] = useState("all");
  const [country, setCountry] = useState("all");

  const effectiveCompetition = quickCompetition !== "all" ? quickCompetition : competitionParam;

  const setCompetition = (key) => {
    setQuickCompetition("all");
    const next = new URLSearchParams(searchParams);
    if (!key || key === "all") next.delete("competition");
    else next.set("competition", key);
    setSearchParams(next, { replace: true });
  };

  const applyMatchResult = useCallback((result) => {
    setMatches(result.matches);
    setTotalCount(result.total_count);
    setTotalPages(result.total_pages || 1);
    setPredictedCount(result.predicted_fixture_count);
    setSourceLabel(result.source_label);
    setElitePicks(result.elite_picks_today || []);
    setLoadMeta({ load_ms: result.load_ms, cache_hits: result.cache_hits });
  }, []);

  const loadCompetitions = useCallback(async () => {
    try {
      const res = await fetchCompetitions();
      setCompetitions(res.competitions || []);
      setTotalUpcoming(res.total_upcoming || 0);
    } catch {
      setCompetitions([]);
    }
  }, []);

  const loadFavorites = useCallback(async () => {
    if (!isAuthenticated) {
      setFavoriteTeams([]);
      return;
    }
    try {
      const data = await fetchFavorites();
      const teams = (data.favorites || [])
        .filter((f) => f.type === "team")
        .map((f) => f.name || f.label)
        .filter(Boolean);
      setFavoriteTeams(teams);
    } catch {
      setFavoriteTeams([]);
    }
  }, [isAuthenticated]);

  const loadMatches = useCallback(async () => {
    setLoading(true);
    setApiError(null);
    const useIncremental = effectiveCompetition === "all" && page === 1;

    try {
      if (useIncremental) {
        const priority = await fetchMatches({
          status: statusTab,
          page: 1,
          page_size: PAGE_SIZE,
          competition: PRIORITY_COMPETITION,
          country: country !== "all" ? country : undefined,
          include_summary: true,
          elite_only: eliteOnly,
        });
        applyMatchResult(priority);
        setLoading(false);
        setBackgroundLoading(true);
        try {
          const full = await fetchMatches({
            status: statusTab,
            page: 1,
            page_size: PAGE_SIZE,
            competition: "all",
            country: country !== "all" ? country : undefined,
            include_summary: true,
            elite_only: eliteOnly,
          });
          applyMatchResult(full);
        } finally {
          setBackgroundLoading(false);
        }
        return;
      }

      const result = await fetchMatches({
        status: statusTab,
        page,
        page_size: PAGE_SIZE,
        competition: effectiveCompetition,
        country: country !== "all" ? country : undefined,
        include_summary: true,
        elite_only: eliteOnly,
      });
      applyMatchResult(result);
    } catch (err) {
      setMatches([]);
      setElitePicks([]);
      setApiError(err instanceof Error ? err.message : "Failed to load matches from API.");
    } finally {
      setLoading(false);
      setBackgroundLoading(false);
    }
  }, [statusTab, page, effectiveCompetition, country, eliteOnly, applyMatchResult]);

  useEffect(() => {
    const fromUrl = searchParams.get("status") || "upcoming";
    if (fromUrl !== statusTab) setStatusTab(fromUrl);
  }, [searchParams]);

  useEffect(() => {
    loadCompetitions();
    loadFavorites();
  }, [loadCompetitions, loadFavorites]);

  useEffect(() => {
    loadMatches();
  }, [loadMatches]);

  useEffect(() => {
    setPage(1);
  }, [
    statusTab,
    search,
    competitionParam,
    quickCompetition,
    country,
    eliteOnly,
    datePreset,
    highConfidence,
    bestValue,
    liveOnly,
    upcomingOnly,
    liveSoon,
    favoritesOnly,
  ]);

  const countries = useMemo(
    () => Array.from(new Set(competitions.map((c) => c.country).filter(Boolean))).sort(),
    [competitions]
  );

  const filtered = useMemo(
    () =>
      applyClientFilters(matches, {
        search,
        competitionKey: quickCompetition,
        datePreset,
        highConfidence,
        eliteOnly: eliteOnly && effectiveCompetition !== "all",
        bestValue,
        liveOnly,
        upcomingOnly,
        liveSoon,
        favoriteTeams: favoritesOnly ? favoriteTeams : [],
        minAiScore: eliteOnly ? 73 : 0,
      }),
    [
      matches,
      search,
      quickCompetition,
      datePreset,
      highConfidence,
      eliteOnly,
      bestValue,
      liveOnly,
      upcomingOnly,
      liveSoon,
      favoritesOnly,
      favoriteTeams,
      effectiveCompetition,
    ]
  );

  return (
    <div className="space-y-6 max-w-[1400px] mx-auto pb-24 px-1 sm:px-0">
      <SaasPageHeader
        eyebrow="Match intelligence"
        title="Match Center"
        subtitle="Filter by competition and status, scan fixtures, and open full multi-market predictions. Research only — not betting advice."
      />

      <LeagueSelector
        competitions={competitions}
        selectedKey={effectiveCompetition}
        onSelect={setCompetition}
        totalUpcoming={totalUpcoming}
      />

      <AnimatePresence mode="wait">
        {!loading && elitePicks.length > 0 && (
          <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }}>
            <TodaysElitePicks picks={elitePicks} />
          </motion.div>
        )}
      </AnimatePresence>

      <MatchCenterFilters
        search={search}
        onSearchChange={setSearch}
        statusTab={statusTab}
        onStatusTabChange={handleStatusTabChange}
        datePreset={datePreset}
        onDatePresetChange={setDatePreset}
        highConfidence={highConfidence}
        onHighConfidenceChange={setHighConfidence}
        eliteOnly={eliteOnly}
        onEliteOnlyChange={setEliteOnly}
        bestValue={bestValue}
        onBestValueChange={setBestValue}
        liveOnly={liveOnly}
        onLiveOnlyChange={setLiveOnly}
        upcomingOnly={upcomingOnly}
        onUpcomingOnlyChange={setUpcomingOnly}
        liveSoon={liveSoon}
        onLiveSoonChange={setLiveSoon}
        favoritesOnly={favoritesOnly}
        onFavoritesOnlyChange={setFavoritesOnly}
        competitionKey={quickCompetition}
        onCompetitionKeyChange={setQuickCompetition}
        country={country}
        onCountryChange={setCountry}
        countries={countries}
      />

      <div className="flex items-center justify-between gap-3 flex-wrap">
        <p className="text-xs text-slate-500">
          {filtered.length} shown · {totalCount} total
          {predictedCount > 0 && ` · ${predictedCount} with predictions`}
          {sourceLabel && ` · ${sourceLabel}`}
          {loadMeta.load_ms != null && ` · ${loadMeta.load_ms}ms`}
          {loadMeta.cache_hits != null && ` · cache ${loadMeta.cache_hits}`}
          {backgroundLoading && " · updating leagues…"}
        </p>
        <Button variant="outline" size="sm" onClick={() => { loadCompetitions(); loadMatches(); }} disabled={loading} className="border-slate-200">
          <RefreshCw className={`w-4 h-4 ${loading || backgroundLoading ? "animate-spin" : ""}`} />
        </Button>
      </div>

      {apiError && (
        <SaasCard className="p-6 text-center border-red-200 bg-red-50">
          <AlertCircle className="w-10 h-10 mx-auto mb-3 text-red-500" />
          <p className="text-sm text-red-700 mb-4">{apiError}</p>
          <Button type="button" variant="outline" size="sm" onClick={loadMatches} className="border-slate-200">Retry</Button>
        </SaasCard>
      )}

      {loading ? (
        <MatchCenterSkeleton count={6} />
      ) : (
        !apiError && filtered.length > 0 && (
          <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map((m, i) => (
              <motion.div
                key={`${m.competition_key || ""}-${m.id || m.fixture_id}`}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.02, 0.25) }}
              >
                <EliteMatchCard match={m} variant="saas" />
              </motion.div>
            ))}
          </div>
        )
      )}

      {!loading && !apiError && matches.length === 0 && (
        <SaasCard className="text-center py-16 p-6">
          <Trophy className="w-12 h-12 mx-auto mb-4 text-slate-300" />
          <p className="text-slate-600 font-medium">No matches in this view</p>
          <p className="text-xs text-slate-400 mt-2 max-w-sm mx-auto">
            Try another league, status tab, or date range. During quiet periods fixture lists can be empty — this is normal, not a provider outage.
          </p>
        </SaasCard>
      )}

      {!loading && !apiError && matches.length > 0 && filtered.length === 0 && (
        <SaasCard className="text-center py-12 p-6 text-slate-500">No matches match your filters.</SaasCard>
      )}

      {!loading && !apiError && totalPages > 1 && effectiveCompetition !== "all" && (
        <div className="flex items-center justify-center gap-3 pt-2">
          <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))} className="border-slate-200">
            <ChevronLeft className="w-4 h-4 mr-1" /> Previous
          </Button>
          <span className="text-sm text-slate-500">Page {page} of {totalPages}</span>
          <Button variant="outline" size="sm" disabled={page >= totalPages} onClick={() => setPage((p) => Math.min(totalPages, p + 1))} className="border-slate-200">
            Next <ChevronRight className="w-4 h-4 ml-1" />
          </Button>
        </div>
      )}

      <BetSlipDrawer />
    </div>
  );
}
