"""Approved wording follows the patient's saved language; older rows are shown as written."""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.services.feed_service import FeedService, FeedSnapshot
from app.services.frequency_labels import localized_frequency
from app.services.patient_wording import patient_text

WORDING = {
    "en-US": {"title": "Walk", "instructions": "Walk 20 minutes", "frequency": "Daily"},
    "es-MX": {"title": "Caminar", "instructions": "Camine 20 minutos", "frequency": "Diario"},
}


@pytest.mark.parametrize("locale", ["en-US", "es-MX"])
def test_bilingual_rows_follow_the_saved_language(locale) -> None:
    text = patient_text(
        "obligation",
        {
            "description": "Walk",
            "notes": "Walk 20 minutes",
            "frequency": "daily",
            "patient_wording": WORDING,
        },
        locale,
    )
    assert text == {
        "name": WORDING[locale]["title"],
        "description": WORDING[locale]["instructions"],
        "frequency": WORDING[locale]["frequency"],
        "content_locale": locale,
    }


def test_legacy_medication_keeps_its_text_and_localizes_known_cadence() -> None:
    text = patient_text(
        "medication",
        {"name": "Metformin", "dosage": "500 mg", "frequency": "twice daily", "instructions": None},
        "es-MX",
    )
    assert text["name"] == "Metformin 500 mg"
    assert text["frequency"] == "Dos veces al día"
    assert text["content_locale"] is None


def test_legacy_activity_reports_its_language_for_labelling() -> None:
    text = patient_text(
        "obligation",
        {
            "description": "Revise su glucosa en ayunas antes del desayuno",
            "notes": None,
            "frequency": "todos los días",
        },
        "en-US",
    )
    assert text["frequency"] == "Daily"
    assert text["content_locale"] == "es-MX"


@pytest.mark.parametrize(
    "phrase,locale,expected",
    [
        ("los lunes, miércoles y viernes", "en-US", "Monday, Wednesday and Friday"),
        ("monday, wednesday, friday", "es-MX", "Lunes, miércoles y viernes"),
        ("Dos veces al día", "en-US", "Twice daily"),
        ("as recorded", "es-MX", "Según lo registrado"),
        ("once after each walking session", "es-MX", None),
    ],
)
def test_frequency_labels_cover_only_the_recognised_vocabulary(phrase, locale, expected) -> None:
    assert localized_frequency(phrase, locale) == expected


def test_feed_renders_tasks_in_the_snapshot_language() -> None:
    obligation = {
        "id": str(UUID(int=1)),
        "description": "Walk",
        "notes": "Walk 20 minutes",
        "frequency": "daily",
        "obligation_type": "exercise",
        "patient_wording": WORDING,
        "care_teams": None,
    }
    feed = FeedService(db=None).render_snapshot(  # type: ignore[arg-type]
        FeedSnapshot(
            date(2026, 10, 10), "America/Los_Angeles", [], [obligation], {}, locale="es-MX"
        )
    )
    (task,) = feed["tasks"]
    assert task["name"] == "Caminar"
    assert task["description"] == "Camine 20 minutos"
    assert task["frequency"] == "Diario"
    assert task["content_locale"] == "es-MX"
