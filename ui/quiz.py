import json

import streamlit as st

from learning_tool import llm, pipeline, store
from ui.common import fmt_date, get_conn, require_api_key, video_picker

conn = get_conn()

st.title("📝 Quiz")

video = video_picker(conn, key="quiz-picker")
if video is None:
    st.stop()
video_id = video["id"]

quiz, questions = store.active_quiz(conn, video_id)
if quiz is None:
    st.warning("No quiz stored for this video yet.")
    if st.button("Generate quiz now", type="primary"):
        if require_api_key():
            with st.spinner("Generating questions…"):
                pipeline.regenerate_quiz(conn, video_id)
            st.rerun()
    st.stop()

mc_questions = [q for q in questions if q["kind"] == "mc"]
short_questions = [q for q in questions if q["kind"] == "short"]

top_left, top_right = st.columns([3, 1])
top_left.caption(
    f"{len(mc_questions)} multiple-choice + {len(short_questions)} short-answer questions. "
    "Short answers are graded by Claude against the note."
)
if top_right.button("🔄 Fresh questions"):
    if require_api_key():
        with st.spinner("Generating a fresh question set…"):
            pipeline.regenerate_quiz(conn, video_id)
        st.session_state.pop(f"result-{video_id}", None)
        st.rerun()

result_key = f"result-{video_id}"

with st.form(key=f"quiz-form-{quiz['id']}"):
    mc_answers: dict[int, int | None] = {}
    for n, q in enumerate(mc_questions, start=1):
        options = json.loads(q["options"])
        choice = st.radio(
            f"**{n}. {q['question']}**", options, index=None, key=f"mc-{quiz['id']}-{q['id']}"
        )
        mc_answers[q["id"]] = options.index(choice) if choice is not None else None
        st.write("")

    short_answers: dict[int, str] = {}
    for n, q in enumerate(short_questions, start=len(mc_questions) + 1):
        short_answers[q["id"]] = st.text_area(
            f"**{n}. {q['question']}**", key=f"short-{quiz['id']}-{q['id']}", height=100
        )

    submitted = st.form_submit_button("Submit answers", type="primary")

if submitted:
    if not require_api_key():
        st.stop()
    unanswered = sum(1 for v in mc_answers.values() if v is None)
    if unanswered:
        st.warning(f"{unanswered} multiple-choice question(s) left blank — they count as wrong.")

    mc_detail = []
    mc_correct = 0
    for q in mc_questions:
        given = mc_answers[q["id"]]
        correct = given is not None and given == q["correct_index"]
        mc_correct += correct
        mc_detail.append({
            "question": q["question"],
            "options": json.loads(q["options"]),
            "given": given,
            "correct_index": q["correct_index"],
            "correct": correct,
            "explanation": q["explanation"],
        })

    short_detail = []
    if short_questions:
        with st.spinner("Claude is grading your short answers…"):
            grades = llm.grade_short_answers(
                video["title"],
                store.read_note(video),
                [
                    {
                        "question": q["question"],
                        "answer_guide": q["answer_guide"],
                        "user_answer": short_answers[q["id"]],
                    }
                    for q in short_questions
                ],
            )
        for q, grade in zip(short_questions, grades):
            short_detail.append({
                "question": q["question"],
                "answer": short_answers[q["id"]],
                "score": grade.score,
                "feedback": grade.feedback,
                "answer_guide": q["answer_guide"],
            })

    total_units = len(mc_questions) + len(short_questions)
    earned = mc_correct + sum(d["score"] for d in short_detail) / 100
    score_pct = round(100 * earned / total_units, 1) if total_units else 0.0

    store.record_attempt(
        conn, video_id, quiz["id"], score_pct, {"mc": mc_detail, "short": short_detail}
    )
    st.session_state[result_key] = {
        "score_pct": score_pct,
        "mc_correct": mc_correct,
        "mc_total": len(mc_questions),
        "mc": mc_detail,
        "short": short_detail,
    }
    st.rerun()

result = st.session_state.get(result_key)
if result:
    st.divider()
    st.subheader("Results")
    icon = "🎉" if result["score_pct"] >= 80 else ("👍" if result["score_pct"] >= 50 else "📚")
    st.metric("Score", f"{result['score_pct']:.0f}%")
    st.write(f"{icon} Multiple choice: {result['mc_correct']}/{result['mc_total']} correct.")

    fresh_video = store.get_video(conn, video_id)
    st.caption(
        f"Next review scheduled for {fmt_date(fresh_video['next_review_at'])} "
        f"(interval: {fresh_video['interval_days']} days)."
    )

    with st.expander("Multiple-choice review", expanded=result["mc_correct"] < result["mc_total"]):
        for n, d in enumerate(result["mc"], start=1):
            mark = "✅" if d["correct"] else "❌"
            given_text = d["options"][d["given"]] if d["given"] is not None else "(blank)"
            st.markdown(
                f"{mark} **{n}. {d['question']}**  \n"
                f"Your answer: {given_text}  \n"
                f"Correct answer: {d['options'][d['correct_index']]}  \n"
                f"_{d['explanation']}_"
            )

    if result["short"]:
        with st.expander("Short-answer feedback", expanded=True):
            for n, d in enumerate(result["short"], start=1):
                st.markdown(
                    f"**{n}. {d['question']}** — scored {d['score']}/100  \n"
                    f"Your answer: {d['answer'] or '(blank)'}  \n"
                    f"Feedback: _{d['feedback']}_"
                )

    if st.button("Clear results"):
        st.session_state.pop(result_key, None)
        st.rerun()

attempts = store.attempts_for(conn, video_id)
if attempts:
    with st.expander(f"Past attempts ({len(attempts)})"):
        for a in attempts:
            st.write(f"{fmt_date(a['taken_at'])} — {a['score_pct']:.0f}%")
