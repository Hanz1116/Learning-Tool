"""Fetch video metadata and captions. No media is ever downloaded."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse

import requests
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


class TranscriptUnavailable(Exception):
    """The video has no usable English captions."""


@dataclass
class TranscriptLine:
    start: float  # seconds
    text: str


def parse_url(url: str) -> tuple[str | None, str | None]:
    """Return (video_id, playlist_id) for a YouTube URL; either may be None.

    A watch URL that carries a `list` param is treated as a single video,
    not a playlist — pasting the bare playlist URL is the explicit signal.
    """
    url = url.strip()
    if _VIDEO_ID_RE.match(url):
        return url, None
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    if host not in ("youtube.com", "youtu.be", "youtube-nocookie.com", "music.youtube.com"):
        return None, None
    qs = parse_qs(parsed.query)

    if host == "youtu.be":
        vid = parsed.path.lstrip("/").split("/")[0]
        return (vid if _VIDEO_ID_RE.match(vid) else None), None
    if parsed.path == "/playlist":
        pl = qs.get("list", [None])[0]
        return None, pl
    if parsed.path.startswith(("/shorts/", "/embed/", "/live/")):
        vid = parsed.path.split("/")[2] if len(parsed.path.split("/")) > 2 else ""
        return (vid if _VIDEO_ID_RE.match(vid) else None), None
    vid = qs.get("v", [None])[0]
    if vid and _VIDEO_ID_RE.match(vid):
        return vid, None
    return None, None


def video_url(video_id: str) -> str:
    return f"https://www.youtube.com/watch?v={video_id}"


def fetch_metadata(video_id: str) -> dict:
    """Title and channel via the keyless oEmbed endpoint."""
    resp = requests.get(
        "https://www.youtube.com/oembed",
        params={"url": video_url(video_id), "format": "json"},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    return {"title": data.get("title", video_id), "channel": data.get("author_name", "")}


def fetch_transcript(video_id: str) -> list[TranscriptLine]:
    """English captions (manual preferred, auto-generated accepted)."""
    try:
        fetched = YouTubeTranscriptApi().fetch(video_id, languages=["en", "en-US", "en-GB"])
    except (TranscriptsDisabled, NoTranscriptFound) as exc:
        raise TranscriptUnavailable(
            "This video has no English captions (v1 supports captioned English videos only)."
        ) from exc
    except VideoUnavailable as exc:
        raise TranscriptUnavailable("Video is unavailable or private.") from exc
    return [TranscriptLine(start=s.start, text=s.text.replace("\n", " ").strip()) for s in fetched]


def expand_playlist(playlist_id: str) -> list[str]:
    """Video IDs in a playlist, via yt-dlp flat extraction (metadata only)."""
    from yt_dlp import YoutubeDL

    opts = {"quiet": True, "extract_flat": "in_playlist", "skip_download": True}
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/playlist?list={playlist_id}", download=False)
    entries = info.get("entries") or []
    return [e["id"] for e in entries if e.get("id")]


def format_transcript(lines: list[TranscriptLine]) -> str:
    """Render as '[mm:ss] text' lines, merging into ~30-second blocks so the
    prompt stays compact without losing timestamp anchors."""
    blocks: list[str] = []
    block_start: float | None = None
    block_text: list[str] = []
    for line in lines:
        if not line.text:
            continue
        if block_start is None:
            block_start = line.start
        block_text.append(line.text)
        if line.start - block_start >= 30:
            blocks.append(f"[{_ts(block_start)}] {' '.join(block_text)}")
            block_start, block_text = None, []
    if block_text and block_start is not None:
        blocks.append(f"[{_ts(block_start)}] {' '.join(block_text)}")
    return "\n".join(blocks)


def _ts(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h else f"{m}:{sec:02d}"
