"""SQLite persistence: videos, quizzes, attempts, and the review schedule."""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta

from . import config
from .llm import Quiz

_SCHEMA = """
CREATE TABLE IF NOT EXISTS videos (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    channel       TEXT NOT NULL DEFAULT '',
    url           TEXT NOT NULL,
    note_path     TEXT NOT NULL,
    added_at      TEXT NOT NULL,
    interval_days INTEGER NOT NULL DEFAULT 1,
    next_review_at TEXT
);
CREATE TABLE IF NOT EXISTS quizzes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id   TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL,
    active     INTEGER NOT NULL DEFAULT 1
);
CREATE TABLE IF NOT EXISTS questions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    quiz_id       INTEGER NOT NULL REFERENCES quizzes(id) ON DELETE CASCADE,
    kind          TEXT NOT NULL CHECK (kind IN ('mc', 'short')),
    question      TEXT NOT NULL,
    options       TEXT,
    correct_index INTEGER,
    explanation   TEXT,
    answer_guide  TEXT
);
CREATE TABLE IF NOT EXISTS attempts (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id  TEXT NOT NULL REFERENCES videos(id) ON DELETE CASCADE,
    quiz_id   INTEGER NOT NULL,
    taken_at  TEXT NOT NULL,
    score_pct REAL NOT NULL,
    detail    TEXT NOT NULL
);
"""


def connect() -> sqlite3.Connection:
    config.ensure_dirs()
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(_SCHEMA)
    return conn


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# ---------------------------------------------------------------- videos & notes

def note_filename(video_id: str, title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title).strip("-").lower()[:60] or "note"
    return f"{slug}-{video_id}.md"


def save_video(conn, video_id: str, title: str, channel: str, url: str, note_markdown: str) -> None:
    config.ensure_dirs()
    path = config.NOTES_DIR / note_filename(video_id, title)
    path.write_text(note_markdown, encoding="utf-8")
    first_interval = config.REVIEW_INTERVALS[0]
    conn.execute(
        """INSERT OR REPLACE INTO videos
           (id, title, channel, url, note_path, added_at, interval_days, next_review_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (video_id, title, channel, url, str(path), _now(),
         first_interval, (datetime.now() + timedelta(days=first_interval)).isoformat(timespec="seconds")),
    )
    conn.commit()


def get_video(conn, video_id: str):
    return conn.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()


def list_videos(conn):
    return conn.execute(
        """SELECT v.*,
                  (SELECT MAX(score_pct) FROM attempts a WHERE a.video_id = v.id) AS best_score,
                  (SELECT score_pct FROM attempts a WHERE a.video_id = v.id
                   ORDER BY taken_at DESC LIMIT 1) AS last_score,
                  (SELECT COUNT(*) FROM attempts a WHERE a.video_id = v.id) AS attempts
           FROM videos v ORDER BY v.added_at DESC"""
    ).fetchall()


def due_videos(conn):
    return conn.execute(
        """SELECT * FROM videos
           WHERE next_review_at IS NOT NULL AND next_review_at <= ?
           ORDER BY next_review_at""",
        (_now(),),
    ).fetchall()


def read_note(row) -> str:
    from pathlib import Path

    path = Path(row["note_path"])
    if not path.exists():
        return f"_Note file missing: {path}_"
    return path.read_text(encoding="utf-8")


def delete_video(conn, video_id: str) -> None:
    row = get_video(conn, video_id)
    if row:
        from pathlib import Path

        Path(row["note_path"]).unlink(missing_ok=True)
    conn.execute("DELETE FROM videos WHERE id = ?", (video_id,))
    conn.commit()


# ---------------------------------------------------------------- quizzes

def save_quiz(conn, video_id: str, quiz: Quiz) -> int:
    conn.execute("UPDATE quizzes SET active = 0 WHERE video_id = ?", (video_id,))
    cur = conn.execute(
        "INSERT INTO quizzes (video_id, created_at, active) VALUES (?, ?, 1)",
        (video_id, _now()),
    )
    quiz_id = cur.lastrowid
    for q in quiz.mc_questions:
        conn.execute(
            """INSERT INTO questions (quiz_id, kind, question, options, correct_index, explanation)
               VALUES (?, 'mc', ?, ?, ?, ?)""",
            (quiz_id, q.question, json.dumps(q.options), q.correct_index, q.explanation),
        )
    for q in quiz.short_questions:
        conn.execute(
            "INSERT INTO questions (quiz_id, kind, question, answer_guide) VALUES (?, 'short', ?, ?)",
            (quiz_id, q.question, q.answer_guide),
        )
    conn.commit()
    return quiz_id


def active_quiz(conn, video_id: str):
    quiz = conn.execute(
        "SELECT * FROM quizzes WHERE video_id = ? AND active = 1 ORDER BY id DESC LIMIT 1",
        (video_id,),
    ).fetchone()
    if not quiz:
        return None, []
    questions = conn.execute(
        "SELECT * FROM questions WHERE quiz_id = ? ORDER BY id", (quiz["id"],)
    ).fetchall()
    return quiz, questions


def past_question_texts(conn, video_id: str) -> list[str]:
    rows = conn.execute(
        """SELECT q.question FROM questions q
           JOIN quizzes z ON z.id = q.quiz_id WHERE z.video_id = ?""",
        (video_id,),
    ).fetchall()
    return [r["question"] for r in rows]


# ---------------------------------------------------------------- attempts & review schedule

def record_attempt(conn, video_id: str, quiz_id: int, score_pct: float, detail: dict) -> None:
    conn.execute(
        "INSERT INTO attempts (video_id, quiz_id, taken_at, score_pct, detail) VALUES (?, ?, ?, ?, ?)",
        (video_id, quiz_id, _now(), score_pct, json.dumps(detail)),
    )
    _update_schedule(conn, video_id, score_pct)
    conn.commit()


def _update_schedule(conn, video_id: str, score_pct: float) -> None:
    row = get_video(conn, video_id)
    if not row:
        return
    intervals = config.REVIEW_INTERVALS
    current = row["interval_days"]
    if score_pct >= config.ADVANCE_THRESHOLD:
        larger = [i for i in intervals if i > current]
        new_interval = larger[0] if larger else intervals[-1]
    elif score_pct >= config.RESET_THRESHOLD:
        new_interval = current
    else:
        new_interval = intervals[0]
    next_review = (datetime.now() + timedelta(days=new_interval)).isoformat(timespec="seconds")
    conn.execute(
        "UPDATE videos SET interval_days = ?, next_review_at = ? WHERE id = ?",
        (new_interval, next_review, video_id),
    )


def attempts_for(conn, video_id: str):
    return conn.execute(
        "SELECT * FROM attempts WHERE video_id = ? ORDER BY taken_at DESC", (video_id,)
    ).fetchall()
