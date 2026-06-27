import React from "react";

export function MatchCardSkeleton() {
  return (
    <div className="rounded-2xl border border-white/[0.06] bg-[#101827]/80 p-5 animate-pulse">
      <div className="flex justify-between mb-4">
        <div className="h-3 w-24 bg-white/10 rounded" />
        <div className="h-5 w-16 bg-white/10 rounded-full" />
      </div>
      <div className="flex items-center justify-between gap-3 mb-4">
        <div className="h-10 w-10 bg-white/10 rounded-full" />
        <div className="h-4 w-20 bg-white/10 rounded" />
        <div className="h-10 w-10 bg-white/10 rounded-full" />
      </div>
      <div className="h-16 bg-white/5 rounded-xl mb-3" />
      <div className="flex gap-2">
        <div className="h-8 flex-1 bg-white/10 rounded-lg" />
        <div className="h-8 w-10 bg-white/10 rounded-lg" />
      </div>
    </div>
  );
}

export default function MatchCenterSkeleton({ count = 6 }) {
  return (
    <div className="grid sm:grid-cols-2 xl:grid-cols-3 gap-4">
      {Array.from({ length: count }).map((_, i) => (
        <MatchCardSkeleton key={i} />
      ))}
    </div>
  );
}
