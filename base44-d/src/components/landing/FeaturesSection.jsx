import React from "react";
import { motion } from "framer-motion";
import { Brain, Target, TrendingUp, Gauge, FileText, Crown } from "lucide-react";

const features = [
  { icon: Brain, title: "Multi-Agent Analysis", desc: "10 specialist AI models analyze every dimension — form, injuries, tactics, weather, and more.", color: "text-blue-400", bg: "bg-blue-500/10" },
  { icon: Target, title: "Match Predictions", desc: "Precise 1X2 predictions with probability breakdowns for every match outcome.", color: "text-green-400", bg: "bg-green-500/10" },
  { icon: TrendingUp, title: "Over / Under", desc: "Goal market predictions with confidence scores for over/under 2.5 and BTTS markets.", color: "text-purple-400", bg: "bg-purple-500/10" },
  { icon: Gauge, title: "Confidence Scores", desc: "Every prediction backed by a confidence percentage so you know the strength of each pick.", color: "text-cyan-400", bg: "bg-cyan-500/10" },
  { icon: FileText, title: "Match Intelligence", desc: "Detailed AI-generated match reports explaining the reasoning behind every prediction.", color: "text-orange-400", bg: "bg-orange-500/10" },
  { icon: Crown, title: "Premium Analytics", desc: "Advanced reports, historical accuracy data, and league-level performance breakdowns.", color: "text-accent", bg: "bg-yellow-500/10" },
];

export default function FeaturesSection() {
  return (
    <section className="py-24 px-4 relative" id="features">
      <div className="max-w-6xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          className="text-center mb-16"
        >
          <span className="text-primary text-sm font-semibold tracking-widest uppercase">Features</span>
          <h2 className="text-3xl sm:text-4xl font-display font-bold mt-3 mb-4">
            Powered by <span className="text-gradient-blue">Advanced AI</span>
          </h2>
          <p className="text-muted-foreground max-w-xl mx-auto">
            Our multi-agent system combines 10 specialist models to deliver the most comprehensive match analysis available.
          </p>
        </motion.div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {features.map((f, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true }}
              transition={{ delay: i * 0.1 }}
              className="glass rounded-2xl p-6 hover:bg-white/10 transition-all duration-300 group cursor-default"
            >
              <div className={`w-12 h-12 ${f.bg} rounded-xl flex items-center justify-center mb-4 group-hover:scale-110 transition-transform`}>
                <f.icon className={`w-6 h-6 ${f.color}`} />
              </div>
              <h3 className="text-lg font-display font-semibold mb-2">{f.title}</h3>
              <p className="text-sm text-muted-foreground leading-relaxed">{f.desc}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  );
}