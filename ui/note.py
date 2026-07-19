import streamlit as st

from learning_tool import store
from ui.common import get_conn, video_picker

conn = get_conn()

st.title("📖 Study note")

video = video_picker(conn, key="note-picker")
if video is None:
    st.stop()

col_link, col_quiz = st.columns([3, 1])
col_link.markdown(f"[▶ Watch on YouTube]({video['url']})")
if col_quiz.button("Take the quiz 📝", type="primary"):
    st.switch_page("ui/quiz.py")

st.divider()
st.markdown(store.read_note(video))
