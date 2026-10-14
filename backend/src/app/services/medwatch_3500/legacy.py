"""Read 048-shape MedWatch drafts as Form 3500 v2 data, without losing anything.

``upgrade_legacy_form`` is pure and idempotent: v2 input comes back unchanged, and a 048
payload maps each value to its Form 3500 item or, when it has no safe home, to ``legacy``
(read-only text shown in the preview). The stored row is untouched until a clinician saves.
A name-bearing A1 identifier is the one value dropped: it is replaced by the default code.

The option matchers here are shared with prefill so stored text is read one way only.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Mapping
from datetime import date
from typing import Any, cast, get_args
from uuid import UUID

from app.models.enums import NaranjoCausality
from app.models.medwatch_form_3500 import (
    FORM_3500_VERSION,
    MAX_OTHER_PRODUCTS,
    DoseUnit,
    Frequency,
    MedWatchFormDataV2,
    Route,
)
from app.services.medwatch_3500.dates import clinic_today, coerce_date, earliest_day
from app.services.medwatch_3500.identifier import (
    PatientIdentity,
    default_code,
    identifier_violations,
)

FREQUENCY_OPTIONS: tuple[str, ...] = get_args(Frequency)
ROUTE_OPTIONS: tuple[str, ...] = get_args(Route)
DOSE_UNIT_OPTIONS: tuple[str, ...] = get_args(DoseUnit)

# The ``medication_route_enum`` values stored on medication records.
_ROUTE_ALIASES = {
    "oral": "Oral",
    "topical": "Topical",
    "iv": "Intravenous (not otherwise specified)",
    "im": "Intramuscular",
    "subcutaneous": "Subcutaneous",
    "inhaled": "Respiratory (inhalation)",
}
_UNIT_BY_ABBREVIATION = {
    option.rsplit("-", 1)[1].strip().casefold(): option for option in DOSE_UNIT_OPTIONS
}
_DOSE = re.compile(r"\s*(\d+(?:\.\d+)?)\s*([A-Za-z%/]+(?:\s?[A-Za-z]+)?)\s*")
_LIST_SPLIT = re.compile(r"[,;\n]")

_IDENTIFIER_MAX = 50
_NAME_MAX = 255
_OTHER_TEXT_MAX = 100
_NARRATIVE_MAX = 4000
_HISTORY_MAX = 2000
_EMAIL_MAX = 254
_RATIONALE_MAX = 2000


def match_frequency(text: str) -> tuple[str | None, str]:
    """(option, other text). Unmatched text becomes ``Other`` with the text kept.

    A bare "other" carries no description, so it maps to nothing.
    """
    value = text.strip()
    if not value or value.casefold() == "other":
        return None, ""
    for option in FREQUENCY_OPTIONS:
        if option != "Other" and option.casefold() == value.casefold():
            return option, ""
    return "Other", value


def match_route(text: str) -> tuple[str | None, str]:
    """(option, other text) from an option name or a stored medication route code."""
    value = text.strip()
    if not value or value.casefold() == "other":
        return None, ""
    for option in ROUTE_OPTIONS:
        if option != "Other" and option.casefold() == value.casefold():
            return option, ""
    alias = _ROUTE_ALIASES.get(value.casefold())
    if alias:
        return alias, ""
    return "Other", value


def split_dose(text: str) -> tuple[str, str] | None:
    """``("10", "MILLIGRAM(S) - MG")`` for ``"10 mg"``; ``None`` unless both parts match."""
    match = _DOSE.fullmatch(text)
    if not match:
        return None
    unit = _UNIT_BY_ABBREVIATION.get(match[2].replace(" ", "").casefold())
    if unit is None:
        unit = _UNIT_BY_ABBREVIATION.get(match[2].casefold())
    if unit is None or len(match[1]) > 50:
        return None
    return match[1], unit


def past_date(value: object, today: date) -> str | None:
    """A parsed date that is not after ``today``, else ``None``."""
    iso = coerce_date(value)
    if iso is None or earliest_day(iso) > today:
        return None
    return iso


def _section(data: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = data.get(key)
    return cast(Mapping[str, Any], value) if isinstance(value, Mapping) else {}


def _leaf_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


class _Upgrade:
    """Tracks which 048 leaves were used so every other value lands in ``legacy``."""

    def __init__(self, data: Mapping[str, Any]) -> None:
        self.data = data
        self.used: set[str] = set()
        self.legacy: dict[str, str] = {}

    def take(self, section: str, key: str) -> str:
        self.used.add(f"{section}.{key}")
        return _leaf_text(_section(self.data, section).get(key)).strip()

    def keep(self, path: str, value: str) -> None:
        if value.strip():
            self.legacy[path] = value

    def leftovers(self) -> None:
        for section, content in self.data.items():
            if isinstance(content, Mapping):
                for key, value in content.items():
                    path = f"{section}.{key}"
                    if path not in self.used:
                        self.keep(path, _leaf_text(value))
            else:
                self.keep(str(section), _leaf_text(content))


def upgrade_legacy_form(
    data: Mapping[str, Any] | None,
    *,
    draft_id: UUID,
    patient: PatientIdentity,
    today: date | None = None,
) -> dict[str, Any]:
    """Return v2 form data for a stored draft payload (v2 is returned unchanged)."""
    source: Mapping[str, Any] = data if isinstance(data, Mapping) else {}
    if source.get("form_version") == FORM_3500_VERSION:
        return copy.deepcopy(dict(source))
    day = today or clinic_today()
    up = _Upgrade(source)

    identifier = up.take("patient", "patient_identifier")
    if (
        not identifier
        or len(identifier) > _IDENTIFIER_MAX
        or identifier_violations(identifier, patient)
    ):
        if identifier and len(identifier) > _IDENTIFIER_MAX:
            up.keep("patient.patient_identifier", identifier)
        identifier = default_code(patient.first_name, patient.last_name, draft_id, patient)

    dob_text = up.take("patient", "date_of_birth")
    date_of_birth = past_date(dob_text, day)
    if date_of_birth is None:
        up.keep("patient.date_of_birth", dob_text)

    sex_text = up.take("patient", "sex")
    sex = {"female": "F", "f": "F", "male": "M", "m": "M"}.get(sex_text.casefold())
    if sex is None:
        up.keep("patient.sex", sex_text)

    onset_text = up.take("event", "onset_date_or_time")
    event_date = past_date(onset_text, day)
    if event_date is None:
        up.keep("event.onset_date_or_time", onset_text)

    description = _leaf_text(_section(source, "event").get("description"))
    up.used.add("event.description")
    narrative = description
    if len(description) > _NARRATIVE_MAX:
        narrative = description[:_NARRATIVE_MAX]
        up.keep("event.description", description)

    product_1, product_legacy = _legacy_product(up, day)
    others = _legacy_others(up)

    relevant_tests = _fitting(up, "tests_and_history", "relevant_tests", _HISTORY_MAX)
    other_history = _fitting(up, "tests_and_history", "other_relevant_history", _HISTORY_MAX)

    reporter_name = up.take("reporter", "name")
    first_name = last_name = ""
    parts = reporter_name.split()
    if len(parts) == 2 and all(len(part) <= 100 for part in parts):
        first_name, last_name = parts
    else:
        up.keep("reporter.name", reporter_name)
    email = _fitting(up, "reporter", "email", _EMAIL_MAX)

    review = _legacy_review(up)
    up.leftovers()
    for path, value in product_legacy.items():
        up.keep(path, value)

    form = {
        "form_version": FORM_3500_VERSION,
        "section_a": {"identifier": identifier, "date_of_birth": date_of_birth, "sex": sex},
        "section_b": {
            "event_date": event_date,
            "event_date_confirmed": False,
            "narrative": narrative,
            "tests_comments": relevant_tests,
            "other_history": other_history,
        },
        "section_d": {"product_1": product_1},
        "section_f": {"others": others},
        "section_g": {"first_name": first_name, "last_name": last_name, "email": email},
        "mediagent_review": review,
        "legacy": dict(sorted(up.legacy.items())),
    }
    validated = MedWatchFormDataV2.model_validate(form, context={"today": day})
    return validated.model_dump(mode="json")


def _fitting(up: _Upgrade, section: str, key: str, limit: int) -> str:
    value = up.take(section, key)
    if len(value) > limit:
        up.keep(f"{section}.{key}", value)
        return ""
    return value


def _legacy_product(up: _Upgrade, day: date) -> tuple[dict[str, Any], dict[str, str]]:
    kept: dict[str, str] = {}
    product: dict[str, Any] = {}
    name = up.take("suspect_product", "name")
    if len(name) <= _NAME_MAX:
        product["name"] = name
    else:
        kept["suspect_product.name"] = name

    dose_text = up.take("suspect_product", "dose")
    dose = split_dose(dose_text) if dose_text else None
    if dose:
        product["dose"], product["dose_unit"] = dose
    elif dose_text:
        kept["suspect_product.dose"] = dose_text

    for key, matcher, other in (
        ("frequency", match_frequency, "frequency_other"),
        ("route", match_route, "route_other"),
    ):
        text = up.take("suspect_product", key)
        option, other_text = matcher(text)
        if option and len(other_text) <= _OTHER_TEXT_MAX:
            product[key], product[other] = option, other_text
        elif text:
            kept[f"suspect_product.{key}"] = text

    start_text = up.take("suspect_product", "therapy_start_date")
    stop_text = up.take("suspect_product", "therapy_end_date")
    start = past_date(start_text, day)
    stop = past_date(stop_text, day)
    if start is None and start_text:
        kept["suspect_product.therapy_start_date"] = start_text
    if stop is not None and start is not None and earliest_day(stop) < earliest_day(start):
        stop = None
    if stop is None and stop_text:
        kept["suspect_product.therapy_end_date"] = stop_text
    product["therapy_start"], product["therapy_stop"] = start, stop
    return product, kept


def _legacy_others(up: _Upgrade) -> list[dict[str, Any]]:
    text = up.take("concomitant_products", "products")
    names = [part.strip() for part in _LIST_SPLIT.split(text) if part.strip()]
    if len(names) > MAX_OTHER_PRODUCTS or any(len(name) > _NAME_MAX for name in names):
        up.keep("concomitant_products.products", text)
        return []
    return [{"name": name} for name in names]


def _legacy_review(up: _Upgrade) -> dict[str, Any]:
    review: dict[str, Any] = {}
    section = _section(up.data, "clinical_review")
    for key in ("naranjo_score", "causality", "reportability_rationale"):
        up.used.add(f"clinical_review.{key}")
    score = section.get("naranjo_score")
    if isinstance(score, int) and not isinstance(score, bool) and -4 <= score <= 13:
        review["naranjo_score"] = score
    else:
        up.keep("clinical_review.naranjo_score", _leaf_text(score))
    causality = _leaf_text(section.get("causality"))
    if causality in {item.value for item in NaranjoCausality}:
        review["causality"] = causality
    else:
        up.keep("clinical_review.causality", causality)
    rationale = _leaf_text(section.get("reportability_rationale")).strip()
    if len(rationale) <= _RATIONALE_MAX:
        review["reportability_rationale"] = rationale
    else:
        up.keep("clinical_review.reportability_rationale", rationale)
    return review
