"""Non-identifying A1 patient identifier and name checks for Form 3500 free text.

FDA holds the A1 identifier in confidence and asks reporters not to identify any patient,
physician or institution by name in the narrative. The default identifier is the patient's
initials and four base32 characters of a SHA-256 of the draft ID: stable for the draft,
and revealing no UUID, email, phone or date of birth. Matching ignores case and accents.
"""

from __future__ import annotations

import base64
import hashlib
import re
import unicodedata
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from itertools import product
from string import ascii_uppercase
from typing import Literal
from uuid import UUID

from app.models.medwatch_form_3500 import MedWatchFormDataV2, MedWatchNameWarning
from app.services.medwatch_3500.dates import MONTH_ABBREVIATIONS, coerce_date

DEFAULT_CODE_PATTERN = re.compile(r"^[A-Z]{2}-[A-Z2-7]{4}$")
_WINDOW = 4
_MAX_ROUNDS = 64
_TOKEN_SPLIT = re.compile(r"[^0-9a-z]+")

IdentifierViolation = Literal["full_name", "name_token", "email", "date_of_birth"]


@dataclass(frozen=True)
class PatientIdentity:
    """The patient facts an identifier or narrative must not reveal."""

    first_name: str = ""
    last_name: str = ""
    email: str = ""
    date_of_birth: str | date | None = None


@dataclass(frozen=True)
class NameSources:
    """Names that must not appear in B5, B6, B7 or F text."""

    patient_names: Sequence[tuple[str, str]] = ()
    clinician_names: Sequence[tuple[str, str]] = ()
    clinic_names: Sequence[str] = field(default_factory=tuple)


def fold(text: str) -> str:
    """Casefold and strip accents (NFKD, combining marks removed)."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def tokens(text: str) -> list[str]:
    """Folded alphanumeric tokens, split on anything else."""
    return [token for token in _TOKEN_SPLIT.split(fold(text)) if token]


def _compact(text: str) -> str:
    return "".join(tokens(text))


def _initial(name: str) -> str:
    for char in fold(name).upper():
        if char in ascii_uppercase:
            return char
        if char.isalnum():
            break
    return "X"


def _name_tokens(first: str, last: str) -> set[str]:
    words = set(tokens(first)) | set(tokens(last))
    # A hyphenated or multi-part name also matches written together ("smithjones").
    for part in (first, last):
        compact = _compact(part)
        if compact:
            words.add(compact)
    return words


def _date_forms(value: str | date | None) -> tuple[set[str], set[str]]:
    """(separated forms, digit-only forms) of a full date of birth."""
    iso = coerce_date(value)
    if iso is None or len(iso) != 10:
        return set(), set()
    year, month, day = iso[0:4], iso[5:7], iso[8:10]
    abbreviation = MONTH_ABBREVIATIONS[int(month) - 1]
    separated = {
        iso,
        f"{month}/{day}/{year}",
        f"{int(month)}/{int(day)}/{year}",
        fold(f"{day}-{abbreviation}-{year}"),
    }
    digits = {f"{year}{month}{day}", f"{month}{day}{year}", f"{day}{month}{year}"}
    return separated, digits


def identifier_violations(value: str, patient: PatientIdentity) -> list[IdentifierViolation]:
    """Why ``value`` identifies the patient (empty when it does not)."""
    violations: list[IdentifierViolation] = []
    folded = fold(value)
    value_tokens = set(tokens(value))
    compact = _compact(value)
    full = _compact(patient.first_name) + _compact(patient.last_name)
    reverse = _compact(patient.last_name) + _compact(patient.first_name)
    if full and (full in compact or reverse in compact):
        violations.append("full_name")
    if _name_tokens(patient.first_name, patient.last_name) & value_tokens:
        violations.append("name_token")
    email = fold(patient.email.strip())
    if email:
        local = email.split("@", 1)[0]
        local_compact = _compact(local)
        if (
            email in folded
            or (local and local in folded and len(local_compact) >= _WINDOW)
            or (local_compact and local_compact in value_tokens)
            or (len(local_compact) >= _WINDOW and local_compact in compact)
        ):
            violations.append("email")
    separated, digits = _date_forms(patient.date_of_birth)
    digits_only = re.sub(r"\D", "", value)
    if any(form in folded for form in separated) or any(form in digits_only for form in digits):
        violations.append("date_of_birth")
    return violations


def _windows(draft_id: UUID) -> Iterator[str]:
    digest = hashlib.sha256(draft_id.bytes).digest()
    for _ in range(_MAX_ROUNDS):
        encoded = base64.b32encode(digest).decode("ascii").rstrip("=")
        for start in range(len(encoded) - _WINDOW + 1):
            yield encoded[start : start + _WINDOW]
        digest = hashlib.sha256(digest).digest()


def _prefixes(first: str, last: str) -> Iterator[str]:
    yield _initial(first) + _initial(last)
    # Initials that are themselves a name token (for example "Al") cannot be used.
    for pair in product(("X", "Z", *ascii_uppercase), repeat=2):
        yield "".join(pair)


def default_code(
    first_name: str,
    last_name: str,
    draft_id: UUID,
    patient: PatientIdentity | None = None,
) -> str:
    """The D16 default A1 identifier: ``<initials>-<4 base32 characters>``."""
    identity = patient or PatientIdentity(first_name=first_name, last_name=last_name)
    for prefix in _prefixes(first_name, last_name):
        if identifier_violations(prefix, identity):
            continue
        for window in _windows(draft_id):
            candidate = f"{prefix}-{window}"
            if not identifier_violations(candidate, identity):
                return candidate
    raise ValueError("No non-identifying code is available for this draft")


def _person_tokens(names: Iterable[tuple[str, str]]) -> set[str]:
    found: set[str] = set()
    for first, last in names:
        found |= {token for token in _name_tokens(first, last) if len(token) > 1}
    return found


def _contains_phrase(text_tokens: list[str], phrase: list[str]) -> bool:
    if not phrase:
        return False
    width = len(phrase)
    return any(text_tokens[i : i + width] == phrase for i in range(len(text_tokens) - width + 1))


def name_text_paths(form: MedWatchFormDataV2) -> list[tuple[str, str]]:
    """``(path, text)`` for every B5, B6, B7 and F free-text item, in form order."""
    b = form.section_b
    items = [("section_b.narrative", b.narrative)]
    for index, row in enumerate(b.tests):
        items.extend(
            [
                (f"section_b.tests[{index}].test", row.test),
                (f"section_b.tests[{index}].low_range", row.low_range),
                (f"section_b.tests[{index}].high_range", row.high_range),
            ]
        )
    items.append(("section_b.tests_comments", b.tests_comments))
    items.append(("section_b.other_history", b.other_history))
    items.extend(
        (f"section_f.others[{index}].name", other.name)
        for index, other in enumerate(form.section_f.others)
    )
    return items


def name_warnings(form: MedWatchFormDataV2, names: NameSources) -> list[MedWatchNameWarning]:
    """Advisory warnings for names in B5, B6, B7 and F text, one per path and kind."""
    patient_tokens = _person_tokens(names.patient_names)
    clinician_tokens = _person_tokens(names.clinician_names)
    clinic_phrases = [tokens(name) for name in names.clinic_names if tokens(name)]
    warnings: list[MedWatchNameWarning] = []
    for path, text in name_text_paths(form):
        if not text.strip():
            continue
        text_tokens = tokens(text)
        token_set = set(text_tokens)
        if patient_tokens & token_set:
            warnings.append(MedWatchNameWarning(path=path, kind="patient_name"))
        if clinician_tokens & token_set:
            warnings.append(MedWatchNameWarning(path=path, kind="clinician_name"))
        if any(_contains_phrase(text_tokens, phrase) for phrase in clinic_phrases):
            warnings.append(MedWatchNameWarning(path=path, kind="clinic_name"))
    return warnings
