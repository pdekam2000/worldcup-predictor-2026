import React from "react";
import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";
import PricingContent from "@/components/pricing/PricingContent";

export default function PricingPage() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-white/10 px-4 py-4">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="w-4 h-4" /> Back to home
          </Link>
          <div className="flex gap-3">
            <Link to="/login" className="text-sm text-muted-foreground hover:text-foreground">Log in</Link>
            <Link to="/register" className="text-sm text-primary font-medium">Sign up</Link>
          </div>
        </div>
      </header>
      <main className="py-16 px-4">
        <PricingContent ctaBase="/register" />
      </main>
    </div>
  );
}
