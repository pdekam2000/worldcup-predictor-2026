import React from "react";
import { useParams } from "react-router-dom";
import { fetchSharePaperReport } from "@/api/socialTrustApi";
import SharePublicLayout from "./SharePublicLayout";

export default function SharePaperReportPage() {
  const { id } = useParams();
  return (
    <SharePublicLayout
      shareId={id}
      fetcher={fetchSharePaperReport}
      renderPayload={(p) => (
        <div className="space-y-2 text-sm">
          <p className="text-xs uppercase text-muted-foreground">Anonymized virtual portfolio</p>
          {p.headline && <p className="font-medium">{p.headline}</p>}
          <div className="grid grid-cols-2 gap-2 mt-2">
            <div>
              <p className="text-muted-foreground">ROI</p>
              <p className="text-xl font-bold">{p.roi_pct != null ? `${p.roi_pct}%` : "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Win rate</p>
              <p className="text-xl font-bold">{p.winrate != null ? `${p.winrate}%` : "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Net P/L</p>
              <p className="text-lg font-mono">{p.net_profit_loss ?? "—"}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Bets</p>
              <p className="text-lg">{p.total_bets ?? "—"}</p>
            </div>
          </div>
          {p.best_market && <p className="text-muted-foreground">Best market: {p.best_market}</p>}
        </div>
      )}
    />
  );
}
