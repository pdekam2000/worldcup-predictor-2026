import React, { useState, useEffect, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  History,
  CheckCircle,
  XCircle,
  Clock,
  Trophy,
  RefreshCw,
  HelpCircle,
  AlertCircle,
} from "lucide-react";
import { fetchPredictionHistoryPage } from "@/api/saasApi";
import { Button } from "@/components/ui/button";

const STATUS_FILTERS = [
  { id: "all", label: "All" },
  { id: "correct", label: "Correct" },
  { id: "wrong", label: "Wrong" },
  { id: "pending", label: "Pending" },
];

const resultConfig = {
  correct: {
    icon: CheckCircle,
    color: "text-green-400",
    bg: "bg-green-500/15 border-green-500/30",
    badge: "bg-green-500/20 text-green-300",
    label: "Correct",
  },
  wrong: {
    icon: XCircle,
    color: "text-red-400",
    bg: "bg-red-500/15 border-red-500/30",
    badge: "bg-red-500/20 text-red-300",
    label: "Wrong",
  },
  incorrect: {
    icon: XCircle,
    color: "text-red-400",
    bg: "bg-red-500/15 border-red-500/30",
    badge: "bg-red-500/20 text-red-300",
    label: "Wrong",
  },
  pending: {
    icon: Clock,
    color: "text-yellow-400",
    bg: "bg-yellow-500/10 border-yellow-500/20",
    badge: "bg-yellow-500/20 text-yellow-200",
    label: "Pending",
  },
  unknown: {
    icon: HelpCircle,
    color: "text-muted-foreground",
    bg: "bg-white/5 border-white/10",
    badge: "bg-white/10 text-muted-foreground",
    label: "Unknown",
  },
};

function pickLabel(value) {
  const v = String(value || "").toLowerCase();
  if (v === "home" || v === "home_win") return "1";
  if (v === "draw") return "X";
  if (v === "away" || v === "away_win") return "2";
  return "—";
}

function actualLabel(value) {
  const v = String(value || "").toLowerCase();
  if (v === "home_win") return "Home win";
  if (v === "draw") return "Draw";
  if (v === "away_win") return "Away win";
  return "—";
}

function formatDate(value) {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return "—";
  }
}

function resolveStatus(item) {
  return item?.result_status || item?.result || "pending";
}

function HistoryCard({ item, index }) {
  const status = resolveStatus(item);
  const rc = resultConfig[status] || resultConfig.pending;
  const Icon = rc.icon;
  const predicted = item?.predicted_1x2 ?? item?.prediction_1x2;
  const confidence = item?.predicted_confidence ?? item?.confidence;

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.03 }}
      className={`rounded-xl border p-4 ${rc.bg}`}
    >
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="space-y-1 min-w-0">
          <Link
            to={`/prediction/${item.fixture_id}`}
            className="font-semibold hover:text-primary transition-colors truncate block"
          >
            {item.home_team || "Home"} vs {item.away_team || "Away"}
          </Link>
          <div className="text-xs text-muted-foreground flex flex-wrap items-center gap-2">
            <span className="inline-flex items-center gap-1">
              <Trophy className="w-3 h-3" />
              {item.league || "World Cup 2026"}
            </span>
            <span>{formatDate(item.match_date || item.viewed_at)}</span>
          </div>
        </div>
        <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold shrink-0 ${rc.badge}`}>
          <Icon className="w-3.5 h-3.5" />
          {rc.label}
        </span>
      </div>

      <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <div>
          <div className="text-xs text-muted-foreground">Prediction</div>
          <div className="font-semibold mt-0.5">
            <span className="px-2 py-0.5 rounded-md bg-primary/10 text-primary text-xs uppercase">
              {pickLabel(predicted)}
            </span>
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Confidence</div>
          <div className="font-medium mt-0.5">
            {confidence != null && !Number.isNaN(Number(confidence)) ? `${Math.round(Number(confidence))}%` : "—"}
          </div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Actual result</div>
          <div className="font-medium mt-0.5">{actualLabel(item.actual_result)}</div>
        </div>
        <div>
          <div className="text-xs text-muted-foreground">Final score</div>
          <div className="font-medium mt-0.5">{item.final_score || "—"}</div>
        </div>
      </div>

      {(item.data_quality != null || item.agent_count != null) && (
        <div className="mt-3 pt-3 border-t border-white/5 text-xs text-muted-foreground flex flex-wrap gap-3">
          {item.data_quality != null && <span>Data quality: {Math.round(Number(item.data_quality))}%</span>}
          {item.agent_count != null && <span>Agents: {item.agent_count}</span>}
          {item.cache_schema_version && <span>Cache: {item.cache_schema_version}</span>}
        </div>
      )}
    </motion.div>
  );
}

export default function PredictionHistoryPage() {
  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState({ total: 0, correct: 0, wrong: 0, pending: 0, accuracy: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState("all");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPredictionHistoryPage({ limit: 100, resultFilter: filter });
      setHistory(data.history || []);
      setStats(data.stats || { total: 0, correct: 0, wrong: 0, pending: 0, accuracy: 0 });
    } catch (err) {
      setHistory([]);
      setError(err instanceof Error ? err.message : "Failed to load prediction history");
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load]);

  const summaryCards = useMemo(
    () => [
      { label: "Total", value: stats.total, color: "text-primary" },
      { label: "Correct", value: stats.correct ?? 0, color: "text-green-400" },
      { label: "Wrong", value: stats.wrong ?? 0, color: "text-red-400" },
      { label: "Accuracy", value: stats.correct || stats.wrong ? `${stats.accuracy}%` : "—", color: "text-accent" },
    ],
    [stats]
  );

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-display font-bold flex items-center gap-2">
            <History className="w-6 h-6 text-primary" /> Prediction History
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Historical predictions with match result evaluation.
          </p>
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

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {summaryCards.map((s) => (
          <div key={s.label} className="glass rounded-xl p-4 text-center">
            <div className={`text-2xl font-display font-bold ${s.color}`}>{loading ? "…" : s.value}</div>
            <div className="text-xs text-muted-foreground mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              filter === f.id
                ? "bg-primary text-primary-foreground"
                : "bg-white/5 text-muted-foreground hover:bg-white/10"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-16">
          <div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" />
        </div>
      ) : history.length === 0 ? (
        <div className="text-center py-16 glass rounded-2xl text-muted-foreground space-y-2">
          <p>No prediction history{filter !== "all" ? ` for “${filter}”` : ""} yet.</p>
          <p className="text-sm">
            Run a prediction from{" "}
            <Link to="/matches" className="text-primary hover:underline">
              Match Center
            </Link>{" "}
            to start building your history.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {history.map((item, index) => (
            <HistoryCard key={item.id || item.fixture_id || index} item={item} index={index} />
          ))}
        </div>
      )}
    </div>
  );
}
