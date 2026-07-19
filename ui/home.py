import streamlit as st

from learning_tool import store
from ui.common import fmt_date, get_conn, select_video

conn = get_conn()

st.title("📚 Library")

due = store.due_videos(conn)
if due:
    st.subheader(f"🔔 Due for review ({len(due)})")
    st.caption("Scores push the next review further out (1 → 3 → 7 → 30 → 90 days); a low score resets it.")
    for v in due:
        col_title, col_note, col_quiz = st.columns([6, 1, 1])
        col_title.markdown(f"**{v['title']}** — due {fmt_date(v['next_review_at'])}")
        if col_note.button("Note", key=f"due-note-{v['id']}"):
            select_video(v["id"], "ui/note.py")
        if col_quiz.button("Quiz", key=f"due-quiz-{v['id']}", type="primary"):
            select_video(v["id"], "ui/quiz.py")
    st.divider()

videos = store.list_videos(conn)
if not videos:
    st.info("No videos yet. Paste a YouTube link on the **Add videos** page to get started.")
    st.page_link("ui/add.py", label="Add your first video", icon="➕")
else:
    st.subheader("All videos")
    for v in videos:
        with st.container(border=True):
            col_info, col_note, col_quiz, col_del = st.columns([6, 1, 1, 1])
            last = f"{v['last_score']:.0f}%" if v["last_score"] is not None else "not taken"
            col_info.markdown(
                f"**{v['title']}**  \n"
                f"{v['channel']} · added {fmt_date(v['added_at'])} · "
                f"last score: {last} · attempts: {v['attempts']} · "
                f"next review: {fmt_date(v['next_review_at'])}"
            )
            if col_note.button("📖 Note", key=f"note-{v['id']}"):
                select_video(v["id"], "ui/note.py")
            if col_quiz.button("📝 Quiz", key=f"quiz-{v['id']}"):
                select_video(v["id"], "ui/quiz.py")
            if col_del.button("🗑️ Delete", key=f"del-{v['id']}"):
                store.delete_video(conn, v["id"])
                st.rerun()
