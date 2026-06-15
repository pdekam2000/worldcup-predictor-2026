"""Phase 48 — Professional Reports page (exported match reports)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import streamlit as st

from worldcup_predictor.config.settings import Locale
from worldcup_predictor.export.professional_match_report_exporter_v2 import DEFAULT_REPORTS_DIR
from worldcup_predictor.ui.gui_i18n import gui_t

_FILENAME_RE = re.compile(r"^fixture_(\d+)_(\d{8})_(\d{6})(?:_(summary))?\.(md|json|txt)$")


@dataclass
class ExportedReportGroup:
    fixture_id: int
    timestamp: str
    created_utc: str
    locale: str
    md_path: str | None = None
    json_path: str | None = None
    summary_path: str | None = None


def _parse_timestamp(ts: str) -> str:
    try:
        dt = datetime.strptime(ts, "%Y%m%d_%H%M%S").replace(tzinfo=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return ts.replace("_", " ")


def _read_locale_from_json(path: Path) -> str:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        loc = data.get("locale") or data.get("export_locale")
        if loc:
            return str(loc)
    except Exception:
        pass
    return "—"


def list_exported_reports(limit: int = 50) -> list[ExportedReportGroup]:
    """Scan reports directory — never raises."""
    root = Path(DEFAULT_REPORTS_DIR)
    if not root.is_dir():
        return []

    groups: dict[tuple[int, str], ExportedReportGroup] = {}
    try:
        for path in sorted(root.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
            match = _FILENAME_RE.match(path.name)
            if not match:
                continue
            fixture_id = int(match.group(1))
            ts = f"{match.group(2)}_{match.group(3)}"
            key = (fixture_id, ts)
            if key not in groups:
                groups[key] = ExportedReportGroup(
                    fixture_id=fixture_id,
                    timestamp=ts,
                    created_utc=_parse_timestamp(ts),
                    locale="—",
                )
            group = groups[key]
            suffix = match.group(4)
            ext = match.group(5)
            resolved = str(path.resolve())
            if suffix == "summary" or path.name.endswith("_summary.txt"):
                group.summary_path = resolved
            elif ext == "md":
                group.md_path = resolved
            elif ext == "json":
                group.json_path = resolved
                group.locale = _read_locale_from_json(path)
    except Exception:
        return []

    ordered = sorted(groups.values(), key=lambda g: g.timestamp, reverse=True)
    return ordered[:limit]


def render_professional_reports_page(locale: Locale) -> None:
    """List and preview exported reports — never raises."""
    try:
        _render_page(locale)
    except Exception:
        st.info(gui_t("reports_page.empty", locale))


def _render_page(locale: Locale) -> None:
    reports = list_exported_reports()
    st.caption(gui_t("reports_page.hint", locale))

    if not reports:
        st.info(gui_t("reports_page.empty", locale))
        return

    import pandas as pd

    rows = []
    for item in reports:
        paths = [p for p in (item.md_path, item.json_path, item.summary_path) if p]
        rows.append(
            {
                gui_t("reports_page.fixture", locale): item.fixture_id,
                gui_t("reports_page.locale", locale): item.locale,
                gui_t("reports_page.created", locale): item.created_utc,
                gui_t("reports_page.files", locale): len(paths),
            }
        )
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    for item in reports[:15]:
        label = f"Fixture {item.fixture_id} · {item.created_utc}"
        with st.expander(label, expanded=False):
            if item.md_path:
                st.markdown(f"**Markdown:** `{item.md_path}`")
            if item.json_path:
                st.markdown(f"**JSON:** `{item.json_path}`")
            if item.summary_path:
                st.markdown(f"**Summary:** `{item.summary_path}`")

            preview_path = item.summary_path or item.md_path
            if preview_path and Path(preview_path).is_file():
                try:
                    text = Path(preview_path).read_text(encoding="utf-8")
                    st.text_area(
                        gui_t("reports_page.preview", locale),
                        value=text[:8000],
                        height=240,
                        disabled=True,
                        key=f"preview_{item.fixture_id}_{item.timestamp}",
                    )
                except Exception:
                    st.caption(gui_t("reports_page.preview_unavailable", locale))
