"""All Claude API calls: note generation, quiz generation, short-answer grading."""

from __future__ import annotations

from typing import List

import anthropic
from pydantic import BaseModel, Field

from .config import MODEL

_client: anthropic.Anthropic | None = None


def client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


# ---------------------------------------------------------------- note

_NOTE_PROMPT = """You are an expert tutor turning a YouTube video transcript into a study note.

Video title: {title}
Channel: {channel}
Video URL: {url}

Write a structured study note in Markdown with exactly these sections:

# {title}

> One-line description of what the video is about, with the channel name.

## TL;DR
3-5 sentences capturing the core message.

## Key Concepts
Each important concept as a `### Concept name` subsection with a plain-language
explanation of 2-5 sentences. Cover every concept needed to understand the video.

## Walkthrough
The video's content section by section, in order. Start each section heading with a
clickable timestamp link to that moment, e.g. `### [[12:34]]({url}&t=754s) Section title`
(timestamp in seconds in the `t` parameter). Summarize each section in a short paragraph
or tight bullets.

## Key Takeaways
A numbered list of the most important points to remember.

Rules:
- Base everything strictly on the transcript; do not add outside claims.
- Write for someone reviewing weeks later who has forgotten the video.
- Use the transcript's `[h:mm:ss]` markers to compute the timestamp links.

Transcript (with timestamps):

{transcript}"""


def generate_note(title: str, channel: str, url: str, transcript_text: str) -> str:
    resp = client().messages.create(
        model=MODEL,
        max_tokens=16000,
        messages=[{
            "role": "user",
            "content": _NOTE_PROMPT.format(
                title=title, channel=channel, url=url, transcript=transcript_text
            ),
        }],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


# ---------------------------------------------------------------- quiz

class MCQuestion(BaseModel):
    question: str
    options: List[str] = Field(description="Exactly 4 answer options")
    correct_index: int = Field(description="0-based index of the correct option")
    explanation: str = Field(description="Why the correct answer is right")


class ShortQuestion(BaseModel):
    question: str
    answer_guide: str = Field(
        description="The key points a correct answer must contain, used for grading"
    )


class Quiz(BaseModel):
    mc_questions: List[MCQuestion]
    short_questions: List[ShortQuestion]


_QUIZ_PROMPT = """Create a comprehension quiz for this study note of the video "{title}".

Requirements:
- 8 multiple-choice questions, each with exactly 4 options and one correct answer.
  Mix recall questions with questions that test understanding (why/how, applying an idea).
  Distribute the correct option index roughly evenly; make distractors plausible.
- 3 short-answer questions that require explaining a concept in the learner's own words.
- Test the substance of the video, not trivia about its structure.
{variation}
Study note:

{note}"""


def generate_quiz(title: str, note_markdown: str, avoid_questions: list[str] | None = None) -> Quiz:
    variation = ""
    if avoid_questions:
        joined = "\n".join(f"- {q}" for q in avoid_questions)
        variation = (
            "- Produce a FRESH set: do not reuse or trivially rephrase any of these "
            f"previously asked questions:\n{joined}\n"
        )
    resp = client().messages.parse(
        model=MODEL,
        max_tokens=8000,
        messages=[{
            "role": "user",
            "content": _QUIZ_PROMPT.format(title=title, note=note_markdown, variation=variation),
        }],
        output_format=Quiz,
    )
    return resp.parsed_output


# ---------------------------------------------------------------- grading

class ShortAnswerGrade(BaseModel):
    score: int = Field(description="0-100, how completely and correctly the answer covers the guide")
    feedback: str = Field(description="1-3 sentences: what was right, what was missing or wrong")


class GradingResult(BaseModel):
    grades: List[ShortAnswerGrade]


_GRADE_PROMPT = """Grade a learner's short answers about the video "{title}".

For each question you get the question, an answer guide (the key points a correct answer
should contain), and the learner's answer. Score each answer 0-100:
- 100: covers all key points correctly in their own words
- 60-90: mostly correct, minor gaps
- 30-50: partially correct or vague
- 0-20: wrong, empty, or unrelated
Be fair: different wording that conveys the right idea scores high. Give concrete,
encouraging feedback that fills the gaps.

{items}

Reference study note:

{note}"""


def grade_short_answers(
    title: str,
    note_markdown: str,
    items: list[dict],  # each: {"question", "answer_guide", "user_answer"}
) -> list[ShortAnswerGrade]:
    rendered = "\n\n".join(
        f"Question {i + 1}: {it['question']}\n"
        f"Answer guide: {it['answer_guide']}\n"
        f"Learner's answer: {it['user_answer'] or '(no answer given)'}"
        for i, it in enumerate(items)
    )
    resp = client().messages.parse(
        model=MODEL,
        max_tokens=4000,
        messages=[{
            "role": "user",
            "content": _GRADE_PROMPT.format(title=title, items=rendered, note=note_markdown),
        }],
        output_format=GradingResult,
    )
    grades = resp.parsed_output.grades
    # Defensive: keep grades aligned with questions even if the model miscounts.
    while len(grades) < len(items):
        grades.append(ShortAnswerGrade(score=0, feedback="No grade returned for this answer."))
    return grades[: len(items)]
