import React from "react";
import { Users, AlertCircle } from "lucide-react";

function PlayerList({ title, players, formation }) {
  if (!players?.length && !formation) return null;
  return (
    <div>
      <p className="text-xs font-semibold text-[#94A3B8] mb-1">{title}{formation ? ` (${formation})` : ""}</p>
      {players?.length ? (
        <ul className="text-sm text-[#E2E8F0] space-y-0.5">
          {players.slice(0, 11).map((p, i) => (
            <li key={i}>{typeof p === "string" ? p : p.name || p.player || "—"}</li>
          ))}
        </ul>
      ) : (
        <p className="text-xs text-[#64748B]">Lineup pending</p>
      )}
    </div>
  );
}

export default function LineupsSection({ lineups, homeTeam, awayTeam }) {
  const hasData =
    lineups?.homeXi?.length ||
    lineups?.awayXi?.length ||
    lineups?.injuries?.length ||
    lineups?.unavailable?.length;
  if (!hasData) {
    return (
      <section className="rounded-xl border border-white/[0.06] p-5 text-sm text-[#94A3B8]">
        <h2 className="text-lg font-semibold text-white flex items-center gap-2 mb-2"><Users className="w-5 h-5" /> Lineups</h2>
        Starting XI not confirmed in cached prediction.
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-white/[0.06] bg-white/[0.02] p-5 space-y-4">
      <h2 className="text-lg font-semibold text-white flex items-center gap-2"><Users className="w-5 h-5 text-[#7DD3FC]" /> Lineups</h2>
      <div className="grid md:grid-cols-2 gap-4">
        <PlayerList title={homeTeam} players={lineups.homeXi} formation={lineups.homeFormation} />
        <PlayerList title={awayTeam} players={lineups.awayXi} formation={lineups.awayFormation} />
      </div>
      {[lineups.injuries, lineups.suspensions, lineups.unavailable].map((list, idx) =>
        list?.length ? (
          <div key={idx} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
            <p className="text-xs font-semibold text-red-300 flex items-center gap-1 mb-1"><AlertCircle className="w-3.5 h-3.5" /> Unavailable</p>
            <ul className="text-xs text-[#94A3B8] space-y-0.5">
              {list.slice(0, 8).map((x, i) => (
                <li key={i}>{typeof x === "string" ? x : x.player || x.name || JSON.stringify(x)}</li>
              ))}
            </ul>
          </div>
        ) : null
      )}
    </section>
  );
}
