"""The words a patient sees in an emergency, in both supported locales.

This copy used to live inside the LangGraph triage module, which is scheduled for
deletion. These tests pin it in its own right so that removing the agent runtime cannot
quietly remove the emergency and self-harm responses with it.
"""

from __future__ import annotations

import pytest

from app.models.enums import Language
from app.safety import TRIAGE_COPY
from app.utils.localization import resolve_locale_resource

# The two a patient must never receive in the wrong language, or not at all.
CRITICAL_KEYS = ("emergency_response", "mental_health_emergency_response")

SUPPORTED_LOCALES = (Language.EN.value, Language.ES.value)


def test_a_default_entry_exists() -> None:
    """`resolve_locale_resource` raises without one, which would break every lookup."""
    assert "default" in TRIAGE_COPY


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_every_supported_locale_is_spelled_out(locale: str) -> None:
    """Not left to the English fallback: an emergency is the worst moment to fall back."""
    assert locale in TRIAGE_COPY


@pytest.mark.parametrize("locale", (*SUPPORTED_LOCALES, "default"))
@pytest.mark.parametrize("key", CRITICAL_KEYS)
def test_the_critical_responses_are_present_and_non_empty(locale: str, key: str) -> None:
    assert TRIAGE_COPY[locale][key].strip()


@pytest.mark.parametrize("key", CRITICAL_KEYS)
def test_spanish_is_translated_rather_than_copied(key: str) -> None:
    """A copy-paste of the English string would pass a presence check and fail a patient."""
    assert TRIAGE_COPY[Language.ES.value][key] != TRIAGE_COPY[Language.EN.value][key]


@pytest.mark.parametrize("locale", (*SUPPORTED_LOCALES, "default"))
def test_the_emergency_response_names_the_emergency_number(locale: str) -> None:
    """The instruction has to be actionable, not a suggestion to seek help generally."""
    assert "911" in TRIAGE_COPY[locale]["emergency_response"]


@pytest.mark.parametrize("locale", (*SUPPORTED_LOCALES, "default"))
def test_the_self_harm_response_names_the_crisis_line(locale: str) -> None:
    assert "988" in TRIAGE_COPY[locale]["mental_health_emergency_response"]


def test_every_locale_offers_the_same_set_of_keys() -> None:
    """A key present in one language and missing in another is a silent English fallback."""
    expected = set(TRIAGE_COPY["default"])
    for locale in SUPPORTED_LOCALES:
        assert set(TRIAGE_COPY[locale]) == expected


@pytest.mark.parametrize("locale", SUPPORTED_LOCALES)
def test_resolution_returns_that_locale_rather_than_falling_back(locale: str) -> None:
    """Proves the map is shaped the way the accessor expects, not merely well populated."""
    resolved = resolve_locale_resource(locale, TRIAGE_COPY)

    assert resolved is TRIAGE_COPY[locale]


def test_an_unknown_locale_still_resolves() -> None:
    """A patient with an unexpected locale must still be told to call 911."""
    resolved = resolve_locale_resource("fr-FR", TRIAGE_COPY)

    assert "911" in resolved["emergency_response"]


@pytest.mark.parametrize("locale", (*SUPPORTED_LOCALES, "default"))
def test_an_outage_message_exists_in_every_locale(locale: str) -> None:
    """When the model is unavailable the patient is told so, not handed a guess."""
    assert TRIAGE_COPY[locale]["service_unavailable"].strip()


@pytest.mark.parametrize("locale", (*SUPPORTED_LOCALES, "default"))
def test_the_outage_message_still_routes_a_real_emergency(locale: str) -> None:
    """ "We are having trouble" alone is unsafe if the person is actually unwell.

    The deterministic floor still answers an explicit emergency during an outage, but this
    message is what someone sees when their wording did not trip it — so it has to say
    where to go.
    """
    assert "911" in TRIAGE_COPY[locale]["service_unavailable"]


@pytest.mark.parametrize("locale", (*SUPPORTED_LOCALES, "default"))
def test_the_outage_message_makes_no_clinical_claim(locale: str) -> None:
    """It must not imply we understood the question, because we did not."""
    message = TRIAGE_COPY[locale]["service_unavailable"].lower()

    for implied_understanding in ("your medication", "your symptom", "tu medicamento"):
        assert implied_understanding not in message


def test_spanish_outage_copy_is_translated_rather_than_copied() -> None:
    assert (
        TRIAGE_COPY[Language.ES.value]["service_unavailable"]
        != TRIAGE_COPY[Language.EN.value]["service_unavailable"]
    )
