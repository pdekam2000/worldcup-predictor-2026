import React, { useRef } from "react";
import { ChevronLeft, ChevronRight, Star } from "lucide-react";
import { cn } from "@/lib/utils";
import SafeImage from "@/components/ui/SafeImage";
import { competitionBadgeLabel, resolveCompetitionLogo } from "@/lib/imageResolver";
export default function LeagueSelector({ competitions, selectedKey, onSelect, totalUpcoming }) {
  const scrollRef = useRef(null);

  const scroll = (dir) => {
    scrollRef.current?.scrollBy({ left: dir * 220, behavior: "smooth" });
  };

  const items = [
    {
      key: "all",
      name: "All Matches",
      emoji: "⭐",
      upcoming_count: totalUpcoming,
    },
    ...(competitions || []),
  ];

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => scroll(-1)}
        className="hidden md:flex absolute left-0 top-1/2 -translate-y-1/2 z-10 w-8 h-8 items-center justify-center rounded-full bg-[#0B1220]/90 border border-white/10 text-[#94A3B8] hover:text-white"
        aria-label="Scroll leagues left"
      >
        <ChevronLeft className="w-4 h-4" />
      </button>
      <div
        ref={scrollRef}
        className="flex gap-3 overflow-x-auto pb-2 scroll-smooth snap-x snap-mandatory scrollbar-thin px-1 md:px-10"
      >
        {items.map((comp) => {
          const active = selectedKey === comp.key;
          return (
            <button
              key={comp.key}
              type="button"
              onClick={() => onSelect(comp.key)}
              className={cn(
                "snap-start shrink-0 min-w-[148px] rounded-2xl border p-3 text-left transition-all duration-200",
                "backdrop-blur-md bg-white/[0.03]",
                active
                  ? "border-[#00E676]/40 bg-[#00E676]/10 shadow-[0_0_24px_rgba(0,230,118,0.12)]"
                  : "border-white/[0.06] hover:border-white/15 hover:bg-white/[0.05]"
              )}
            >
              <div className="flex items-center gap-2 mb-2">
                <span className="text-xl leading-none">{comp.emoji || "⚽"}</span>
                {resolveCompetitionLogo(comp) ? (
                  <SafeImage
                    src={resolveCompetitionLogo(comp)}
                    alt={comp.name || "League"}
                    fallbackText={competitionBadgeLabel(comp)}
                    className="w-6 h-6 rounded"
                    fallbackClassName="text-[9px]"
                  />
                ) : (
                  <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-white/5 text-[#94A3B8]">
                    {competitionBadgeLabel(comp)}
                  </span>
                )}
              </div>              <p className="text-sm font-semibold text-[#F8FAFC] leading-tight line-clamp-2">{comp.name}</p>
              <p className="text-[11px] text-[#94A3B8] mt-1">
                {comp.upcoming_count ?? 0} upcoming
                {comp.upcoming_count === 0 && comp.zero_fixture_reason && (
                  <span className="block text-[10px] text-[#64748B] capitalize">
                    {String(comp.zero_fixture_reason).replace(/_/g, " ")}
                  </span>
                )}
              </p>
            </button>
          );
        })}
      </div>
      <button
        type="button"
        onClick={() => scroll(1)}
        className="hidden md:flex absolute right-0 top-1/2 -translate-y-1/2 z-10 w-8 h-8 items-center justify-center rounded-full bg-[#0B1220]/90 border border-white/10 text-[#94A3B8] hover:text-white"
        aria-label="Scroll leagues right"
      >
        <ChevronRight className="w-4 h-4" />
      </button>
      {selectedKey === "all" && (
        <p className="text-[10px] text-[#64748B] mt-1 flex items-center gap-1">
          <Star className="w-3 h-3" /> Aggregated across all enabled API competitions
        </p>
      )}
    </div>
  );
}
