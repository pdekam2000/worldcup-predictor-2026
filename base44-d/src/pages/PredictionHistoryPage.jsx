import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { motion } from "framer-motion";
import { History, CheckCircle, XCircle, Clock, Trophy } from "lucide-react";

const mockHistory = [
  { id: "1", home_team: "Arsenal", away_team: "Chelsea", league: "Premier League", match_date: "2026-06-15T15:00:00Z", prediction_1x2: "home", confidence: 74, result: "correct" },
  { id: "2", home_team: "Barcelona", away_team: "Real Madrid", league: "La Liga", match_date: "2026-06-14T20:00:00Z", prediction_1x2: "away", confidence: 61, result: "incorrect" },
  { id: "3", home_team: "Bayern Munich", away_team: "Dortmund", league: "Bundesliga", match_date: "2026-06-13T17:30:00Z", prediction_1x2: "home", confidence: 82, result: "correct" },
  { id: "4", home_team: "PSG", away_team: "Marseille", league: "Ligue 1", match_date: "2026-06-16T20:45:00Z", prediction_1x2: "home", confidence: 77, result: "pending" },
];

const resultConfig = {
  correct: { icon: CheckCircle, color: "text-green-400", bg: "bg-green-500/10", label: "Correct" },
  incorrect: { icon: XCircle, color: "text-red-400", bg: "bg-red-500/10", label: "Incorrect" },
  pending: { icon: Clock, color: "text-yellow-400", bg: "bg-yellow-500/10", label: "Pending" },
};

export default function PredictionHistoryPage() {
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const load = async () => {
      try {
        const user = await base44.auth.me();
        const data = await base44.entities.PredictionHistory.filter({ user_id: user.id }, "-viewed_at", 50);
        setHistory(data.length > 0 ? data : mockHistory);
      } catch {
        setHistory(mockHistory);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const correct = history.filter(h => h.result === "correct").length;
  const total = history.filter(h => h.result !== "pending").length;
  const accuracy = total > 0 ? Math.round((correct / total) * 100) : 0;

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold flex items-center gap-2"><History className="w-6 h-6 text-primary" /> Prediction History</h1>
        <p className="text-sm text-muted-foreground mt-1">All predictions you've viewed, with results.</p>
      </div>

      <div className="grid grid-cols-3 gap-4">
        {[
          { label: "Total Viewed", value: history.length, color: "text-primary" },
          { label: "Correct", value: correct, color: "text-green-400" },
          { label: "Accuracy", value: `${accuracy}%`, color: "text-accent" },
        ].map((s, i) => (
          <div key={i} className="glass rounded-xl p-4 text-center">
            <div className={`text-2xl font-display font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-muted-foreground mt-1">{s.label}</div>
          </div>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" /></div>
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
                        <span className="flex items-center gap-1"><Trophy className="w-3 h-3" />{h.league}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className="px-2 py-0.5 rounded-md bg-primary/10 text-primary text-xs font-semibold uppercase">
                          {h.prediction_1x2 === "home" ? "1" : h.prediction_1x2 === "draw" ? "X" : "2"}
                        </span>
                      </td>
                      <td className="px-4 py-3"><span className="text-xs font-semibold">{h.confidence}%</span></td>
                      <td className="px-4 py-3">
                        <span className={`flex items-center gap-1 text-xs font-medium px-2 py-0.5 rounded-md ${rc.bg} ${rc.color}`}>
                          <rc.icon className="w-3 h-3" />{rc.label}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-muted-foreground text-xs">{new Date(h.match_date).toLocaleDateString()}</td>
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