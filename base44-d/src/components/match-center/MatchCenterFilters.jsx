import React from "react";
import { Search, Filter, Calendar, Sparkles, Radio, Clock } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";

function Chip({ active, onClick, children, icon: Icon }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors border",
        active
          ? "bg-[#3B82F6] text-white border-[#3B82F6]"
          : "bg-white/[0.04] text-[#94A3B8] border-white/[0.06] hover:bg-white/[0.08]"
      )}
    >
      {Icon ? <Icon className="w-3.5 h-3.5" /> : null}
      {children}
    </button>
  );
}

export default function MatchCenterFilters({
  search,
  onSearchChange,
  statusTab,
  onStatusTabChange,
  datePreset,
  onDatePresetChange,
  highConfidence,
  onHighConfidenceChange,
  eliteOnly,
  onEliteOnlyChange,
  liveOnly,
  onLiveOnlyChange,
  upcomingOnly,
  onUpcomingOnlyChange,
  country,
  onCountryChange,
  countries,
}) {
  return (
    <div className="space-y-3">
      <div className="flex flex-col lg:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[#94A3B8]" />
          <Input
            placeholder="Search competition, club, or national team…"
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            className="pl-10 bg-[#101827]/80 border-white/10 rounded-xl text-[#F8FAFC] backdrop-blur-sm"
          />
        </div>
        <Select value={country || "all"} onValueChange={onCountryChange}>
          <SelectTrigger className="w-full lg:w-44 bg-[#101827]/80 border-white/10 rounded-xl">
            <SelectValue placeholder="Country" />
          </SelectTrigger>
          <SelectContent className="bg-[#101827] border-white/10">
            <SelectItem value="all">All countries</SelectItem>
            {(countries || []).map((c) => (
              <SelectItem key={c} value={c}>{c}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
        <Filter className="w-4 h-4 text-[#64748B]" />
        {[
          { id: "upcoming", label: "Upcoming", icon: Clock },
          { id: "live", label: "Live", icon: Radio },
          { id: "finished", label: "Finished", icon: Calendar },
          { id: "predicted", label: "Predicted", icon: Sparkles },
        ].map((t) => (
          <Chip
            key={t.id}
            icon={t.icon}
            active={statusTab === t.id}
            onClick={() => onStatusTabChange(t.id)}
          >
            {t.label}
          </Chip>
        ))}
      </div>

      <div className="flex flex-wrap gap-2">
        <Chip active={datePreset === "today"} onClick={() => onDatePresetChange(datePreset === "today" ? "" : "today")}>Today</Chip>
        <Chip active={datePreset === "tomorrow"} onClick={() => onDatePresetChange(datePreset === "tomorrow" ? "" : "tomorrow")}>Tomorrow</Chip>
        <Chip active={datePreset === "weekend"} onClick={() => onDatePresetChange(datePreset === "weekend" ? "" : "weekend")}>Weekend</Chip>
        <Chip active={highConfidence} onClick={() => onHighConfidenceChange(!highConfidence)}>High Confidence</Chip>
        <Chip active={eliteOnly} onClick={() => onEliteOnlyChange(!eliteOnly)}>Elite Picks</Chip>
        <Chip active={liveOnly} onClick={() => onLiveOnlyChange(!liveOnly)}>Live only</Chip>
        <Chip active={upcomingOnly} onClick={() => onUpcomingOnlyChange(!upcomingOnly)}>Upcoming only</Chip>
      </div>
    </div>
  );
}
