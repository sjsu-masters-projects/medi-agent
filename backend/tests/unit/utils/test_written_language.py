"""Chat messages are labelled with the language they are written in."""

from __future__ import annotations

import pytest

from app.models.enums import Language
from app.utils.localization import written_language


@pytest.mark.parametrize(
    "text,declared,expected",
    [
        # The screenshot case: Spanish typed in an app set to English.
        ("¿Y qué pasa si se me olvida una dosis?", "en-US", Language.ES),
        ("What is metformin for, in simple words?", "es-MX", Language.EN),
        (
            "Como cada caso puede ser distinto, te recomiendo consultar con tu equipo.",
            "en-US",
            Language.ES,
        ),
        # Too short to tell: keep the app language rather than guess.
        ("ok", "es-MX", Language.ES),
        ("metformina?", "en-US", Language.EN),
        ("Metformin 500 mg", "es-MX", Language.ES),
    ],
)
def test_written_language(text: str, declared: str, expected: Language) -> None:
    assert written_language(text, declared) == expected
