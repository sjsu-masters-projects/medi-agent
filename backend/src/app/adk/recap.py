"""The conversation context a turn's model reads: recent whole turns plus a rolling summary.

Two parts, both bounded:

* **Recent turns**, newest first, whole turns (a patient message and the replies after it),
  until a character budget is spent. A turn is never cut in half to fit; only a single
  message longer than ``MESSAGE_CHARS`` is clipped. The newest turn is always included, even
  when it alone is over budget, by keeping its newest messages that fit.
* **The stored summary** of what came before, written off the hot path by
  ``app.services.conversation_summary``. It is read as given (clipped to ``SUMMARY_CHARS``)
  and labelled as background that may be incomplete, never as the patient's record.

Only stored chat messages are read. A private symptom draft lives in its own tables and is
never an input here, so it can reach neither the recap nor the summary. Source lines are
removed because the server writes those; the model must not learn to copy them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.adk.grounding import without_source_lines

RECENT_CHARS = 6000
"""Budget for the recent turns' text (about 1,500 tokens)."""
MESSAGE_CHARS = 1200
"""One message is clipped to this; a long reply is not allowed to crowd out the turns before it."""
SUMMARY_CHARS = 1500
"""The summary read into a turn; the stored summary is capped a little higher."""
NO_HISTORY = "(none: this is the first message)"

_SPEAKERS = {"user": "Patient", "assistant": "Nora"}


@dataclass(frozen=True)
class Line:
    index: int  # position in the message list it came from
    speaker: str
    text: str

    @property
    def size(self) -> int:
        return len(self.speaker) + len(self.text) + 3  # "Speaker: " and a newline


def _clip(text: str, limit: int) -> str:
    flat = " ".join(without_source_lines(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def lines_of(messages: list[dict[str, Any]]) -> list[Line]:
    """The patient and Nora lines of stored messages, in order; empty ones are dropped."""
    lines: list[Line] = []
    for index, message in enumerate(messages):
        speaker = _SPEAKERS.get(str(message.get("role") or ""))
        text = _clip(str(message.get("content") or ""), MESSAGE_CHARS) if speaker else ""
        if speaker and text:
            lines.append(Line(index, speaker, text))
    return lines


def _turns(lines: list[Line]) -> list[list[Line]]:
    """Group into turns: a new turn starts at a patient line that follows a Nora line."""
    turns: list[list[Line]] = []
    for line in lines:
        if not turns or (line.speaker == "Patient" and turns[-1][-1].speaker == "Nora"):
            turns.append([])
        turns[-1].append(line)
    return turns


def recent_window(messages: list[dict[str, Any]], budget: int = RECENT_CHARS) -> list[Line]:
    """The newest whole turns that fit the budget, oldest first."""
    kept: list[Line] = []
    used = 0
    for turn in reversed(_turns(lines_of(messages))):
        size = sum(line.size for line in turn)
        if used + size <= budget:
            kept = [*turn, *kept]
            used += size
            continue
        if not kept:
            # The newest turn alone is over budget: keep its newest lines that fit.
            for line in reversed(turn):
                if used + line.size > budget and kept:
                    break
                kept.insert(0, line)
                used += line.size
        break
    return kept


def window_start(messages: list[dict[str, Any]]) -> int:
    """Index of the first message the recent window shows (len(messages) when none)."""
    window = recent_window(messages)
    return window[0].index if window else len(messages)


def build_recap(messages: list[dict[str, Any]], summary: str | None = None) -> str:
    """The text the coordinator and responder read for conversation context."""
    window = recent_window(messages)
    recent = "\n".join(f"{line.speaker}: {line.text}" for line in window)
    background = " ".join((summary or "").split())
    if len(background) > SUMMARY_CHARS:
        background = background[: SUMMARY_CHARS - 1].rstrip() + "…"
    if not background:
        return recent or NO_HISTORY
    parts = [
        "Summary of the earlier part of this conversation (written automatically; it may be "
        "incomplete, so check anything clinical against the record tools):",
        background,
    ]
    if recent:
        parts += ["", "Most recent messages:", recent]
    return "\n".join(parts)
