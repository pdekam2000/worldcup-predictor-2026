"""Locale strings for Phase 47 match report export."""

from __future__ import annotations

from typing import Literal

ExportLocale = Literal["en", "de", "fa"]

_STRINGS: dict[str, dict[str, str]] = {
    "report.title": {
        "en": "Professional Match Prediction Report",
        "de": "Professioneller Spiel-Prognosebericht",
        "fa": "گزارش حرفه‌ای پیش‌بینی مسابقه",
    },
    "report.match": {"en": "Match", "de": "Spiel", "fa": "مسابقه"},
    "report.fixture_id": {"en": "Fixture ID", "de": "Spiel-ID", "fa": "شناسه مسابقه"},
    "report.kickoff": {"en": "Kickoff (UTC)", "de": "Anstoß (UTC)", "fa": "شروع (UTC)"},
    "report.stage": {"en": "Stage", "de": "Phase", "fa": "مرحله"},
    "report.prediction": {"en": "Final prediction", "de": "Finale Prognose", "fa": "پیش‌بینی نهایی"},
    "report.confidence": {"en": "Confidence", "de": "Konfidenz", "fa": "اطمینان"},
    "report.fusion": {"en": "Fusion summary", "de": "Fusion-Zusammenfassung", "fa": "خلاصه همگرایی"},
    "report.executive": {"en": "Executive summary", "de": "Executive Summary", "fa": "خلاصه مدیریتی"},
    "report.agents": {"en": "Agent contributions", "de": "Agenten-Beiträge", "fa": "مشارکت عامل‌ها"},
    "report.risk": {"en": "Risk analysis", "de": "Risikoanalyse", "fa": "تحلیل ریسک"},
    "report.conflicts": {"en": "Conflict analysis", "de": "Konfliktanalyse", "fa": "تحلیل تعارض"},
    "report.lineup": {"en": "Lineup Intelligence V2", "de": "Aufstellungs-Intelligenz V2", "fa": "هوش ترکیب V2"},
    "report.injury": {"en": "Injury Intelligence V2", "de": "Verletzungs-Intelligenz V2", "fa": "هوش مصدومیت V2"},
    "report.sharp": {"en": "Sharp Money V2", "de": "Sharp Money V2", "fa": "پول هوشمند V2"},
    "report.tournament": {"en": "Tournament Intelligence V2", "de": "Turnier-Intelligenz V2", "fa": "هوش تورنمنت V2"},
    "report.elo": {"en": "ELO & Team Strength V2", "de": "ELO & Teamstärke V2", "fa": "ELO و قدرت تیم V2"},
    "report.xg": {"en": "xG & Chance Quality V2", "de": "xG & Chancenqualität V2", "fa": "xG و کیفیت موقعیت V2"},
    "report.disclaimer": {
        "en": "Analytical prediction only. Not guaranteed. Not financial or betting advice.",
        "de": "Nur analytische Prognose. Nicht garantiert. Keine Finanz- oder Wettberatung.",
        "fa": "فقط پیش‌بینی تحلیلی. تضمین‌شده نیست. توصیه مالی یا شرط‌بندی نیست.",
    },
    "report.unavailable": {"en": "Unavailable", "de": "Nicht verfügbar", "fa": "در دسترس نیست"},
    "report.one_x_two": {"en": "1X2", "de": "1X2", "fa": "1X2"},
    "report.over_under": {"en": "Over/Under 2.5", "de": "Over/Under 2.5", "fa": "Over/Under 2.5"},
    "report.scoreline": {"en": "Scoreline", "de": "Ergebnis", "fa": "نتیجه"},
    "report.no_bet": {"en": "No-bet flag", "de": "No-Bet-Flag", "fa": "پرچم عدم شرط"},
    "report.first_goal": {"en": "First goal intelligence", "de": "Erstes Tor", "fa": "گل اول"},
    "report.first_goal_team": {"en": "First goal team", "de": "Erstes Tor Team", "fa": "تیم گل اول"},
    "report.first_goal_band": {"en": "Minute band", "de": "Minutenband", "fa": "بازه دقیقه"},
    "report.first_goal_confidence": {"en": "First goal confidence", "de": "Tor-Konfidenz", "fa": "اطمینان گل اول"},
    "summary.intro": {
        "en": "Analytical match report — not betting advice.",
        "de": "Analytischer Spielbericht — keine Wettberatung.",
        "fa": "گزارش تحلیلی مسابقه — توصیه شرط‌بندی نیست.",
    },
}


def report_t(key: str, locale: ExportLocale) -> str:
    block = _STRINGS.get(key, {})
    return block.get(locale) or block.get("en") or key
