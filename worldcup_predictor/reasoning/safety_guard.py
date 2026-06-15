from __future__ import annotations

import re
from typing import Iterable

from worldcup_predictor.reasoning.report_models import ProfessionalMatchReport

FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\b(guaranteed|guarantee|guarantees)\b", re.I), "not guaranteed"),
    (re.compile(r"\bsure win\b", re.I), "uncertain outcome"),
    (re.compile(r"\brisk[- ]free\b", re.I), "never risk-free"),
    (re.compile(r"\bbet now\b", re.I), "wait for more data"),
    (re.compile(r"\bfixed match\b", re.I), "outcome uncertain"),
    (re.compile(r"\binsider information\b", re.I), "publicly available information only"),
    (re.compile(r"\b100\s*%\s*(certain|sure|win)\b", re.I), "high uncertainty remains"),
    (re.compile(r"\block\s+win\b", re.I), "analytical estimate only"),
]

SAFETY_WARNING = (
    "Safety guard replaced forbidden betting/certainty language and replaced it with analytical wording."
)


def sanitize_text(text: str) -> tuple[str, bool]:
    """Replace forbidden phrases. Returns (sanitized_text, was_modified)."""
    if not text:
        return text, False
    modified = False
    result = text
    for pattern, replacement in FORBIDDEN_PATTERNS:
        if pattern.search(result):
            result = pattern.sub(replacement, result)
            modified = True
    return result, modified


def sanitize_list(items: Iterable[str]) -> tuple[list[str], bool]:
    sanitized: list[str] = []
    modified = False
    for item in items:
        clean, changed = sanitize_text(item)
        sanitized.append(clean)
        modified = modified or changed
    return sanitized, modified


def apply_safety_guard(report: ProfessionalMatchReport) -> ProfessionalMatchReport:
    """Post-process all narrative fields; add safety warning if content was adjusted."""
    modified = False

    report.executive_summary, c1 = sanitize_text(report.executive_summary)
    report.tactical_context, c2 = sanitize_text(report.tactical_context)
    report.market_analysis_information_only, c3 = sanitize_text(report.market_analysis_information_only)
    report.final_analytical_view, c4 = sanitize_text(report.final_analytical_view)
    report.disclaimer, c5 = sanitize_text(report.disclaimer)
    modified = any((c1, c2, c3, c4, c5))

    report.key_factors, c6 = sanitize_list(report.key_factors)
    report.risk_notes, c7 = sanitize_list(report.risk_notes)
    report.data_limitations, c8 = sanitize_list(report.data_limitations)
    report.audit_highlights, c9 = sanitize_list(report.audit_highlights)
    modified = modified or any((c6, c7, c8, c9))

    if modified and SAFETY_WARNING not in report.safety_warnings:
        report.safety_warnings.append(SAFETY_WARNING)

    return report
