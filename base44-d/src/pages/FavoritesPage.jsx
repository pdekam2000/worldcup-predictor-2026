import React, { useState, useEffect } from "react";
import { base44 } from "@/api/base44Client";
import { motion } from "framer-motion";
import { Heart, Trophy, Users, Calendar, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";

const mockFavorites = [
  { id: "1", type: "team", item_name: "Arsenal", item_meta: "Premier League" },
  { id: "2", type: "team", item_name: "Barcelona", item_meta: "La Liga" },
  { id: "3", type: "league", item_name: "Premier League", item_meta: "England" },
  { id: "4", type: "league", item_name: "Bundesliga", item_meta: "Germany" },
];

const typeConfig = {
  team: { icon: Users, color: "text-primary", bg: "bg-primary/10", label: "Team" },
  league: { icon: Trophy, color: "text-accent", bg: "bg-yellow-500/10", label: "League" },
  match: { icon: Calendar, color: "text-green-400", bg: "bg-green-500/10", label: "Match" },
};

export default function FavoritesPage() {
  const [favorites, setFavorites] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState("all");

  useEffect(() => {
    const load = async () => {
      try {
        const user = await base44.auth.me();
        const data = await base44.entities.Favorite.filter({ user_id: user.id }, "-created_date", 50);
        setFavorites(data.length > 0 ? data : mockFavorites);
      } catch {
        setFavorites(mockFavorites);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleRemove = async (id) => {
    try {
      await base44.entities.Favorite.delete(id);
      setFavorites(prev => prev.filter(f => f.id !== id));
    } catch {
      setFavorites(prev => prev.filter(f => f.id !== id));
    }
  };

  const filtered = filter === "all" ? favorites : favorites.filter(f => f.type === filter);

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-display font-bold flex items-center gap-2"><Heart className="w-6 h-6 text-red-400" /> Favorites</h1>
        <p className="text-sm text-muted-foreground mt-1">Your followed teams, leagues, and matches.</p>
      </div>

      <div className="flex gap-2">
        {["all", "team", "league", "match"].map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-all capitalize ${filter === f ? "bg-primary text-primary-foreground" : "glass text-muted-foreground hover:text-foreground"}`}>
            {f}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-16"><div className="w-8 h-8 border-4 border-primary/20 border-t-primary rounded-full animate-spin" /></div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-16 glass rounded-2xl">
          <Heart className="w-12 h-12 mx-auto mb-3 text-muted-foreground opacity-30" />
          <p className="text-muted-foreground">No favorites yet. Add teams and leagues from Match Center.</p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-3">
          {filtered.map((fav, i) => {
            const tc = typeConfig[fav.type] || typeConfig.team;
            return (
              <motion.div key={fav.id || i} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.04 }}
                className="glass rounded-xl p-4 flex items-center justify-between group">
                <div className="flex items-center gap-3">
                  <div className={`w-10 h-10 rounded-xl ${tc.bg} flex items-center justify-center`}>
                    <tc.icon className={`w-5 h-5 ${tc.color}`} />
                  </div>
                  <div>
                    <div className="font-medium text-sm">{fav.item_name}</div>
                    <div className="text-xs text-muted-foreground">{fav.item_meta}</div>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${tc.bg} ${tc.color}`}>{tc.label}</span>
                  <button onClick={() => handleRemove(fav.id)} className="opacity-0 group-hover:opacity-100 transition-opacity text-muted-foreground hover:text-red-400 p-1">
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
}