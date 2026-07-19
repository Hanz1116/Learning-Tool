import streamlit as st

st.set_page_config(page_title="YouTube Learning Tool", page_icon="🎓", layout="wide")

pages = [
    st.Page("ui/home.py", title="Library", icon="📚", default=True),
    st.Page("ui/add.py", title="Add videos", icon="➕"),
    st.Page("ui/note.py", title="Study note", icon="📖"),
    st.Page("ui/quiz.py", title="Quiz", icon="📝"),
]

st.navigation(pages).run()
