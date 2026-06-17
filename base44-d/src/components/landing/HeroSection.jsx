import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { ArrowRight, Play, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function HeroSection() {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden px-4 pt-20">
      {/* Background effects */}
      <div className="absolute inset-0">
        <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-primary/20 rounded-full blur-3xl animate-pulse" />
        <div className="absolute bottom-1/4 right-1/4 w-80 h-80 bg-blue-600/15 rounded-full blur-3xl animate-pulse delay-1000" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-primary/5 rounded-full blur-3xl" />
      </div>
      
      {/* Grid pattern */}
      <div className="absolute inset-0 bg-[linear-gradient(rgba(59,130,246,0.03)_1px,transparent_1px),linear-gradient(90deg,rgba(59,130,246,0.03)_1px,transparent_1px)] bg-[size:60px_60px]" />

      <div className="relative z-10 max-w-6xl mx-auto text-center">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6 }}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-full glass mb-8"
        >
          <Sparkles className="w-4 h-4 text-accent" />
          <span className="text-sm font-medium text-muted-foreground">WorldCup Predictor Pro 2026</span>
        </motion.div>

        <motion.h1
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.1 }}
          className="text-5xl sm:text-6xl lg:text-7xl font-display font-bold leading-tight mb-6"
        >
          <span className="text-foreground">AI-Powered Football</span>
          <br />
          <span className="text-gradient-blue">Predictions</span>
        </motion.h1>

        <motion.p
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.2 }}
          className="text-lg sm:text-xl text-muted-foreground max-w-2xl mx-auto mb-10"
        >
          Advanced multi-agent analysis for football matches worldwide. 
          Powered by 10 specialist AI models analyzing every dimension of the game.
        </motion.p>

        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, delay: 0.3 }}
          className="flex flex-col sm:flex-row gap-4 justify-center"
        >
          <Link to="/register">
            <Button size="lg" className="px-8 py-6 text-base font-semibold glow-blue rounded-xl">
              Get Started
              <ArrowRight className="w-5 h-5 ml-2" />
            </Button>
          </Link>
          <Link to="/login">
            <Button variant="outline" size="lg" className="px-8 py-6 text-base font-semibold rounded-xl border-white/10 hover:bg-white/5">
              <Play className="w-5 h-5 mr-2" />
              View Predictions
            </Button>
          </Link>
        </motion.div>

        {/* Dashboard preview */}
        <motion.div
          initial={{ opacity: 0, y: 60 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.9, delay: 0.5 }}
          className="mt-16 relative"
        >
          <div className="glass rounded-2xl p-1 glow-blue">
            <div className="bg-card rounded-xl p-6 space-y-4">
              <div className="flex items-center gap-3 mb-4">
                <div className="w-3 h-3 rounded-full bg-red-500" />
                <div className="w-3 h-3 rounded-full bg-yellow-500" />
                <div className="w-3 h-3 rounded-full bg-green-500" />
                <span className="text-xs text-muted-foreground ml-2">WorldCup Predictor Pro — Dashboard</span>
              </div>
              <div className="grid grid-cols-3 gap-4">
                {[
                  { label: "Today's Matches", value: "12", color: "text-primary" },
                  { label: "Win Rate", value: "73.2%", color: "text-green-400" },
                  { label: "Active Predictions", value: "48", color: "text-accent" },
                ].map((stat, i) => (
                  <div key={i} className="glass rounded-lg p-4 text-center">
                    <div className={`text-2xl font-bold font-display ${stat.color}`}>{stat.value}</div>
                    <div className="text-xs text-muted-foreground mt-1">{stat.label}</div>
                  </div>
                ))}
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div className="glass rounded-lg p-4 h-32 flex items-center justify-center">
                  <div className="text-center">
                    <div className="text-xs text-muted-foreground mb-2">Next Match</div>
                    <div className="font-semibold text-sm">Brazil vs Germany</div>
                    <div className="text-primary text-xs mt-1">87% Confidence</div>
                  </div>
                </div>
                <div className="glass rounded-lg p-4 h-32 flex items-center justify-center">
                  <div className="w-full space-y-2">
                    <div className="text-xs text-muted-foreground mb-2 text-center">Accuracy Trend</div>
                    <div className="flex items-end gap-1 justify-center h-16">
                      {[40, 55, 45, 70, 65, 80, 75, 85, 78, 82].map((h, i) => (
                        <div key={i} className="w-3 bg-primary/60 rounded-t" style={{ height: `${h}%` }} />
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="absolute -bottom-8 left-1/2 -translate-x-1/2 w-3/4 h-16 bg-primary/20 blur-3xl rounded-full" />
        </motion.div>
      </div>
    </section>
  );
}