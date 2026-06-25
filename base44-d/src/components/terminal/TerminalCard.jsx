import React from "react";
import { cn } from "@/lib/utils";

export default function TerminalCard({ children, className, glow = false, ...props }) {
  return (
    <div
      className={cn(glow ? "terminal-card-glow" : "terminal-card", "p-4 sm:p-5", className)}
      {...props}
    >
      {children}
    </div>
  );
}
