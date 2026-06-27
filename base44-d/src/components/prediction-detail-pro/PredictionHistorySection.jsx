import React from "react";
import { Link } from "react-router-dom";
import { History, CheckCircle2, XCircle } from "lucide-react";

export default function PredictionHistorySection({ history, fixtureId, accuracy }) {
  const tracking = accuracy || {};
  return (
    <section className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-4">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2"><History className="w-5 h-5 text-[#94A3B8]" /> Prediction History</h2>

      {tracking.evaluated != null || tracking.result || tracking.result_status ? (
        <div className="rounded-lg border border-white/[0.06] p-4">
          <p className="text-sm font-medium text-[#F8FAFC] mb-2">Latest evaluation</p>
          <div className="flex items-center gap-2 text-sm">
            {tracking.result_status === "correct" || tracking.correct || tracking.result === "correct" ? (
              <CheckCircle2 className="w-4 h-4 text-[#00E676]" />
            ) : tracking.result_status === "partial" ? (
              <CheckCircle2 className="w-4 h-4 text-violet-400" />
            ) : (
              <XCircle className="w-4 h-4 text-red-400" />
            )}
            <span className="text-[#94A3B8]">
              {tracking.result_status || tracking.result || (tracking.correct ? "Correct" : "Incorrect")}
            </span>
            {tracking.final_score && <span className="text-[#64748B]">· FT {tracking.final_score}</span>}
            {tracking.accuracy_pct != null && <span className="text-[#64748B]">· Accuracy {tracking.accuracy_pct}%</span>}
          </div>
        </div>
      ) : (
        <p className="text-sm text-[#64748B]">Match not yet evaluated.</p>
      )}

      {history?.length > 0 ? (
        <ul className="space-y-2">
          {history.slice(0, 5).map((h) => (
            <li key={h.entry_id || h.id} className="text-sm border-b border-white/[0.04] pb-2">
              <Link to={`/archive/${h.entry_id || h.id}`} className="text-[#00E676] hover:underline">
                {h.predicted_1x2 || h.prediction || "Prediction"} · {h.created_at?.slice(0, 10) || h.date}
              </Link>
              {h.evaluation_status && <span className="text-[#64748B] ml-2">{h.evaluation_status}</span>}
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-[#64748B]">
          <Link to={`/archive/global-${fixtureId}`} className="text-[#7DD3FC] hover:underline">View full archive entry</Link>
          {" · "}
          <Link to="/archive" className="text-[#7DD3FC] hover:underline">All predictions</Link>
        </p>
      )}
    </section>
  );
}
