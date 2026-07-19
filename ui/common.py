import os
from datetime import datetime

import streamlit as st

from learning_tool import store


def get_conn():
    # A fresh connection per rerun: cheap, and avoids cross-thread sqlite issues.
    return store.connect()


def require_api_key() -> bool:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return True
    st.error(
        "`ANTHROPIC_API_KEY` is not set. Add it to a `.env` file in the project root "
        "(see `.env.example`) and restart the app."
    )
    return False


def select_video(video_id: str, page: str) -> None:
    st.session_state["selected_video"] = video_id
    st.switch_page(page)


def video_picker(conn, key: str):
    """Selectbox over the library; honors a selection made on another page."""
    videos = store.list_videos(conn)
    if not videos:
        st.info("Your library is empty — add a video first.")
        st.page_link("ui/add.py", label="Add videos", icon="➕")
        return None
    ids = [v["id"] for v in videos]
    labels = {v["id"]: v["title"] for v in videos}
    preselected = st.session_state.get("selected_video")
    index = ids.index(preselected) if preselected in ids else 0
    chosen = st.selectbox("Video", ids, index=index, format_func=lambda i: labels[i], key=key)
    st.session_state["selected_video"] = chosen
    return next(v for v in videos if v["id"] == chosen)


def fmt_date(iso: str | None) -> str:
    if not iso:
        return "—"
    return datetime.fromisoformat(iso).strftime("%b %d, %Y")
