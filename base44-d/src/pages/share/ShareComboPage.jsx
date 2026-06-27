import React from "react";
import { useParams } from "react-router-dom";
import { fetchShareCombo } from "@/api/socialTrustApi";
import SharePublicLayout from "./SharePublicLayout";

export default function ShareComboPage() {
  const { id } = useParams();
  return (
    <SharePublicLayout
      shareId={id}
      fetcher={fetchShareCombo}
      renderPayload={(p) => (
        <div className="space-y-3 text-sm">
          <p className="text-lg font-semibold capitalize">{p.label || p.combo_type || "Combo"}</p>
          {p.combined_odds && <p className="text-muted-foreground">Combined odds ~{p.combined_odds}</p>}
          <ul className="space-y-2">
            {(p.legs || []).map((leg, i) => (
              <li key={i} className="glass rounded-lg p-2">
                <p className="font-medium">
                  {leg.home_team} vs {leg.away_team}
                </p>
                <p className="text-muted-foreground">
                  {leg.market_label || leg.market}: {leg.prediction}
                  {leg.bet_quality_score != null && ` · Q${leg.bet_quality_score}`}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    />
  );
}
