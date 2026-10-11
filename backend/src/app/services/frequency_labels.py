"""Patient-language labels for recognised cadence phrases on single-language records.

Bilingual care-plan wording carries its own reviewed frequency text. Older rows hold one
phrase in whatever language it was entered; a phrase from the bounded vocabulary that
reminder parsing already recognises can be shown in either language. Anything else is
returned unchanged, never machine-translated.
"""

from __future__ import annotations

from app.services.reminder_schedule_service import DAY_ORDER, normalize_supported_frequency

_LABELS: dict[str, tuple[str, str]] = {
    "daily": ("Daily", "Todos los días"),
    "once daily": ("Once daily", "Una vez al día"),
    "twice daily": ("Twice daily", "Dos veces al día"),
    "three times daily": ("Three times daily", "Tres veces al día"),
    "every 8 hours": ("Every 8 hours", "Cada 8 horas"),
    "once weekly": ("Once weekly", "Una vez por semana"),
    "three times per week": ("Three times per week", "Tres veces por semana"),
    "with breakfast and dinner": ("With breakfast and dinner", "Con el desayuno y la cena"),
    "with each meal": ("With each meal", "Con cada comida"),
    "before bed": ("Before bed", "Antes de acostarse"),
    "each day before breakfast": (
        "Each day before breakfast",
        "Todos los días antes del desayuno",
    ),
    "as recorded": ("As recorded", "Según lo registrado"),
}
_DAYS = dict(
    zip(
        DAY_ORDER,
        zip(
            ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
            ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"],
            strict=True,
        ),
        strict=True,
    )
)


def _join(words: list[str], conjunction: str) -> str:
    return words[0] if len(words) == 1 else f"{', '.join(words[:-1])} {conjunction} {words[-1]}"


def localized_frequency(frequency: str, locale: str) -> str | None:
    """Return the label in ``locale`` for a recognised phrase, else None."""
    canonical = normalize_supported_frequency(frequency)
    spanish = locale == "es-MX"
    if canonical in _LABELS:
        return _LABELS[canonical][1 if spanish else 0]
    days = [part.strip() for part in canonical.split(",")]
    if days and all(day in _DAYS for day in days):
        names = [_DAYS[day][1 if spanish else 0] for day in days]
        label = _join(names, "y" if spanish else "and")
        return label[0].upper() + label[1:]
    return None
