import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BarChart3,
  CheckCircle2,
  Clock,
  RefreshCw,
  Target,
  Timer,
  TrendingUp,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import GoalTimingPageShell from "@/components/goalTiming/GoalTimingPageShell";
import HybridConfidenceDisplay, { TierBadge } from "@/components/goalTiming/HybridConfidenceDisplay";
import { fetchGoalTimingDashboard,
  fetchGoalTimingPicks,
  fetchGoalTimingHistory,
  fetchGoalTimingAccuracy,
  fetchGoalTimingPerformance,
} from "@/api/saasApi";
import { classifyApiError } from "@/lib/apiError";

function pct(value) {
  if (value == null || Number.isNaN(value)) return "—";
  return `${Math.round(value)}%`;
}

function StatCard({ label, value, sub, accent = false }) {
  return (
    <div
      className={`rounded-xl border p-4 bg-white shadow-sm ${
        accent ? "border-emerald-200 ring-1 ring-emerald-100" : "border-slate-200"
      }`}
    >
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`text-2xl font-bold mt-1 ${accent ? "text-emerald-700" : "text-slate-900"}`}>
        {value ?? "—"}
      </p>
      {sub && <p className="text-xs text-slate-500 mt-1">{sub}</p>}
    </div>
  );
}

function StatusBadge({ status }) {
  const map = {
    correct: "bg-emerald-50 text-emerald-700 border-emerald-200",
    wrong: "bg-red-50 text-red-700 border-red-200",
    partial: "bg-amber-50 text-amber-700 border-amber-200",
    pending: "bg-slate-50 text-slate-600 border-slate-200",
  };
  const cls = map[status] || map.pending;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full border capitalize ${cls}`}>
      {status || "pending"}
    </span>
  );
}

function BucketBar({ rows, title }) {
  if (!rows?.length) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <p className="text-sm font-semibold text-slate-800">{title}</p>
        <p className="text-xs text-slate-500 mt-2">No evaluated samples in this bucket yet.</p>
      </div>
    );
  }
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm space-y-2">
      <p className="text-sm font-semibold text-slate-800">{title}</p>
      {rows.map((row) => (
        <div key={row.bucket} className="flex items-center justify-between gap-2 text-sm">
          <span className="font-mono text-xs text-slate-600 truncate">{row.bucket}</span>
          <span className="font-semibold text-emerald-700 shrink-0">{pct(row.winrate_pct)}</span>
          <span className="text-xs text-slate-400 shrink-0">n={row.total}</span>
        </div>
      ))}
    </div>
  );
}

export default function GoalTimingDashboardPage() {
  const [dashboard, setDashboard] = useState(null);
  const [apiHealth, setApiHealth] = useState({ ok: true, errors: [] });
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    setRefreshing(true);
    const errors = [];
    const probes = await Promise.allSettled([
      fetchGoalTimingDashboard(),
      fetchGoalTimingPicks({ limit: 5 }),
      fetchGoalTimingHistory({ limit: 5 }),
      fetchGoalTimingAccuracy(),
      fetchGoalTimingPerformance(),
    ]);
    const names = ["dashboard", "picks", "history", "accuracy", "performance"];
    probes.forEach((result, i) => {
      if (result.status === "rejected") {
        errors.push({
          endpoint: names[i],
          message: classifyApiError({ message: result.reason?.message || "" }).message,
        });
      }
    });
    setApiHealth({ ok: errors.length === 0, errors });
    if (probes[0].status === "fulfilled") {
      setDashboard(probes[0].value);
    } else {
      setDashboard(null);
    }
    setLoading(false);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const counts = dashboard?.counts || {};
  const accuracy = dashboard?.accuracy || {};
  const scheduler = dashboard?.scheduler || {};
  const noPick = dashboard?.no_pick || {};
  const upcoming = dashboard?.upcoming_picks || [];
  const recentEvals = dashboard?.recent_evaluations || [];
  const learning = dashboard?.learning || {};

  const formatTs = (ts) => {
    if (!ts) return "—";
    try {
      return new Date(ts).toLocaleString();
    } catch {
      return ts;
    }
  };

  return (
    <GoalTimingPageShell
      title="EGIE Monitoring"
      subtitle="Live production metrics from PostgreSQL evaluations and SQLite fixtures. No demo data."
      phase="52E"
      variant="monitoring"
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm text-slate-600">
          <span
            className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${
              apiHealth.ok
                ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                : "bg-red-50 text-red-700 border-red-200"
            }`}
          >
            {apiHealth.ok ? <CheckCircle2 className="w-3.5 h-3.5" /> : <AlertCircle className="w-3.5 h-3.5" />}
            {apiHealth.ok ? "All EGIE APIs live" : `${apiHealth.errors.length} API error(s)`}
          </span>
          {dashboard?.data_source && (
            <span className="text-xs text-slate-400">source: {dashboard.data_source}</span>
          )}
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={load}
          disabled={refreshing}
          className="border-emerald-200 text-emerald-800 hover:bg-emerald-50"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      {!apiHealth.ok && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
          <p className="font-medium flex items-center gap-2">
            <AlertCircle className="w-4 h-4" />
            Some EGIE endpoints failed
          </p>
          <ul className="mt-2 space-y-1 text-xs">
            {apiHealth.errors.map((e) => (
              <li key={e.endpoint}>
                <strong>{e.endpoint}</strong>: {e.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {loading && !dashboard && (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-500 text-sm">
          Loading live dashboard…
        </div>
      )}

      {dashboard && (
        <>
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
            <StatCard label="Published picks" value={counts.published_picks} accent />
            <StatCard label="Evaluated" value={counts.evaluated_picks} sub="Finished matches scored" />
            <StatCard label="Pending eval" value={counts.pending_picks} sub="Awaiting match finish" />
            <StatCard label="NO_PICK" value={counts.no_pick_count} sub="Below DQ / no signal" />
          </div>

          <div className="grid sm:grid-cols-3 gap-3">
            <StatCard
              label="Team accuracy"
              value={pct(accuracy.team_winrate_pct)}
              sub={`n=${accuracy.sample_size || 0}`}
              accent
            />
            <StatCard
              label="Range accuracy"
              value={pct(accuracy.range_winrate_pct)}
              sub="First goal minute bucket"
            />
            <StatCard
              label="Minute accuracy"
              value={pct(accuracy.minute_soft_winrate_pct ?? accuracy.minute_winrate_pct)}
              sub={
                accuracy.minute_soft_winrate_pct != null
                  ? "Includes partial tolerance"
                  : "Strict win rate"
              }
            />
          </div>

          <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4 shadow-sm">
            <div className="flex items-start gap-3">
              <Timer className="w-5 h-5 text-emerald-700 shrink-0 mt-0.5" />
              <div className="flex-1 min-w-0">
                <h2 className="font-semibold text-slate-900">Scheduler (egie-goal-timing-evaluation)</h2>
                <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3 mt-3 text-sm">
                  <div>
                    <p className="text-xs text-slate-500">Timer status</p>
                    <p className="font-medium text-slate-800">
                      {scheduler.timer_active ? "Active" : scheduler.timer_installed ? "Installed" : "Not detected"}
                    </p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Last run</p>
                    <p className="font-medium text-slate-800">{formatTs(scheduler.last_run_at)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">Last API refresh</p>
                    <p className="font-medium text-slate-800">{formatTs(scheduler.last_refresh_at)}</p>
                  </div>
                  <div>
                    <p className="text-xs text-slate-500">API calls (last run)</p>
                    <p className="font-medium text-slate-800">{scheduler.last_api_calls ?? 0}</p>
                  </div>
                </div>
                {scheduler.next_run_at && (
                  <p className="text-xs text-slate-500 mt-2 flex items-center gap-1">
                    <Clock className="w-3.5 h-3.5" />
                    Next scheduled: {formatTs(scheduler.next_run_at)}
                  </p>
                )}
              </div>
            </div>
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <BucketBar rows={learning.dq_bucket_winrate} title="DQ bucket win rate (team market)" />
            <BucketBar
              rows={learning.confidence_bucket_winrate}
              title="Legacy confidence bucket win rate (team market)"
            />
          </div>

          <div className="grid lg:grid-cols-2 gap-4">
            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                  <Target className="w-4 h-4 text-emerald-600" />
                  Upcoming picks ({upcoming.length})
                </h2>
                <Link to="/goal-timing/picks" className="text-xs text-emerald-700 font-medium inline-flex items-center gap-1">
                  All picks <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {upcoming.length === 0 ? (
                <p className="text-sm text-slate-500">No upcoming published picks in store.</p>
              ) : (
                <ul className="space-y-2 max-h-64 overflow-y-auto">
                  {upcoming.slice(0, 8).map((pick) => (
                    <li
                      key={pick.fixture_id}
                      className="flex justify-between gap-2 text-sm border-b border-slate-100 pb-2 last:border-0"
                    >
                      <span className="text-slate-800 truncate">
                        {pick.home_team} vs {pick.away_team}
                      </span>
                      <span className="text-slate-500 shrink-0 text-xs flex items-center gap-1">
                        {pick.first_goal_time_range}
                        {pick.hybrid_confidence?.team?.tier ? (
                          <TierBadge tier={pick.hybrid_confidence.team.tier} label="Team" />
                        ) : (
                          <span className="opacity-50">· legacy</span>
                        )}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <div className="flex items-center justify-between mb-3">
                <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                  <Activity className="w-4 h-4 text-emerald-600" />
                  Recent evaluations
                </h2>
                <Link to="/goal-timing/history" className="text-xs text-emerald-700 font-medium inline-flex items-center gap-1">
                  History <ArrowRight className="w-3 h-3" />
                </Link>
              </div>
              {recentEvals.length === 0 ? (
                <p className="text-sm text-slate-500">No evaluations yet — scheduler runs every 30 min after FT.</p>
              ) : (
                <ul className="space-y-2">
                  {recentEvals.slice(0, 6).map((item) => (
                    <li
                      key={item.evaluation_id || item.fixture_id}
                      className="flex justify-between items-center gap-2 text-sm border-b border-slate-100 pb-2 last:border-0"
                    >
                      <span className="text-slate-800 truncate">
                        {item.home_team} vs {item.away_team}
                      </span>
                      <StatusBadge status={item.status?.first_goal_team} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </div>

          {noPick.count > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50/50 p-4 shadow-sm">
              <h2 className="font-semibold text-slate-900 flex items-center gap-2">
                <Zap className="w-4 h-4 text-amber-600" />
                NO_PICK ({noPick.count})
              </h2>
              <ul className="mt-3 space-y-2 text-sm">
                {(noPick.items || []).slice(0, 5).map((item) => (
                  <li key={item.fixture_id} className="border-b border-amber-100 pb-2 last:border-0">
                    <p className="font-medium text-slate-800">
                      {item.home_team} vs {item.away_team}
                      <span className="text-slate-500 font-normal ml-2">
                        DQ {Math.round((item.data_quality_score || 0) * 100)}%
                      </span>
                    </p>
                    <p className="text-xs text-slate-600 mt-0.5 line-clamp-2">{item.reason}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              { icon: BarChart3, title: "Accuracy", path: "/goal-timing/accuracy" },
              { icon: TrendingUp, title: "Performance", path: "/goal-timing/performance" },
              { icon: Target, title: "Picks", path: "/goal-timing/picks" },
              { icon: Activity, title: "History", path: "/goal-timing/history" },
            ].map(({ icon: Icon, title, path }) => (
              <Link
                key={path}
                to={path}
                className="rounded-xl border border-slate-200 bg-white p-4 hover:border-emerald-300 hover:shadow-md transition-all group"
              >
                <Icon className="w-5 h-5 text-emerald-600 mb-2" />
                <p className="font-semibold text-slate-900 group-hover:text-emerald-800">{title}</p>
              </Link>
            ))}
          </div>

          {dashboard.message && (
            <p className="text-xs text-slate-500 border-t border-slate-100 pt-3">{dashboard.message}</p>
          )}
        </>
      )}
    </GoalTimingPageShell>
  );
}
