import React from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import { Target, BarChart3, Layers, ShieldAlert } from "lucide-react";
import { TRUST_NO_GUARANTEE } from "@/lib/trustCopy";

const blocks = [
  {
    icon: Target,
    title: "What you get",
    body: "Pick any fixture in Match Center and run a full multi-market analysis — 1X2, over/under, BTTS, and more — with confidence tiers and plain-language reasoning.",
  },
  {
    icon: Layers,
    title: "Prediction markets",
    body: "Each market is scored separately. Program best bets are flagged when the model sees a strong edge; other probabilities stay available for research without being promoted as picks.",
  },
  {
    icon: BarChart3,
    title: "Best Bet Winrate",
    body: "Our public winrate counts evaluated program best bets only — not every probability the model outputs. Sample size grows as World Cup fixtures finish.",
    link: { to: "/public/accuracy", label: "View public accuracy archive" },
  },
  {
    icon: ShieldAlert,
    title: "No guaranteed profit",
    body: TRUST_NO_GUARANTEE,
  },
];

export default function UnderstandingSection() {
  return (
    <section className="py-20 px-4" id="how-it-works">
      <div className="max-w-5xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-12"
        >
          <span className="text-primary text-sm font-semibold tracking-widest uppercase">How it works</span>
          <h2 className="text-3xl sm:text-4xl font-display font-bold mt-3 mb-4">
            Built for clarity, not hype
          </h2>
          <p className="text-muted-foreground max-w-2xl mx-auto text-sm sm:text-base">
            WorldCup Predictor is a research platform for football match analysis — invite-only during soft launch.
          </p>
        </motion.div>

        <div className="grid sm:grid-cols-2 gap-5">
          {blocks.map((b, i) => (
            <motion.div
              key={b.title}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.08 }}
              className="wc-premium-card p-6"
            >
              <b.icon className="w-6 h-6 text-amber-700 mb-3" />
              <h3 className="font-display font-semibold text-slate-900 mb-2">{b.title}</h3>
              <p className="text-sm text-slate-600 leading-relaxed">{b.body}</p>
              {b.link && (
                <Link to={b.link.to} className="inline-block text-sm text-amber-800 font-medium mt-3 hover:underline">
                  {b.link.label} →
                </Link>
              )}
            </motion.div>
          ))}
        </div>

        <motion.div
          initial={{ opacity: 0 }}
          whileInView={{ opacity: 1 }}
          viewport={{ once: true }}
          className="mt-10 flex flex-col sm:flex-row gap-3 justify-center"
        >
          <Link
            to="/register"
            className="inline-flex items-center justify-center px-6 py-3 rounded-xl bg-gradient-to-r from-amber-400 to-yellow-500 text-[#14181f] font-semibold text-sm hover:opacity-95 transition-opacity"
          >
            Create free account
          </Link>
          <Link
            to="/login"
            className="inline-flex items-center justify-center px-6 py-3 rounded-xl border border-amber-200 text-slate-700 font-semibold text-sm hover:bg-amber-50 transition-colors"
          >
            Sign in
          </Link>
        </motion.div>
      </div>
    </section>
  );
}
