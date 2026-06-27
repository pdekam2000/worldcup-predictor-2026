import React from "react";
import { Plus, Layers } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "react-router-dom";

export default function BetSlipActions({ summary, match, onAddBestPick, onAddCombo }) {
  return (
    <div className="flex flex-wrap gap-2 sticky bottom-20 z-30 p-3 rounded-xl border border-[#00E676]/20 bg-[#0B1220]/95 backdrop-blur-md">
      <Button
        type="button"
        className="bg-[#00E676] text-[#0B1220] hover:bg-[#00E676]/90 flex-1 sm:flex-none"
        disabled={!summary?.bestPick}
        onClick={onAddBestPick}
      >
        <Plus className="w-4 h-4 mr-1" /> Add Best Pick
      </Button>
      <Button type="button" variant="outline" className="border-white/10 flex-1 sm:flex-none" asChild>
        <Link to={`/matches/${match.fixture_id}?competition=${match.competition_key || ""}#markets`}>Add Market</Link>
      </Button>
      <Button type="button" variant="outline" className="border-white/10 flex-1 sm:flex-none" onClick={onAddCombo}>
        <Layers className="w-4 h-4 mr-1" /> Add Combo
      </Button>
    </div>
  );
}
