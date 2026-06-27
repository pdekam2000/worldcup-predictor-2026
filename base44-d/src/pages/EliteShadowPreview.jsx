import React, { useCallback, useEffect, useState } from "react";
import { Eye, Filter, RefreshCw, ChevronRight, X, AlertTriangle, GitCompare } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  fetchAdminEliteShadowPredictions,
  fetchAdminEliteShadowFixture,
  fetchAdminEliteShadowSummary,
  fetchAdminEliteShadowComparison,
  fetchAdminEliteShadowHealth,
  postAdminEliteShadowAction,
} from "@/api/saasApi";
import { formatPickWithProb, formatPercent } from "@/lib/formatPercent";

const TIER_COLORS = {
  A: "bg-green-500/15 text-green-400 border-green-500/30",
  B: "bg-blue-500/15 text-blue-400 border-blue-500/30",
  C: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  D: "bg-white/5 text-muted-foreground border-white/10",
};

const MARKET_OPTIONS = [
  { value: "all", label: "All markets" },
  { value: "1x2", label: "1x2" },
  { value: "first_goal_team", label: "First goal team" },
  { value: "team_to_score_first", label: "Team to score first" },
  { value: "anytime_goalscorer", label: "Anytime goalscorer" },
  { value: "first_goalscorer", label: "First goalscorer" },
  { value: "goal_timing", label: "Goal timing" },
];

function StatCard({ label, value, sub }) {
  return (
    <div className="glass rounded-xl p-4">
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className="text-2xl font-display font-bold">{value ?? "—"}</div>
      {sub && <div className="text-xs text-muted-foreground mt-1">{sub}</div>}
    </div>
  );
}

function formatPick(pred) {
  return formatPickWithProb(pred);
}

function formatConfidence(value) {
  return formatPercent(value);
}

export default function EliteShadowPreview() {
  const [summary, setSummary] = useState(null);
  const [fixtures, setFixtures] = useState([]);
  const [comparison, setComparison] = useState(null);
  const [comparisonRows, setComparisonRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [marketFilter, setMarketFilter] = useState("all");
  const [tierFilter, setTierFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [disagreementOnly, setDisagreementOnly] = useState(false);
  const [fixtureFilter, setFixtureFilter] = useState("");
  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [health, setHealth] = useState(null);
  const [actionLoading, setActionLoading] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    const fixtureId = fixtureFilter.trim() ? Number(fixtureFilter.trim()) : undefined;
    try {
      const [sum, data, comp, healthData] = await Promise.all([
        fetchAdminEliteShadowSummary(),
        fetchAdminEliteShadowPredictions({
          market: marketFilter,
          tier: tierFilter,
          status: statusFilter,
          limit: 50,
        }),
        fetchAdminEliteShadowComparison({
          market: marketFilter,
          tier: tierFilter,
          status: statusFilter,
          disagreement_only: disagreementOnly,
          fixture_id: fixtureId,
          limit: 100,
        }),
        fetchAdminEliteShadowHealth(),
      ]);
      setSummary(sum);
      setFixtures(data.fixtures || []);
      setComparison(comp.summary || null);
      setComparisonRows(comp.rows || []);
      setHealth(healthData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load elite shadow preview");
    } finally {
      setLoading(false);
    }
  }, [marketFilter, tierFilter, statusFilter, disagreementOnly, fixtureFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const openDetail = async (fixtureId) => {
    setDetailLoading(true);
    try {
      const data = await fetchAdminEliteShadowFixture(fixtureId);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load fixture detail");
    } finally {
      setDetailLoading(false);
    }
  };

  const runAction = async (action) => {
    setActionLoading(action);
    setError(null);
    try {
      await postAdminEliteShadowAction(action);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Action ${action} failed`);
    } finally {
      setActionLoading(null);
    }
  };

  const scheduler = health?.scheduler || summary?.health || null;

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-display font-bold flex items-center gap-2">
            <Eye className="w-6 h-6 text-primary" /> Elite Shadow Preview
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Admin-only — Phase 58C shadow predictions. Not visible to public users.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-2 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

      <div className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 p-3 text-sm text-amber-200">
        <AlertTriangle className="w-4 h-4 mt-0.5 flex-shrink-0" />
        Shadow research path only — does not affect live WDE or user-facing predictions.
      </div>

      {scheduler && (
        <div className="glass rounded-xl p-4 space-y-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Shadow Scheduler (Phase A22)</h2>
            <span
              className={`text-xs px-2 py-0.5 rounded-full border ${
                scheduler.last_status === "ok"
                  ? "border-green-500/40 text-green-400"
                  : scheduler.last_status === "running"
                    ? "border-blue-500/40 text-blue-400"
                    : "border-white/20 text-muted-foreground"
              }`}
            >
              {scheduler.last_status || "never_run"}
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <StatCard label="Last run" value={scheduler.last_run_at ? scheduler.last_run_at.slice(0, 19) : "—"} />
            <StatCard label="Next run" value={scheduler.next_run_estimate ? scheduler.next_run_estimate.slice(0, 19) : "—"} />
            <StatCard
              label="Last duration"
              value={scheduler.last_duration_seconds != null ? `${scheduler.last_duration_seconds}s` : "—"}
            />
            <StatCard label="Rows last run" value={scheduler.rows_generated_last_run ?? 0} />
            <StatCard label="Evaluations" value={scheduler.evaluations_written ?? 0} sub="last cycle" />
            <StatCard label="Root cause added" value={scheduler.root_cause_records_added ?? 0} sub="last cycle" />
            <StatCard label="Queue pending" value={scheduler.queue_pending ?? 0} />
            <StatCard label="Last error" value={scheduler.last_error ? "yes" : "none"} sub={scheduler.last_error?.slice(0, 40)} />
          </div>
          <div className="flex flex-wrap gap-2 pt-1">
            {[
              ["run_now", "Run Shadow Now"],
              ["rebuild_jsonl", "Rebuild JSONL"],
              ["recalculate_root_cause", "Recalculate Root Cause"],
              ["re_evaluate", "Re-evaluate Finished"],
              ["vacuum", "Vacuum Store"],
              ["export", "Export JSONL"],
            ].map(([action, label]) => (
              <Button
                key={action}
                variant="outline"
                size="sm"
                disabled={!!actionLoading}
                onClick={() => runAction(action)}
              >
                {actionLoading === action ? "…" : label}
              </Button>
            ))}
          </div>
        </div>
      )}

      {error && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-300">{error}</div>
      )}

      {summary && (
        <>
          {summary.sources?.predictions?.exists === false ? (
            <div className="rounded-xl border border-white/10 bg-white/[0.03] p-6 text-center">
              <p className="text-base font-medium text-[#F8FAFC]">No shadow predictions have been generated yet.</p>
              <p className="text-sm text-muted-foreground mt-2 max-w-xl mx-auto">
                Elite Shadow reads Phase 58C JSONL stores on the API server. Run the shadow runtime or redeploy shadow data
                if historical predictions should appear here.
              </p>
              {summary.sources?.predictions?.path && (
                <p className="text-xs text-muted-foreground mt-3 font-mono break-all">{summary.sources.predictions.path}</p>
              )}
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <StatCard label="Fixtures" value={summary.fixtures_with_predictions} />
              <StatCard label="Prediction rows" value={summary.prediction_rows} />
              <StatCard label="Pending evals" value={summary.evaluations_pending} />
              <StatCard label="Root-cause records" value={summary.root_cause_records} />
            </div>
          )}
        </>
      )}

      <div className="glass rounded-xl p-4 flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-xs text-muted-foreground flex items-center gap-1 mb-1">
            <Filter className="w-3 h-3" /> Market
          </label>
          <select
            className="bg-background border border-white/10 rounded-lg px-3 py-2 text-sm"
            value={marketFilter}
            onChange={(e) => setMarketFilter(e.target.value)}
          >
            {MARKET_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Tier</label>
          <select
            className="bg-background border border-white/10 rounded-lg px-3 py-2 text-sm"
            value={tierFilter}
            onChange={(e) => setTierFilter(e.target.value)}
          >
            <option value="all">All tiers</option>
            <option value="A">Tier A</option>
            <option value="B">Tier B</option>
            <option value="C">Tier C</option>
            <option value="D">Tier D</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Status</label>
          <select
            className="bg-background border border-white/10 rounded-lg px-3 py-2 text-sm"
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
          >
            <option value="all">All</option>
            <option value="pending">Pending</option>
            <option value="evaluated">Evaluated</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-muted-foreground mb-1 block">Fixture ID</label>
          <input
            type="text"
            inputMode="numeric"
            placeholder="e.g. 1489409"
            className="bg-background border border-white/10 rounded-lg px-3 py-2 text-sm w-36"
            value={fixtureFilter}
            onChange={(e) => setFixtureFilter(e.target.value)}
          />
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground pb-2 cursor-pointer">
          <input
            type="checkbox"
            className="rounded border-white/20"
            checked={disagreementOnly}
            onChange={(e) => setDisagreementOnly(e.target.checked)}
          />
          Disagreement only
        </label>
      </div>

      <section className="space-y-4">
        <div className="flex items-center gap-2">
          <GitCompare className="w-5 h-5 text-primary" />
          <h2 className="text-lg font-semibold">Shadow vs Production</h2>
        </div>
        <p className="text-sm text-muted-foreground">
          Side-by-side comparison of Elite Shadow picks against stored production predictions for the same fixture and market.
        </p>

        {comparison && (
          <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
            <StatCard label="Comparable" value={comparison.total_comparable} sub={`of ${comparison.total_rows} rows`} />
            <StatCard label="Same pick" value={comparison.same_pick_count} />
            <StatCard label="Disagreements" value={comparison.disagreement_count} />
            <StatCard label="Avg prod conf" value={formatConfidence(comparison.average_production_confidence)} />
            <StatCard label="Avg shadow conf" value={formatConfidence(comparison.average_shadow_confidence)} />
            <StatCard
              label="Missing production"
              value={comparison.missing_production_count}
              sub={comparison.missing_production_count ? "no stored prod pick" : "all covered"}
            />
          </div>
        )}

        {comparison?.markets_with_most_disagreement?.length > 0 && (
          <div className="glass rounded-xl p-4">
            <h3 className="text-sm font-medium mb-3">Markets with most disagreement</h3>
            <div className="flex flex-wrap gap-2">
              {comparison.markets_with_most_disagreement.map((item) => (
                <span
                  key={item.market_id}
                  className="px-3 py-1 rounded-lg text-xs border border-red-500/30 bg-red-500/10 text-red-200"
                >
                  {item.market_id}: {item.disagreement_count}
                </span>
              ))}
            </div>
          </div>
        )}

        {comparison?.strong_disagreements?.length > 0 && (
          <div className="glass rounded-xl p-4">
            <h3 className="text-sm font-medium mb-3">Strong shadow disagreements</h3>
            <div className="space-y-2">
              {comparison.strong_disagreements.map((row) => (
                <div
                  key={`${row.fixture_id}-${row.market_id}`}
                  className="text-sm border border-white/5 rounded-lg p-3 bg-white/[0.02]"
                >
                  <div className="font-medium">{row.match}</div>
                  <div className="text-xs text-muted-foreground mt-1">
                    {row.market_id} · Shadow: <span className="text-foreground">{row.shadow_pick || "—"}</span> (
                    {formatConfidence(row.shadow_confidence)}, tier {row.shadow_tier || "?"}) vs Production:{" "}
                    <span className="text-foreground">{row.production_pick || "—"}</span> (
                    {formatConfidence(row.production_confidence)})
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="glass rounded-xl overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-white/[0.03] text-muted-foreground">
              <tr>
                <th className="text-left p-3">Fixture</th>
                <th className="text-left p-3">Market</th>
                <th className="text-left p-3">Shadow</th>
                <th className="text-left p-3">Production</th>
                <th className="text-left p-3">Disagree</th>
                <th className="text-left p-3">Eval</th>
              </tr>
            </thead>
            <tbody>
              {comparisonRows.map((row) => (
                <tr key={`${row.fixture_id}-${row.market_id}`} className="border-t border-white/5 hover:bg-white/[0.02]">
                  <td className="p-3">
                    <div className="font-medium">
                      {row.fixture?.home_team || "Home"} vs {row.fixture?.away_team || "Away"}
                    </div>
                    <div className="text-xs text-muted-foreground">#{row.fixture_id}</div>
                  </td>
                  <td className="p-3">{row.market_id}</td>
                  <td className="p-3">
                    <div>{formatPick(row.shadow?.prediction)}</div>
                    <div className="text-xs text-muted-foreground">
                      {formatConfidence(row.shadow?.confidence)}
                      {row.shadow?.tier ? ` · tier ${row.shadow.tier}` : ""}
                    </div>
                  </td>
                  <td className="p-3">
                    <div>{row.has_production ? formatPick(row.production?.prediction) : "—"}</div>
                    <div className="text-xs text-muted-foreground">
                      {row.has_production ? formatConfidence(row.production?.confidence) : "missing"}
                    </div>
                  </td>
                  <td className="p-3">
                    {row.comparable ? (
                      <span
                        className={`px-2 py-0.5 rounded text-xs border ${
                          row.disagreement
                            ? "border-red-500/30 bg-red-500/10 text-red-300"
                            : "border-green-500/30 bg-green-500/10 text-green-300"
                        }`}
                      >
                        {row.disagreement ? "yes" : "no"}
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">n/a</span>
                    )}
                  </td>
                  <td className="p-3 text-xs text-muted-foreground">{row.evaluation_status || "—"}</td>
                </tr>
              ))}
              {!loading && comparisonRows.length === 0 && (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-muted-foreground">
                    No comparison rows match filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <div className="glass rounded-xl overflow-hidden">
        <div className="p-4 border-b border-white/5">
          <h2 className="text-lg font-semibold">Shadow fixtures</h2>
        </div>
        <table className="w-full text-sm">
          <thead className="bg-white/[0.03] text-muted-foreground">
            <tr>
              <th className="text-left p-3">Fixture</th>
              <th className="text-left p-3">Kickoff</th>
              <th className="text-left p-3">Markets</th>
              <th className="text-left p-3">Status</th>
              <th className="p-3" />
            </tr>
          </thead>
          <tbody>
            {fixtures.map((fx) => (
              <tr key={fx.fixture_id} className="border-t border-white/5 hover:bg-white/[0.02]">
                <td className="p-3">
                  <div className="font-medium">
                    {fx.fixture?.home_team || "Home"} vs {fx.fixture?.away_team || "Away"}
                  </div>
                  <div className="text-xs text-muted-foreground">#{fx.fixture_id}</div>
                </td>
                <td className="p-3 text-muted-foreground">{fx.fixture?.kickoff_utc || "—"}</td>
                <td className="p-3">{(fx.markets || []).length}</td>
                <td className="p-3">
                  <span className="px-2 py-0.5 rounded-md text-xs border border-white/10 bg-white/5">
                    {fx.fixture_status}
                  </span>
                </td>
                <td className="p-3 text-right">
                  <Button variant="ghost" size="sm" onClick={() => openDetail(fx.fixture_id)}>
                    Inspect <ChevronRight className="w-4 h-4 ml-1" />
                  </Button>
                </td>
              </tr>
            ))}
            {!loading && fixtures.length === 0 && (
              <tr>
                <td colSpan={5} className="p-8 text-center text-muted-foreground">
                  No shadow predictions match filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {(detail || detailLoading) && (
        <div className="fixed inset-0 z-50 flex justify-end">
          <div className="absolute inset-0 bg-black/60" onClick={() => setDetail(null)} />
          <div className="relative w-full max-w-xl h-full bg-[#0a0f1a] border-l border-white/10 overflow-y-auto p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold">Fixture shadow detail</h2>
              <button type="button" onClick={() => setDetail(null)} className="p-2 hover:bg-white/5 rounded-lg">
                <X className="w-5 h-5" />
              </button>
            </div>
            {detailLoading && <p className="text-muted-foreground">Loading…</p>}
            {detail && (
              <div className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  {detail.fixture?.home_team} vs {detail.fixture?.away_team}
                </p>
                {(detail.markets || []).map((m) => (
                  <div key={m.market_id} className="rounded-xl border border-white/10 p-4 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{m.market_id}</span>
                      <span className={`px-2 py-0.5 rounded text-xs border ${TIER_COLORS[m.tier] || TIER_COLORS.C}`}>
                        Tier {m.tier || "?"}
                      </span>
                    </div>
                    <div className="text-sm">
                      Pick: <span className="text-foreground">{formatPick(m.prediction)}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      Confidence: {formatConfidence(m.confidence)} · Status:{" "}
                      {m.status}
                    </div>
                    {m.evaluation && (
                      <div className="text-xs text-muted-foreground">
                        Outcome: {m.evaluation.outcome} · Reality: {String(m.evaluation.reality ?? "—")}
                      </div>
                    )}
                    {m.root_cause?.length > 0 && (
                      <div className="text-xs border-t border-white/5 pt-2 mt-2">
                        <div className="font-medium text-amber-300 mb-1">Root cause</div>
                        {m.root_cause.map((rc, i) => (
                          <div key={i} className="text-muted-foreground">
                            {rc.failure_reason} — {rc.recommended_action}
                          </div>
                        ))}
                      </div>
                    )}
                    {(m.component_contributions || []).length > 0 && (
                      <details className="text-xs">
                        <summary className="cursor-pointer text-muted-foreground">Components</summary>
                        <ul className="mt-2 space-y-1 pl-2">
                          {m.component_contributions.map((c, i) => (
                            <li key={i}>
                              {c.component_id}: w={c.weight} pred={String(c.prediction ?? "—")}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
