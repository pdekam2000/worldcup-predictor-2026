import React, { useState } from "react";
import { motion } from "framer-motion";
import { BarChart3, TrendingUp, Target, Trophy } from "lucide-react";
import { AreaChart, Area, BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

const monthlyData = [
  { month: "Jan", accuracy: 68, total: 120 }, { month: "Feb", accuracy: 71, total: 135 },
  { month: "Mar", accuracy: 69, total: 142 }, { month: "Apr", accuracy: 74, total: 156 },
  { month: "May", accuracy: 72, total: 148 }, { month: "Jun", accuracy: 76, total: 162 },
];

const leagueData = [
  { league: "Premier League", accuracy: 75, predictions: 340 },
  { league: "La Liga", accuracy: 72, predictions: 280 },
  { league: "Bundesliga", accuracy: 78, predictions: 240 },
  { league: "Serie A", accuracy: 70, predictions: 260 },
  { league: "Ligue 1", accuracy: 73, predictions: 220 },
];

const pieData = [
  { name: "Correct", value: 73, color: "hsl(217, 91%, 60%)" },
  { name: "Incorrect", value: 27, color: "rgba(255,255,255,0.1)" },
];

const recentResults = [
  { match: "Arsenal vs Chelsea", prediction: "Home Win", result: "correct", confidence: 74 },
  { match: "Barcelona vs Real Madrid", prediction: "Away Win", result: "incorrect", confidence: 58 },
  { match: "Bayern vs Dortmund", prediction: "Home Win", result: "correct", confidence: 82 },
  { match: "PSG vs Marseille", prediction: "Home Win", result: "correct", confidence: 77 },
  { match: "Inter vs AC Milan", prediction: "Draw", result: "correct", confidence: 65 },
  { match: "Ajax vs PSV", prediction: "Home Win", result: "incorrect", confidence: 70 },
  { match: "Liverpool vs Man City", prediction: "Draw", result: "correct", confidence: 55 },
  { match: "Juventus vs Napoli", prediction: "Home Win", result: "correct", confidence: 68 },
];

const chartTooltipStyle = {
  contentStyle: { background: "hsl(222, 47%, 9%)", border: "1px solid rgba(255,255,255,0.1)", borderRadius: "12px", fontSize: "12px" },
  itemStyle: { color: "hsl(210, 40%, 98%)" },
  labelStyle: { color: "hsl(215, 20%, 55%)" },
};

export default function AccuracyCenter() {
  const stats = [
    { label: "Overall Accuracy", value: "73.2%", icon: Target, color: "text-green-400", bg: "bg-green-500/10" },
    { label: "Total Predictions", value: "863", icon: BarChart3, color: "text-primary", bg: "bg-primary/10" },
    { label: "Current Streak", value: "5W", icon: TrendingUp, color: "text-accent", bg: "bg-yellow-500/10" },
    { label: "Best League", value: "Bundesliga", icon: Trophy, color: "text-purple-400", bg: "bg-purple-500/10" },
  ];

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold">Accuracy Center</h1>
        <p className="text-sm text-muted-foreground mt-1">Track prediction performance across all leagues.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {stats.map((s, i) => (
          <motion.div key={i} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.1 }} className="glass rounded-xl p-4">
            <div className="flex items-center justify-between mb-3">
              <span className="text-xs text-muted-foreground">{s.label}</span>
              <div className={`w-8 h-8 rounded-lg ${s.bg} flex items-center justify-center`}>
                <s.icon className={`w-4 h-4 ${s.color}`} />
              </div>
            </div>
            <div className="text-2xl font-display font-bold">{s.value}</div>
          </motion.div>
        ))}
      </div>

      <div className="grid lg:grid-cols-5 gap-6">
        <div className="lg:col-span-3 glass rounded-xl p-5">
          <h2 className="font-display font-semibold mb-4">Monthly Accuracy</h2>
          <ResponsiveContainer width="100%" height={260}>
            <AreaChart data={monthlyData}>
              <defs>
                <linearGradient id="accGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="hsl(217, 91%, 60%)" stopOpacity={0.3} />
                  <stop offset="100%" stopColor="hsl(217, 91%, 60%)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis dataKey="month" tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <YAxis domain={[60, 85]} tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 12 }} axisLine={false} tickLine={false} />
              <Tooltip {...chartTooltipStyle} />
              <Area type="monotone" dataKey="accuracy" stroke="hsl(217, 91%, 60%)" fill="url(#accGrad)" strokeWidth={2} />
            </AreaChart>
          </ResponsiveContainer>
        </div>

        <div className="lg:col-span-2 glass rounded-xl p-5 flex flex-col items-center justify-center">
          <h2 className="font-display font-semibold mb-4 self-start">Win Rate</h2>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={pieData} innerRadius={60} outerRadius={80} dataKey="value" startAngle={90} endAngle={-270}>
                {pieData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <div className="text-center -mt-4">
            <div className="text-3xl font-display font-bold text-gradient-blue">73.2%</div>
            <div className="text-xs text-muted-foreground">Overall Win Rate</div>
          </div>
        </div>
      </div>

      <div className="glass rounded-xl p-5">
        <h2 className="font-display font-semibold mb-4">League Performance</h2>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={leagueData} layout="vertical">
            <XAxis type="number" domain={[60, 85]} tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 12 }} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="league" tick={{ fill: "hsl(215, 20%, 55%)", fontSize: 12 }} axisLine={false} tickLine={false} width={120} />
            <Tooltip {...chartTooltipStyle} />
            <Bar dataKey="accuracy" fill="hsl(217, 91%, 60%)" radius={[0, 6, 6, 0]} barSize={24} />
          </BarChart>
        </ResponsiveContainer>
      </div>

      <div className="glass rounded-xl p-5">
        <h2 className="font-display font-semibold mb-4">Recent Results</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-muted-foreground text-xs">
                <th className="pb-3 font-medium">Match</th>
                <th className="pb-3 font-medium">Prediction</th>
                <th className="pb-3 font-medium">Confidence</th>
                <th className="pb-3 font-medium">Result</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {recentResults.map((r, i) => (
                <tr key={i} className="hover:bg-white/5">
                  <td className="py-3 font-medium">{r.match}</td>
                  <td className="py-3 text-muted-foreground">{r.prediction}</td>
                  <td className="py-3">{r.confidence}%</td>
                  <td className="py-3">
                    <span className={`px-2 py-1 rounded-md text-xs font-medium ${r.result === "correct" ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400"}`}>
                      {r.result === "correct" ? "Correct" : "Incorrect"}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}