import React from "react";
import { Loader2 } from "lucide-react";

export default function PageLoadingState({ label = "Loading…", className = "" }) {
  return (
    <div className={`flex flex-col items-center justify-center py-16 gap-3 ${className}`}>
      <Loader2 className="w-8 h-8 text-amber-600 animate-spin" />
      <p className="text-sm text-slate-600">{label}</p>
    </div>
  );
}
