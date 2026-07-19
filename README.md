# YouTube Learning Tool

A personal, locally-run Streamlit app that turns YouTube videos into study notes and
quizzes so you can learn, test yourself, and review on a schedule.

**The loop:**

1. **Add** — paste a YouTube link (or several, or a playlist). The app pulls the video's
   English captions — nothing is downloaded.
2. **Note** — Claude turns the transcript into a structured study note (TL;DR, key
   concepts, a section-by-section walkthrough with clickable timestamps, key takeaways),
   saved as a plain Markdown file in `data/notes/` — readable anywhere, Obsidian-importable.
3. **Quiz** — 8 multiple-choice questions (auto-graded, with explanations) plus 3
   short-answer questions graded by Claude against the note. A "Fresh questions" button
   regenerates the set so retakes test the material, not your memory of the answers.
4. **Review** — quiz scores are tracked in SQLite, and the home page shows videos due for
   a re-quiz using expanding intervals (1 → 3 → 7 → 30 → 90 days). Good scores push the
   next review out; poor scores reset it.

## Setup

Requires Python 3.10+ and an [Anthropic API key](https://platform.claude.com/).

```bash
pip install -r requirements.txt
cp .env.example .env       # then put your ANTHROPIC_API_KEY in .env
streamlit run app.py
```

The app opens at http://localhost:8501.

## Costs

Each video costs one note-generation and one quiz-generation call
(typically a few cents with the default `claude-sonnet-5` model), plus a small
grading call per quiz attempt.

## Limitations (v1)

- English captions only — videos without captions are rejected with a clear error
  (YouTube auto-generates captions for most videos, so coverage is high).
- YouTube sometimes blocks caption requests from cloud/datacenter IPs; running the app
  on your own machine avoids this.

## Layout

```
app.py               # Streamlit entry point (navigation)
ui/                  # Streamlit pages: Library, Add videos, Study note, Quiz
learning_tool/       # Core logic
  youtube.py         #   URL parsing, oEmbed metadata, caption fetching, playlists
  llm.py             #   Claude calls: note, quiz (structured output), grading
  store.py           #   SQLite: videos, quizzes, attempts, review schedule
  pipeline.py        #   Ingest flow: URL -> transcript -> note -> quiz
data/notes/*.md      # Your study notes (plain Markdown)
data/learning.db     # Quiz questions, attempts, review schedule (not committed)
```
