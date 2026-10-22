"""AI-003: the budgeted conversation context. Synthetic text only."""

from app.adk.recap import (
    MESSAGE_CHARS,
    NO_HISTORY,
    RECENT_CHARS,
    SUMMARY_CHARS,
    build_recap,
    recent_window,
    window_start,
)


def _turns(count: int, size: int = 300) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for number in range(count):
        messages.append({"role": "user", "content": f"question {number} " + "q" * size})
        messages.append({"role": "assistant", "content": f"answer {number} " + "a" * size})
    return messages


def test_a_short_conversation_is_shown_whole_in_the_plain_form() -> None:
    messages = [
        {"role": "user", "content": "Why metformin?"},
        {"role": "assistant", "content": "It lowers sugar.\n\nSources: MedlinePlus: x"},
    ]
    assert build_recap(messages) == "Patient: Why metformin?\nNora: It lowers sugar."
    assert build_recap([]) == NO_HISTORY


def test_a_long_conversation_stays_within_the_budget_newest_first_in_whole_turns() -> None:
    messages = _turns(200)
    window = recent_window(messages)
    assert sum(line.size for line in window) <= RECENT_CHARS
    assert window[0].speaker == "Patient"  # never starts in the middle of a turn
    assert window[-1].text.startswith("answer 199")
    assert len(window) > 6  # far more than the old three turns of 280 characters
    recap = build_recap(messages)
    assert len(recap) <= RECENT_CHARS
    assert window_start(messages) == window[0].index


def test_one_oversized_message_is_clipped_and_the_newest_turn_always_stays() -> None:
    messages = [{"role": "user", "content": "x" * 50000}, {"role": "assistant", "content": "ok"}]
    window = recent_window(messages)
    assert [line.speaker for line in window] == ["Patient", "Nora"]
    assert len(window[0].text) <= MESSAGE_CHARS
    many = [{"role": "user", "content": "y" * 1000} for _ in range(20)] + [
        {"role": "assistant", "content": "done"}
    ]
    kept = recent_window(many)
    assert sum(line.size for line in kept) <= RECENT_CHARS and kept[-1].text == "done"


def test_the_stored_summary_is_read_with_the_recent_messages_and_is_bounded() -> None:
    recap = build_recap(_turns(3), "The patient asked about metformin timing. " * 100)
    assert recap.startswith("Summary of the earlier part of this conversation")
    assert "Most recent messages:" in recap and "answer 2" in recap
    summary_part = recap.split("\n")[1]
    assert len(summary_part) <= SUMMARY_CHARS
    assert build_recap([], "Earlier: a question about timing.").endswith(
        "Earlier: a question about timing."
    )
