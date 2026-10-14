"""Form 3500 date encoding: ISO storage, ``dd-mmm-yyyy`` on the official form.

Drafts store ISO ``YYYY-MM-DD`` or, where FDA accepts a month and year (B3), ``YYYY-MM``.
The PDF prints ``03-Oct-2026`` or ``Oct-2026``. Month abbreviations come from a fixed
English tuple, never ``strftime``, so the process locale cannot change the output.
"""

from __future__ import annotations

import re
from calendar import monthrange
from datetime import date, datetime
from zoneinfo import ZoneInfo

CLINIC_TIMEZONE = ZoneInfo("America/Los_Angeles")

MONTH_ABBREVIATIONS: tuple[str, ...] = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_MONTH_NAMES: tuple[str, ...] = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTH_INDEX = {name.casefold(): index for index, name in enumerate(MONTH_ABBREVIATIONS, 1)}
_MONTH_INDEX.update({name: index for index, name in enumerate(_MONTH_NAMES, 1)})

_ISO_FULL = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_ISO_MONTH = re.compile(r"(\d{4})-(\d{2})")
_FDA_FULL = re.compile(r"(\d{1,2})[- ]([A-Za-z]{3})[- ](\d{4})")
_FDA_MONTH = re.compile(r"([A-Za-z]{3})[- ](\d{4})")
_US_FULL = re.compile(r"(\d{1,2})/(\d{1,2})/(\d{4})")
_NAMED_MONTH = re.compile(r"([A-Za-z]+)\.?,?\s+(\d{4})")
_NAMED_FULL = re.compile(r"([A-Za-z]+)\.?\s+(\d{1,2}),?\s+(\d{4})")

MIN_YEAR = 1900
MAX_YEAR = 2100


def _checked_iso(year: int, month: int, day: int | None) -> str:
    if not MIN_YEAR <= year <= MAX_YEAR or not 1 <= month <= 12:
        raise ValueError("Date is outside the supported range")
    if day is None:
        return f"{year:04d}-{month:02d}"
    if not 1 <= day <= monthrange(year, month)[1]:
        raise ValueError("Day is not valid for the month")
    return f"{year:04d}-{month:02d}-{day:02d}"


def validate_iso_date(value: str) -> str:
    """Return ``value`` when it is a real ISO full date or month and year."""
    full = _ISO_FULL.fullmatch(value)
    if full:
        return _checked_iso(int(full[1]), int(full[2]), int(full[3]))
    month = _ISO_MONTH.fullmatch(value)
    if month:
        return _checked_iso(int(month[1]), int(month[2]), None)
    raise ValueError("Use YYYY-MM-DD or YYYY-MM")


def fda_date(value: str) -> str:
    """Encode a stored ISO date as Form 3500 text (``03-Oct-2026`` or ``Oct-2026``)."""
    iso = validate_iso_date(value)
    year, month = int(iso[0:4]), int(iso[5:7])
    abbreviation = MONTH_ABBREVIATIONS[month - 1]
    if len(iso) == 7:
        return f"{abbreviation}-{year:04d}"
    return f"{int(iso[8:10]):02d}-{abbreviation}-{year:04d}"


def parse_fda_date(text: str) -> str:
    """Decode Form 3500 date text back to ISO. Raises ``ValueError`` for anything else."""
    value = text.strip()
    full = _FDA_FULL.fullmatch(value)
    if full and full[2].casefold() in _MONTH_INDEX:
        return _checked_iso(int(full[3]), _MONTH_INDEX[full[2].casefold()], int(full[1]))
    month = _FDA_MONTH.fullmatch(value)
    if month and month[1].casefold() in _MONTH_INDEX:
        return _checked_iso(int(month[2]), _MONTH_INDEX[month[1].casefold()], None)
    raise ValueError("Use dd-mmm-yyyy or mmm-yyyy")


def coerce_date(text: object) -> str | None:
    """Read a stored date in a common unambiguous shape, or return ``None``.

    Accepts ISO, Form 3500 text, ``MM/DD/YYYY``, ISO timestamps (date part only) and
    English month names. Free text such as "a few hours after starting" returns
    ``None``; nothing is guessed.
    """
    if isinstance(text, datetime):
        return _checked_or_none(text.year, text.month, text.day)
    if isinstance(text, date):
        return _checked_or_none(text.year, text.month, text.day)
    if not isinstance(text, str):
        return None
    value = text.strip()
    if not value:
        return None
    for parser in (validate_iso_date, parse_fda_date):
        try:
            return parser(value)
        except ValueError:
            pass
    if len(value) > 10 and value[10] in "T " and _ISO_FULL.fullmatch(value[:10]):
        return _iso_or_none(value[:10])
    us = _US_FULL.fullmatch(value)
    if us:
        return _checked_or_none(int(us[3]), int(us[1]), int(us[2]))
    named_full = _NAMED_FULL.fullmatch(value)
    if named_full and named_full[1].casefold() in _MONTH_INDEX:
        return _checked_or_none(
            int(named_full[3]), _MONTH_INDEX[named_full[1].casefold()], int(named_full[2])
        )
    named = _NAMED_MONTH.fullmatch(value)
    if named and named[1].casefold() in _MONTH_INDEX:
        return _checked_or_none(int(named[2]), _MONTH_INDEX[named[1].casefold()], None)
    return None


def _iso_or_none(value: str) -> str | None:
    try:
        return validate_iso_date(value)
    except ValueError:
        return None


def _checked_or_none(year: int, month: int, day: int | None) -> str | None:
    try:
        return _checked_iso(year, month, day)
    except ValueError:
        return None


def earliest_day(value: str) -> date:
    """First calendar day an ISO full or month-and-year date can mean."""
    iso = validate_iso_date(value)
    return date(int(iso[0:4]), int(iso[5:7]), int(iso[8:10]) if len(iso) == 10 else 1)


def latest_day(value: str) -> date:
    """Last calendar day an ISO full or month-and-year date can mean."""
    iso = validate_iso_date(value)
    year, month = int(iso[0:4]), int(iso[5:7])
    return date(year, month, int(iso[8:10]) if len(iso) == 10 else monthrange(year, month)[1])


def clinic_today(now: datetime | None = None) -> date:
    """The calendar date in the clinic's time zone (America/Los_Angeles)."""
    return (now or datetime.now(CLINIC_TIMEZONE)).astimezone(CLINIC_TIMEZONE).date()


def clinic_date_of(timestamp: object) -> str | None:
    """ISO date, in the clinic's time zone, of a stored ``timestamptz`` value."""
    if isinstance(timestamp, datetime):
        moment = timestamp
    elif isinstance(timestamp, str) and timestamp.strip():
        try:
            moment = datetime.fromisoformat(timestamp.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    if moment.tzinfo is None:
        return None
    return clinic_today(moment).isoformat()
