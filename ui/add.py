import streamlit as st

from learning_tool import pipeline
from ui.common import get_conn, require_api_key

conn = get_conn()

st.title("➕ Add videos")
st.markdown(
    "Paste one or more YouTube links (one per line). Playlist links are expanded "
    "into all their videos. Each video is turned into a study note and a quiz — "
    "expect roughly a minute per video."
)

raw = st.text_area(
    "YouTube links",
    placeholder="https://www.youtube.com/watch?v=…\nhttps://youtu.be/…\nhttps://www.youtube.com/playlist?list=…",
    height=140,
)

if st.button("Process", type="primary", disabled=not raw.strip()):
    if not require_api_key():
        st.stop()
    with st.status("Collecting videos…", expanded=True) as status:
        ids, errors = pipeline.collect_video_ids(raw)
        for err in errors:
            st.warning(err)
        if not ids:
            status.update(label="No videos found in the input.", state="error")
            st.stop()
        st.write(f"Found {len(ids)} video(s).")

        results = []
        for n, video_id in enumerate(ids, start=1):
            st.write(f"**[{n}/{len(ids)}]** `{video_id}`")
            result = pipeline.ingest_video(conn, video_id, progress=st.write)
            results.append(result)
            if result.status == "added":
                st.success(f"Added: {result.title}")
            elif result.status == "skipped":
                st.info(f"Skipped `{video_id}`: {result.message}")
            else:
                st.error(f"Failed `{video_id}`: {result.message}")

        added = sum(1 for r in results if r.status == "added")
        failed = sum(1 for r in results if r.status == "error")
        status.update(
            label=f"Done — {added} added, {failed} failed, {len(results) - added - failed} skipped.",
            state="complete" if failed == 0 else "error",
            expanded=True,
        )
    if any(r.status == "added" for r in results):
        st.page_link("ui/home.py", label="Go to your library", icon="📚")
