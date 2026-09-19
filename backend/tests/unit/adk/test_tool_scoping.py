"""A model must not be able to choose whose records a tool reads.

This is the sole control: RLS policies key off `auth.uid()`, and tools hold the
service-role client, so there is no database-level filter behind this function. The most
important test here is the signature one — it pins that no patient identifier is part of
any tool's surface, which is a stronger guarantee than validating one that was passed.
"""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.adk.tools import PATIENT_ID_STATE_KEY, PatientScopeError, require_patient_id

PATIENT_ID = str(uuid4())


def _context(state: dict[str, object] | None) -> SimpleNamespace:
    return SimpleNamespace(state=state)


def test_the_patient_comes_from_session_state() -> None:
    assert require_patient_id(_context({PATIENT_ID_STATE_KEY: PATIENT_ID})) == PATIENT_ID


def test_no_patient_identifier_is_part_of_the_tool_surface() -> None:
    """The guarantee: a model cannot name the patient, because there is no way to.

    Validating a model-supplied identifier would be weaker — prompt injection only has to
    win once against a check, whereas an argument that does not exist cannot be supplied.
    """
    parameters = list(inspect.signature(require_patient_id).parameters)

    assert parameters == ["tool_context"]


def test_an_absent_patient_raises_rather_than_defaulting() -> None:
    """Reading "no patient" would either return nothing or, worse, return everyone."""
    with pytest.raises(PatientScopeError):
        require_patient_id(_context({}))


def test_a_missing_state_raises() -> None:
    with pytest.raises(PatientScopeError):
        require_patient_id(_context(None))


@pytest.mark.parametrize("value", [None, "", "   "])
def test_an_empty_identifier_raises(value: object) -> None:
    with pytest.raises(PatientScopeError):
        require_patient_id(_context({PATIENT_ID_STATE_KEY: value}))


@pytest.mark.parametrize(
    "value",
    [
        "not-a-uuid",
        "1",
        "' OR 1=1 --",
        "00000000-0000-0000-0000-00000000000",  # one character short
    ],
)
def test_a_malformed_identifier_is_refused(value: str) -> None:
    """A malformed identifier reaching a query is how a filter stops filtering."""
    with pytest.raises(PatientScopeError):
        require_patient_id(_context({PATIENT_ID_STATE_KEY: value}))


def test_the_rejected_value_is_not_echoed_in_the_error() -> None:
    """It claimed to identify a patient; it does not belong in a message or a log."""
    secret = "maria-gomez-record-42"

    with pytest.raises(PatientScopeError) as raised:
        require_patient_id(_context({PATIENT_ID_STATE_KEY: secret}))

    assert secret not in str(raised.value)


def test_a_uuid_object_is_accepted_and_normalised() -> None:
    """State may carry a UUID rather than a string; both must resolve identically."""
    identifier = uuid4()

    assert require_patient_id(_context({PATIENT_ID_STATE_KEY: identifier})) == str(identifier)


def test_surrounding_whitespace_does_not_defeat_validation() -> None:
    assert require_patient_id(_context({PATIENT_ID_STATE_KEY: f"  {PATIENT_ID}  "})) == PATIENT_ID


def test_the_state_key_is_durable_not_temp_scoped() -> None:
    """The subject of a conversation belongs to the session, not to a single turn."""
    assert not PATIENT_ID_STATE_KEY.startswith("temp:")
