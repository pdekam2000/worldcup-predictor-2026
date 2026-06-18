import React, { useState, useEffect, useCallback } from "react";
import { motion } from "framer-motion";
import { History, CheckCircle, XCircle, Clock, Trophy } from "lucide-react";
import { fetchPredictionHistoryPage } from "@/api/saasApi";

const resultConfig = {
  correct: { icon: CheckCircle, color: "text-green-400", bg: "bg-green-500/10", label: "Correct" },
  incorrect: { icon: XCircle, color: "text-red-400", bg: "bg-red-500/10", label: "Incorrect" },
  pending: { icon: Clock, color: "text-yellow-400", bg: "bg-yellow-500/10", label: "Pending" },
};

export default function PredictionHistoryPage() {
  const [history, setHistory] = useState([]);
  const [stats, setStats] = useState({ total: 0, correct: 0, accuracy: 0 });
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchPredictionHistoryPage({ limit: 100 });
      setHistory(data.history || []);
      setStats(data.stats || { total: 0, correct: 0, accuracy: 0 });
    } catch (err) {
      setHistory([]);
      setError(err instanceof Error ? err.message : "Failed to load prediction history");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold flex items-center gap-2"><History className="w-6 h-6 text-primary" /> Prediction History</h1>
        <p className="text-sm text-muted-foreground mt-1">All predictions you've viewed, with results.</p>
      </div>

      {error && <div className="glass rounded-xl p-3 text-sm text-red-300">{error}</div>}

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Total Viewed", value: stats.total, color: "text-primary" },
          { label: "Correct", value: stats.correct, color: "text-green-400" },
          { label: "Accuracy", value: stats.total ? `${stats.accuracy}%` : "—", color: "text-accent" },
        ].map((s, i) => (
          <div key={i} className="glass rounded-xl p-4 text-center">
            <div className={`text-2xl font-display font-bold ${s.color}`}>{loading ? "…" : s.value}</div>
            <div className="text-xs text-muted-foreground mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" /></div>
      ) : history.length === 0 ? (
        <div className="text-center py-16 glass rounded-2xl text-muted-foreground">
          No prediction history yet. Run a prediction from Match Center to start building your history.
        </div>
      ) : (
        <div className="glass rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-white/10 text-left text-xs text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Match</th>
                  <th className="px-4 py-3 font-medium">League</th>
                  <th className="px-4 py-3 font-medium">Prediction</th>
                  <th className="px-4 py-3 font-medium">Confidence</th>
                  <th className="px-4 py-3 font-medium">Result</th>
                  <th className="px-4 py-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {history.map((h, i) => {
                  const rc = resultConfig[h.result] || resultConfig.pending;
                  return (
                    <motion.tr key={h.id || i} initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: i * 0.03 }} className="hover:bg-white/5">
                      <td className="px-4 py-3 font-medium">{h.home_team} vs {h.away_team}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        <span className="flex items-center gap-1"><Trophy className="w-3 h-3" />{h.league || "—"}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded-md bg-primary/10 text-primary text-xs font-semibold uppercase">
                          {h.prediction_1x2 === "home" ? "1" : h.prediction_1x2 === "draw" ? "X" : "2"}
                        </span>
                      </td>
                      <td className="px-4 py-3">{h.confidence != null ? `${Math.round(h.confidence)}%` : "—"}</td>
                      <td className="px-4 py-3">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs font-medium ${rc.bg} ${rc.color}`}>
                          <rc.icon className="w-3 h-3" /> {rc.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">
                        {h.viewed_at ? new Date(h.viewed_at).toLocaleDateString() : "—"}
                      </td>
                    </motion.tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
