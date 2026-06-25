import React from "react";
import { motion } from "framer-motion";

export default function MetricCard({ label, value, hint, icon: Icon, color, bg, index = 0, loading }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: index * 0.05 }}
      className="glass rounded-xl p-4"
    >
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs text-muted-foreground">{label}</span>
        {Icon && (
          <div className={`w-8 h-8 rounded-lg ${bg} flex items-center justify-center`}>
            <Icon className={`w-4 h-4 ${color}`} />
          </div>
        )}
      </div>
      <div className="text-2xl font-display font-bold tabular-nums">
        {loading ? "…" : value}
      </div>
      {hint && <p className="text-[10px] text-muted-foreground mt-1">{hint}</p>}
    </motion.div>
  );
}
