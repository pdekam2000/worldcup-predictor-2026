import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Play, Sparkles, Trophy } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function HeroSection() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden px-4 pt-20">
      <div className="absolute inset-0">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-amber-400/15 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-yellow-300/10 rounded-full blur-3xl animate-pulse delay-1000" />
      </div>

      <div className="relative z-10 max-w-6xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full border border-amber-200/60 bg-white/80 mb-8"
        >
          <Sparkles className="w-4 h-4 text-amber-600" />
          <span className="text-sm font-medium text-slate-600">World Cup 2026 · Premium football analytics</span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="text-5xl sm:text-6xl lg:text-7xl font-display font-bold leading-tight mb-6"
        >
          <span className="text-slate-900">AI football predictions</span>
          <br />
          <span className="terminal-gradient-text">built for clarity</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="text-lg sm:text-xl text-slate-600 max-w-2xl mx-auto mb-10"
        >
          Multi-market match analysis with confidence tiers, best-bet filtering, and a public accuracy archive.
          Analytical entertainment — not betting advice.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.3 }}
          className="flex flex-col sm:flex-row gap-4 justify-center"
        >
          <Link to="/register">
            <Button size="lg" className="px-8 py-6 text-base font-semibold glow-gold rounded-xl">
              Get Started
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </Link>
          <Link to="/login">
            <Button variant="outline" size="lg" className="px-8 py-6 text-base font-semibold rounded-xl border-amber-200 hover:bg-amber-50">
              Sign In
            </Button>
          </Link>
          <Link to="/public/accuracy">
            <Button variant="outline" size="lg" className="px-8 py-6 text-base font-semibold rounded-xl border-amber-200 hover:bg-amber-50">
              <Play className="w-5 h-5 mr-2" />
              View public accuracy
            </Button>
          </Link>
        </motion.div>

        <motion.p
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.45 }}
          className="text-xs text-slate-500 mt-4"
        >
          Soft launch — invite code required.{" "}
          <Link to="/contact" className="text-amber-800 hover:underline">Request access</Link>
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 60 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.5 }}
          className="mt-16 relative"
        >
          <div className="wc-premium-card p-1 glow-gold">
            <div className="bg-white rounded-xl p-6 space-y-4">
              <div className="flex items-center gap-3 mb-4">
                <Trophy className="w-4 h-4 text-amber-600" />
                <span className="text-xs text-slate-500">Match Center preview</span>
              </div>
              <div className="grid grid-cols-3 gap-4">
                {[
                  { label: "Markets per match", value: "10+", color: "text-amber-700" },
                  { label: "Best bet filter", value: "Live", color: "text-emerald-700" },
                  { label: "Public winrate", value: "Tracked", color: "text-slate-800" },
                ].map((stat) => (
                  <div key={stat.label} className="rounded-lg border border-amber-100 bg-amber-50/50 p-4 text-center">
                    <div className={`text-xl font-bold font-display ${stat.color}`}>{stat.value}</div>
                    <div className="text-xs text-slate-500 mt-1">{stat.label}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}
