import React from "react";
import { useParams } from "react-router-dom";
import { fetchSharePick } from "@/api/socialTrustApi";
import SharePublicLayout from "./SharePublicLayout";

export default function SharePickPage() {
  const { id } = useParams();
  return (
    <SharePublicLayout
      shareId={id}
      fetcher={fetchSharePick}
      renderPayload={(p) => (
        <div className="space-y-2 text-sm">
          <p className="text-lg font-semibold">
            {p.home_team} vs {p.away_team}
          </p>
          {p.league && <p className="text-muted-foreground">{p.league}</p>}
          <p>
            <span className="text-muted-foreground">{p.market_label || p.market}:</span>{" "}
            <strong>{p.prediction}</strong>
          </p>
          {p.bet_quality_score != null && (
            <p className="text-primary">Bet quality {p.bet_quality_score}</p>
          )}
          {p.reason && <p className="text-muted-foreground text-xs">{p.reason}</p>}
        </div>
      )}
    />
  );
}
