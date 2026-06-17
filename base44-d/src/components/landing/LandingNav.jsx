import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Zap, Menu, X } from "lucide-react";

export default function LandingNav() {
  const [open, setOpen] = useState(false);

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 glass">
      <div className="max-w-6xl mx-auto px-4 h-16 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <Zap className="w-4 h-4 text-primary-foreground" />
          </div>
          <span className="font-display font-bold text-lg hidden sm:block">WorldCup Predictor Pro</span>
        </Link>

        <div className="hidden md:flex items-center gap-8 text-sm text-muted-foreground">
          <a href="#features" className="hover:text-foreground transition-colors">Features</a>
          <a href="#pricing" className="hover:text-foreground transition-colors">Pricing</a>
          <a href="#testimonials" className="hover:text-foreground transition-colors">Testimonials</a>
          <a href="#faq" className="hover:text-foreground transition-colors">FAQ</a>
        </div>

        <div className="hidden md:flex items-center gap-3">
          <Link to="/login">
            <Button variant="ghost" size="sm" className="text-muted-foreground hover:text-foreground">Sign In</Button>
          </Link>
          <Link to="/register">
            <Button size="sm" className="rounded-lg">Get Started</Button>
          </Link>
        </div>

        <button className="md:hidden" onClick={() => setOpen(!open)}>
          {open ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
        </button>
      </div>

      {open && (
        <div className="md:hidden glass border-t border-white/10 p-4 space-y-3">
          <a href="#features" className="block py-2 text-sm text-muted-foreground" onClick={() => setOpen(false)}>Features</a>
          <a href="#pricing" className="block py-2 text-sm text-muted-foreground" onClick={() => setOpen(false)}>Pricing</a>
          <a href="#testimonials" className="block py-2 text-sm text-muted-foreground" onClick={() => setOpen(false)}>Testimonials</a>
          <a href="#faq" className="block py-2 text-sm text-muted-foreground" onClick={() => setOpen(false)}>FAQ</a>
          <div className="flex gap-3 pt-2">
            <Link to="/login" className="flex-1"><Button variant="outline" size="sm" className="w-full">Sign In</Button></Link>
            <Link to="/register" className="flex-1"><Button size="sm" className="w-full">Get Started</Button></Link>
          </div>
        </div>
      )}
    </nav>
  );
}