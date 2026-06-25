import React from "react";
import { Link } from "react-router-dom";
import { ShieldOff } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Generic access denied — Phase 37A (no admin feature details). */
export default function AccessDenied() {
  return (
    <div className="flex flex-col items-center justify-center py-24 px-4 text-center">
      <div className="w-14 h-14 rounded-2xl bg-white/5 flex items-center justify-center mb-4">
        <ShieldOff className="w-7 h-7 text-muted-foreground" />
      </div>
      <h1 className="text-xl font-display font-semibold">Access denied.</h1>
      <p className="text-sm text-muted-foreground mt-2 max-w-sm">
        You do not have permission to view this page.
      </p>
      <Button asChild variant="outline" className="mt-6">
        <Link to="/dashboard">Return to dashboard</Link>
      </Button>
    </div>
  );
}
