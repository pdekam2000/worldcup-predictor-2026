import React, { useState } from "react";
import { LANGUAGES, getLang, setLang } from "@/lib/i18n";
import { Globe } from "lucide-react";

export default function LanguageSwitcher({ compact = false }) {
  const [open, setOpen] = useState(false);
  const current = LANGUAGES.find(l => l.code === getLang()) || LANGUAGES[0];

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs text-muted-foreground hover:text-foreground hover:bg-white/5 transition-all border border-white/10"
      >
        <Globe className="w-3.5 h-3.5" />
        {!compact && <span>{current.flag} {current.code.toUpperCase()}</span>}
        {compact && <span>{current.flag}</span>}
      </button>
      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="absolute right-0 mt-1 w-44 glass-strong border border-white/10 rounded-xl shadow-xl z-50 overflow-hidden">
            {LANGUAGES.map(l => (
              <button
                key={l.code}
                onClick={() => { setLang(l.code); setOpen(false); }}
                className={`w-full flex items-center gap-2 px-3 py-2 text-xs hover:bg-white/10 transition-all ${l.code === current.code ? "text-primary font-semibold" : "text-muted-foreground"}`}
              >
                <span>{l.flag}</span>
                <span>{l.label}</span>
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}