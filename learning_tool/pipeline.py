"""The ingest pipeline: URL -> transcript -> note -> quiz -> stored."""

from __future__ import annotations

from dataclasses import dataclass

from . import llm, store, youtube


@dataclass
class IngestResult:
    video_id: str
    title: str
    status: str  # "added" | "skipped" | "error"
    message: str = ""


def collect_video_ids(raw_input: str) -> tuple[list[str], list[str]]:
    """Parse pasted text (one URL per line) into video IDs, expanding playlists.

    Returns (video_ids, errors). Order is preserved, duplicates removed.
    """
    ids: list[str] = []
    errors: list[str] = []
    for line in raw_input.splitlines():
        line = line.strip()
        if not line:
            continue
        video_id, playlist_id = youtube.parse_url(line)
        if video_id:
            ids.append(video_id)
        elif playlist_id:
            try:
                ids.extend(youtube.expand_playlist(playlist_id))
            except Exception as exc:
                errors.append(f"Could not expand playlist {playlist_id}: {exc}")
        else:
            errors.append(f"Not a recognized YouTube URL: {line}")
    seen: set[str] = set()
    unique = [i for i in ids if not (i in seen or seen.add(i))]
    return unique, errors


def ingest_video(conn, video_id: str, progress=lambda msg: None) -> IngestResult:
    if store.get_video(conn, video_id):
        return IngestResult(video_id, video_id, "skipped", "Already in your library.")

    url = youtube.video_url(video_id)
    try:
        progress("Fetching captions…")
        lines = youtube.fetch_transcript(video_id)
        transcript_text = youtube.format_transcript(lines)

        progress("Fetching video info…")
        try:
            meta = youtube.fetch_metadata(video_id)
        except Exception:
            meta = {"title": video_id, "channel": ""}

        progress("Writing study note with Claude…")
        note = llm.generate_note(meta["title"], meta["channel"], url, transcript_text)

        progress("Generating quiz…")
        quiz = llm.generate_quiz(meta["title"], note)

        store.save_video(conn, video_id, meta["title"], meta["channel"], url, note)
        store.save_quiz(conn, video_id, quiz)
        return IngestResult(video_id, meta["title"], "added")
    except youtube.TranscriptUnavailable as exc:
        return IngestResult(video_id, video_id, "error", str(exc))
    except Exception as exc:
        return IngestResult(video_id, video_id, "error", f"{type(exc).__name__}: {exc}")


def regenerate_quiz(conn, video_id: str):
    """Fresh question set for a video, avoiding all previously asked questions."""
    row = store.get_video(conn, video_id)
    if not row:
        raise ValueError(f"Unknown video: {video_id}")
    note = store.read_note(row)
    quiz = llm.generate_quiz(row["title"], note, avoid_questions=store.past_question_texts(conn, video_id))
    store.save_quiz(conn, video_id, quiz)
