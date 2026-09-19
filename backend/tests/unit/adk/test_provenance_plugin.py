"""A record written during a run must be able to say which model produced it.

`source_provenances.model_version` went unfilled for years because nothing carried the
answering model forward to the write. These tests pin the carrying, including the two
cases where writing something would be worse than writing nothing.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.adk.plugins import PROVENANCE_AGENT_KEY, PROVENANCE_MODEL_KEY, ProvenancePlugin


def _context(agent: str = "document_evidence") -> SimpleNamespace:
    return SimpleNamespace(agent_name=agent, state={}, invocation_id="inv-1")


def _response(**overrides: object) -> SimpleNamespace:
    base: dict[str, object] = {"partial": False, "model_version": "gemini-3.8-flash"}
    base.update(overrides)
    return SimpleNamespace(**base)


async def _run(context: SimpleNamespace, response: SimpleNamespace) -> None:
    await ProvenancePlugin().after_model_callback(callback_context=context, llm_response=response)


@pytest.mark.asyncio
async def test_the_answering_model_is_stamped_into_state() -> None:
    context = _context()

    await _run(context, _response())

    assert context.state[PROVENANCE_MODEL_KEY] == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_the_agent_is_recorded_alongside_it() -> None:
    context = _context("medication_safety")

    await _run(context, _response())

    assert context.state[PROVENANCE_AGENT_KEY] == "medication_safety"


@pytest.mark.asyncio
async def test_the_keys_are_temp_scoped() -> None:
    """ADK trims `temp:` state before persisting, so this cannot go stale in a session.

    A durable key would leave a "last model used" value behind that a later turn could
    read and stamp onto a candidate the model never produced.
    """
    assert PROVENANCE_MODEL_KEY.startswith("temp:")
    assert PROVENANCE_AGENT_KEY.startswith("temp:")


@pytest.mark.asyncio
async def test_a_streaming_chunk_does_not_stamp() -> None:
    """The final response carries the authoritative model; chunks are not answers."""
    context = _context()

    await _run(context, _response(partial=True))

    assert context.state == {}


@pytest.mark.asyncio
async def test_a_missing_model_leaves_the_key_unset() -> None:
    """Absent is honest; blank is indistinguishable from "recorded nothing"."""
    context = _context()

    await _run(context, _response(model_version=None))

    assert PROVENANCE_MODEL_KEY not in context.state


@pytest.mark.asyncio
async def test_the_most_recent_model_wins() -> None:
    """Two calls in a turn: the stamp must describe the answer that was actually used."""
    context = _context()

    await _run(context, _response(model_version="gemini-3.1-flash-lite"))
    await _run(context, _response(model_version="gemini-3.8-flash"))

    assert context.state[PROVENANCE_MODEL_KEY] == "gemini-3.8-flash"


@pytest.mark.asyncio
async def test_a_missing_state_does_not_break_the_turn() -> None:
    context = SimpleNamespace(agent_name="care_coordinator", state=None)

    await _run(context, _response())  # must not raise


@pytest.mark.asyncio
async def test_a_failing_state_write_does_not_break_the_turn() -> None:
    """Bookkeeping must not cost the patient their answer."""

    class _Hostile(dict[str, object]):
        def __setitem__(self, key: str, value: object) -> None:
            raise RuntimeError("state is read-only here")

    context = SimpleNamespace(agent_name="care_coordinator", state=_Hostile())

    await _run(context, _response())  # must not raise


def test_the_plugin_is_named_for_the_runner_to_register() -> None:
    assert ProvenancePlugin().name == "provenance"
