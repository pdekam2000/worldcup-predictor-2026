"""User feedback form and developer viewer."""

from __future__ import annotations

import streamlit as st

from worldcup_predictor.access.identity import current_user_id, init_access_session
from worldcup_predictor.access.repository import AccessRepository
from worldcup_predictor.config.settings import Locale
from worldcup_predictor.ui.gui_i18n import gui_t


def render_feedback_form(
    locale: Locale,
    *,
    fixture_id: int | None = None,
    prediction_context: str | None = None,
    key_prefix: str = "feedback",
) -> None:
    """Compact feedback form — never raises."""
    try:
        init_access_session()
        with st.expander(gui_t("feedback.title", locale), expanded=False):
            rating = st.slider(gui_t("feedback.rating", locale), 1, 5, 4, key=f"{key_prefix}_rating")
            comment = st.text_area(gui_t("feedback.comment", locale), key=f"{key_prefix}_comment")
            if st.button(gui_t("feedback.submit", locale), key=f"{key_prefix}_submit"):
                ok = AccessRepository().save_feedback(
                    user_id=current_user_id(),
                    rating=rating,
                    comment=comment,
                    fixture_id=fixture_id,
                    prediction_context=prediction_context,
                )
                if ok:
                    st.success(gui_t("feedback.saved", locale))
                else:
                    st.warning(gui_t("feedback.failed", locale))
    except Exception:
        st.caption(gui_t("feedback.unavailable", locale))


def render_feedback_viewer_page(locale: Locale) -> None:
    """Developer Mode feedback list + CSV export."""
    try:
        _render_viewer(locale)
    except Exception:
        st.error(gui_t("feedback.viewer_unavailable", locale))


def _render_viewer(locale: Locale) -> None:
    repo = AccessRepository()
    items = repo.list_feedback(limit=200)
    if not items:
        st.info(gui_t("feedback.empty", locale))
        return

    import pandas as pd

    rows = [
        {
            "id": i.id,
            "user_id": i.user_id,
            "fixture_id": i.fixture_id,
            "rating": i.rating,
            "comment": (i.comment or "")[:120],
            "created_at": i.created_at,
        }
        for i in items
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    csv_data = repo.export_feedback_csv()
    st.download_button(
        gui_t("feedback.export_csv", locale),
        data=csv_data,
        file_name="user_feedback.csv",
        mime="text/csv",
        key="feedback_export_csv",
    )

    for item in items[:20]:
        with st.expander(f"★{item.rating} · {item.created_at}", expanded=False):
            st.markdown(item.comment or "—")
            if item.fixture_id:
                st.caption(f"Fixture: {item.fixture_id}")
            if item.prediction_context:
                st.caption(item.prediction_context)
