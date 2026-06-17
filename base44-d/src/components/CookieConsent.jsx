import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Cookie, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTranslation } from "@/lib/i18n";
import { Link } from "react-router-dom";

export default function CookieConsent() {
  const [visible, setVisible] = useState(false);
  const { tr } = useTranslation();

  useEffect(() => {
    const consent = localStorage.getItem("cookie_consent");
    if (!consent) setTimeout(() => setVisible(true), 1500);
  }, []);

  const accept = () => { localStorage.setItem("cookie_consent", "accepted"); setVisible(false); };
  const decline = () => { localStorage.setItem("cookie_consent", "declined"); setVisible(false); };

  return (
    <AnimatePresence>
      {visible && (
        <motion.div
          initial={{ y: 100, opacity: 0 }}
          animate={{ y: 0, opacity: 1 }}
          exit={{ y: 100, opacity: 0 }}
          className="fixed bottom-4 left-4 right-4 md:left-auto md:right-6 md:max-w-md z-50"
        >
          <div className="glass-strong rounded-2xl p-5 border border-white/15 shadow-2xl">
            <div className="flex items-start gap-3 mb-4">
              <Cookie className="w-5 h-5 text-accent flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-sm mb-1">{tr.cookieTitle} 🍪</p>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  {tr.cookieText}{" "}
                  <Link to="/privacy" className="text-primary underline">{tr.privacyPolicy}</Link>.
                </p>
              </div>
              <button onClick={decline} className="ml-auto text-muted-foreground hover:text-foreground flex-shrink-0">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div className="flex gap-2">
              <Button size="sm" onClick={accept} className="flex-1 rounded-lg text-xs">{tr.cookieAccept}</Button>
              <Button size="sm" variant="outline" onClick={decline} className="flex-1 rounded-lg text-xs border-white/10">{tr.cookieDecline}</Button>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}