"""Capturing a symptom, and refusing to invent one.

The behaviour these pin replaced a rule-based extractor that ran whenever the model was
unavailable. It inferred the symptom from substrings and made up a severity: "worst
headache pain today" was recorded as severity 8, and "tengo dolor fuerte en el pecho" —
severe chest pain — as `symptom="reported symptom"`, severity 4, unflagged.

Those values were not only shown to the patient. They were written to `symptom_reports`,
counted toward the adverse-event signal, and read afterwards by a clinician as the
patient's own account of what happened. A guess that persists is worse than one that does
not, which is why the central assertion here is a negative one: a failed extraction writes
no report at all.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.config import settings
from app.followup import FOLLOWUP_COPY, SymptomExtractionResult, analyse_symptom
from app.followup import service as service_module
from app.models.enums import Language
from app.utils.localization import resolve_locale_resource

EXTRACTION = SymptomExtractionResult(
    symptom="dizziness",
    severity=4,
    onset="this morning",
    related_medication_name="Metformin",
    needs_follow_up=True,
    follow_up_question="When did this start?",
    flagged_for_adr=True,
    ai_assessment="Reported after a recent medication change.",
)


def _client(
    *,
    extraction: SymptomExtractionResult | None = EXTRACTION,
    reply: str | None = "Thanks for telling me about the dizziness.",
) -> MagicMock:
    """A stub Gemini client. `None` on either call means that step failed."""
    client = MagicMock()
    client.generate_structured = (
        AsyncMock(side_effect=RuntimeError("model unavailable"))
        if extraction is None
        else AsyncMock(return_value=extraction)
    )
    client.generate = (
        AsyncMock(side_effect=RuntimeError("model unavailable"))
        if reply is None
        else AsyncMock(return_value=reply)
    )
    return client


async def _analyse(client: MagicMock, message: str = "I feel dizzy", **kwargs: Any) -> Any:
    with patch.object(service_module, "_extraction_client", return_value=client):
        return await analyse_symptom(message=message, **kwargs)


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_read_symptom_is_recorded() -> None:
    result = await _analyse(_client())

    assert result.status == "success"
    assert result.symptom_report is not None
    assert result.symptom_report["symptom"] == "dizziness"
    assert result.symptom_report["severity"] == 4


@pytest.mark.asyncio
async def test_the_adverse_event_flag_is_carried_through() -> None:
    """This decides whether a clinician is asked to look, so it must not be dropped."""
    result = await _analyse(_client())

    assert result.flagged_for_adr is True
    assert result.follow_up_question == "When did this start?"


@pytest.mark.asyncio
async def test_the_patient_gets_the_model_s_reply() -> None:
    result = await _analyse(_client())

    assert result.response_text == "Thanks for telling me about the dizziness."


# ---------------------------------------------------------------------------
# The refusal to invent — the reason this module was rewritten
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_extraction_records_nothing() -> None:
    """The caller writes a row whenever `symptom_report` is set, so it must stay unset."""
    result = await _analyse(_client(extraction=None))

    assert result.symptom_report is None
    assert result.status == "degraded"


@pytest.mark.asyncio
async def test_a_failed_extraction_raises_no_adverse_event_signal() -> None:
    """An unread symptom must not reach the clinician queue as though it had been read."""
    result = await _analyse(_client(extraction=None))

    assert result.flagged_for_adr is False


@pytest.mark.asyncio
async def test_a_failed_extraction_tells_the_patient() -> None:
    expected = resolve_locale_resource(Language.EN.value, FOLLOWUP_COPY)["report_unavailable"]

    result = await _analyse(_client(extraction=None))

    assert result.response_text == expected


@pytest.mark.asyncio
async def test_the_failure_message_still_points_at_emergency_care() -> None:
    """It reaches people who are unwell; "I could not record that" alone is not enough."""
    result = await _analyse(_client(extraction=None))

    assert "911" in result.response_text


@pytest.mark.asyncio
async def test_a_spanish_patient_is_told_in_spanish() -> None:
    result = await _analyse(_client(extraction=None), language=Language.ES)

    assert result.response_text.startswith("No pude registrar")


@pytest.mark.asyncio
async def test_severe_wording_is_never_invented_from_the_message() -> None:
    """The old extractor read "severe" and wrote severity 8 with nobody having read it."""
    result = await _analyse(
        _client(extraction=None), message="Severe crushing pain, worst imaginable"
    )

    assert result.symptom_report is None


# ---------------------------------------------------------------------------
# A failed reply is not a failed reading
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_reply_still_records_what_was_read() -> None:
    """Extraction succeeded, so the report is real even though the prose call failed."""
    result = await _analyse(_client(reply=None))

    assert result.status == "success"
    assert result.symptom_report is not None
    assert result.symptom_report["symptom"] == "dizziness"


@pytest.mark.asyncio
async def test_a_composed_reply_states_only_extracted_values() -> None:
    result = await _analyse(_client(reply=None))

    assert "dizziness" in result.response_text
    assert "4" in result.response_text


@pytest.mark.asyncio
async def test_a_severe_reading_adds_same_day_guidance() -> None:
    severe = EXTRACTION.model_copy(update={"severity": 9})

    result = await _analyse(_client(extraction=severe, reply=None))

    assert "care team today" in result.response_text


@pytest.mark.asyncio
async def test_a_moderate_reading_does_not_add_it() -> None:
    """The threshold has to bite in one direction only, or it says nothing."""
    result = await _analyse(_client(reply=None))

    assert "care team today" not in result.response_text


# ---------------------------------------------------------------------------
# Switches and edges
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_empty_message_is_not_sent_to_a_model() -> None:
    client = _client()

    result = await _analyse(client, message="   ")

    assert result.status == "degraded"
    assert result.response_text == ""
    client.generate_structured.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_kill_switch_records_nothing_rather_than_guessing() -> None:
    """Turning the model off is not a licence to write a report nobody read."""
    client = _client()

    # Patched on the settings object itself, which is the singleton the registry reads
    # through `route.is_enabled()`. Patching a name on this module would miss it.
    with patch.object(settings, "adr_extraction_ai_enabled", False):
        result = await _analyse(client, message="I feel dizzy")

    assert result.symptom_report is None
    client.generate_structured.assert_not_awaited()


def test_a_workload_routed_elsewhere_fails_loudly() -> None:
    """Sending a bare model id to the wrong SDK reads like an outage, not a misconfig."""
    route = MagicMock()
    route.primary.transport = "invented-transport"
    route.primary.key = "mystery"

    with patch.object(service_module, "route_for", return_value=route), pytest.raises(ValueError):
        service_module._extraction_client()
