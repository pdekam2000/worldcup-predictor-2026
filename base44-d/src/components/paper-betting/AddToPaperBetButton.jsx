import React, { useState } from "react";
import { NotebookPen } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { placePaperBet, placePaperCombo } from "@/api/paperBettingApi";
import { useAuth } from "@/lib/AuthContext";
import { Button } from "@/components/ui/button";

/**
 * Add to virtual paper bet slip (simulation only).
 */
export default function AddToPaperBetButton({
  bet,
  combo,
  label = "Add to Paper Bet",
  size = "sm",
  variant = "outline",
  className = "",
  onSuccess,
}) {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [msg, setMsg] = useState(null);

  const handleClick = async () => {
    if (!isAuthenticated) {
      navigate("/login");
      return;
    }
    setLoading(true);
    setMsg(null);
    try {
      if (combo?.legs?.length) {
        await placePaperCombo({
          legs: combo.legs.map((leg) => ({
            fixture_id: leg.fixture_id,
            market: leg.market,
            prediction: leg.prediction || leg.selection,
            odds_decimal: leg.odds_decimal,
            odds_estimated: leg.odds_estimated,
            bet_quality_score: leg.bet_quality_score,
            competition_key: leg.competition_key,
            home_team: leg.home_team,
            away_team: leg.away_team,
            snapshot_id: leg.snapshot_id,
          })),
          combo_type: combo.combo_type || combo.type || "balanced",
          source_page: combo.source_page,
        });
      } else if (bet) {
        await placePaperBet({
          fixture_id: bet.fixture_id,
          market: bet.market || "1x2",
          prediction: bet.prediction || bet.selection,
          stake: bet.stake,
          odds_decimal: bet.odds_decimal,
          odds_estimated: bet.odds_estimated,
          bet_quality_score: bet.bet_quality_score,
          source_page: bet.source_page,
          snapshot_id: bet.snapshot_id,
          competition_key: bet.competition_key,
          home_team: bet.home_team,
          away_team: bet.away_team,
        });
      }
      setMsg("Added");
      onSuccess?.();
    } catch (err) {
      const detail = err.message || "Failed";
      if (detail.includes("no_account") || detail.includes("bankroll")) {
        navigate("/paper-betting");
      } else {
        setMsg(detail.slice(0, 40));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="inline-flex flex-col items-start gap-0.5">
      <Button type="button" size={size} variant={variant} className={className} onClick={handleClick} disabled={loading}>
        <NotebookPen className="w-3.5 h-3.5 mr-1" />
        {loading ? "Adding…" : label}
      </Button>
      {msg && <span className="text-[10px] text-[#94A3B8]">{msg}</span>}
    </div>
  );
}
