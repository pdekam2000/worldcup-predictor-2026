import React, { useState, useEffect, useRef } from "react";
import { motion, useInView } from "framer-motion";

function AnimatedCounter({ end, suffix = "", duration = 2000 }) {
  const [count, setCount] = useState(0);
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true });

  useEffect(() => {
    if (!isInView) return;
    let start = 0;
    const step = end / (duration / 16);
    const timer = setInterval(() => {
      start += step;
      if (start >= end) {
        setCount(end);
        clearInterval(timer);
      } else {
        setCount(Math.floor(start));
      }
    }, 16);
    return () => clearInterval(timer);
  }, [isInView, end, duration]);

  return <span ref={ref}>{count.toLocaleString()}{suffix}</span>;
}

const stats = [
  { value: 24580, suffix: "+", label: "Predictions Generated" },
  { value: 8432, suffix: "+", label: "Matches Analyzed" },
  { value: 12750, suffix: "+", label: "Active Users" },
  { value: 73, suffix: "%", label: "Accuracy Rate" },
];

export default function StatsSection() {
  return (
    <section className="py-20 px-4 relative">
      <div className="absolute inset-0 bg-gradient-to-b from-transparent via-primary/5 to-transparent" />
      <div className="max-w-5xl mx-auto relative z-10">
        <div className="glass rounded-2xl p-8 sm:p-12">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-8">
            {stats.map((s, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.9 }}
                whileInView={{ opacity: 1, scale: 1 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.15 }}
                className="text-center"
              >
                <div className="text-3xl sm:text-4xl font-display font-bold text-gradient-blue">
                  <AnimatedCounter end={s.value} suffix={s.suffix} />
                </div>
                <div className="text-sm text-muted-foreground mt-2">{s.label}</div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}