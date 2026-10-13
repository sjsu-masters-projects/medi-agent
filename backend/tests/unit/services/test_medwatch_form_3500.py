"""Form 3500 v2 model, date encoding and validators (R16.1 to R16.4, R16.7, R21.3)."""

import calendar
import locale
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.models.medwatch_form_3500 import FORM_3500_VERSION, MedWatchFormDataV2
from app.services.medwatch_3500.dates import (
    MONTH_ABBREVIATIONS,
    clinic_date_of,
    coerce_date,
    fda_date,
    parse_fda_date,
)
from tests.unit.services.medwatch_3500_fixtures import CONTEXT, TODAY, full_form, full_payload


def _validate(payload: dict) -> MedWatchFormDataV2:
    return MedWatchFormDataV2.model_validate(payload, context=CONTEXT)


def _locs(error: ValidationError) -> set[tuple]:
    return {tuple(item["loc"]) for item in error.errors()}


def _with(path: tuple, value: object, i: int = 1) -> dict:
    payload = full_payload(i)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    return payload


@contextmanager
def _non_english_time_locale() -> Iterator[str | None]:
    previous = locale.setlocale(locale.LC_TIME)
    chosen = None
    for name in ("es_MX.UTF-8", "es_ES.UTF-8", "de_DE.UTF-8", "fr_FR.UTF-8"):
        try:
            locale.setlocale(locale.LC_TIME, name)
        except locale.Error:
            continue
        chosen = name
        break
    try:
        yield chosen
    finally:
        locale.setlocale(locale.LC_TIME, previous)


def test_full_form_has_sections_a_b_d_f_g_and_an_internal_review_only() -> None:
    dumped = full_form().model_dump(mode="json")
    assert set(dumped) == {
        "form_version",
        "section_a",
        "section_b",
        "section_d",
        "section_f",
        "section_g",
        "mediagent_review",
        "legacy",
    }
    assert dumped["form_version"] == FORM_3500_VERSION == "fda-3500-2025-09"


@pytest.mark.parametrize(
    "section",
    ["section_c", "section_e", "header"],
)
def test_sections_c_e_and_the_fda_header_are_not_modelled(section) -> None:
    payload = full_payload()
    payload[section] = {"anything": "x"}
    with pytest.raises(ValidationError) as caught:
        _validate(payload)
    assert (section,) in _locs(caught.value)


@pytest.mark.parametrize(
    "field",
    ["place_name", "address", "country", "website", "purchase_date", "zip_code"],
)
def test_purchase_place_and_product_address_are_not_modelled(field) -> None:
    with pytest.raises(ValidationError) as caught:
        _validate(_with(("section_d", "product_1", field), "x"))
    assert ("section_d", "product_1", field) in _locs(caught.value)


# Property 9 (model part): saving then loading returns equal data.
@pytest.mark.parametrize("i", range(12))
def test_property_9_json_dump_then_validate_is_equal(i) -> None:
    form = full_form(i)
    assert _validate(form.model_dump(mode="json")) == form
    assert MedWatchFormDataV2.model_validate_json(form.model_dump_json(), context=CONTEXT) == form


def test_property_9_minimal_and_blank_forms_round_trip() -> None:
    for payload in (
        {"form_version": FORM_3500_VERSION},
        {"form_version": FORM_3500_VERSION, "section_d": {"product_2": None}},
        {"form_version": FORM_3500_VERSION, "section_a": {"sex": "", "date_of_birth": ""}},
    ):
        form = _validate(payload)
        assert _validate(form.model_dump(mode="json")) == form


def test_blank_strings_mean_not_provided_for_dates_and_options() -> None:
    form = _validate(
        _with(("section_d", "product_1"), {"name": "X", "route": "", "therapy_start": " "})
    )
    assert form.section_d.product_1.route is None
    assert form.section_d.product_1.therapy_start is None


ENUMERATED = [
    (("section_a", "sex"), "female"),
    (("section_a", "sex"), "X"),
    (("section_a", "age_unit"), "decades"),
    (("section_a", "weight_unit"), "stone"),
    (("section_a", "race"), ["asian", "martian"]),
    (("section_b", "report_types"), ["adverse_event", "rumour"]),
    (("section_b", "outcomes"), ["mild"]),
    (("section_d", "product_1", "route"), "inhaled"),
    (("section_d", "product_1", "frequency"), "twice daily"),
    (("section_d", "product_1", "dose_unit"), "mg"),
    (("section_d", "product_1", "dose_unit"), "AS NECESSARY - AN"),
    (("section_d", "product_1", "strength_unit"), "INTERNATIONAL UNITS PER MILLILITRE - IU/ML"),
    (("section_d", "product_1", "duration_unit"), "5"),
    (("section_d", "product_1", "product_types"), ["vitamin"]),
    (("section_d", "product_1", "ongoing"), "maybe"),
    (("section_d", "product_1", "abated"), "unknown"),
    (("section_d", "product_2", "reappeared"), "do_not_know"),
    (("section_g", "health_professional"), "true"),
    (("section_g", "occupation"), "Surgeon"),
    (("section_g", "also_reported_to"), ["fda"]),
    (("section_g", "country"), "NARNIA"),
    (("mediagent_review", "causality"), "Certain"),
]


@pytest.mark.parametrize(("path", "value"), ENUMERATED)
def test_out_of_list_values_fail_naming_the_path(path, value) -> None:
    with pytest.raises(ValidationError) as caught:
        _validate(_with(path, value))
    assert any(loc[: len(path)] == path for loc in _locs(caught.value)), caught.value


@pytest.mark.parametrize(
    "path",
    [
        ("section_a", "race"),
        ("section_b", "report_types"),
        ("section_b", "outcomes"),
        ("section_g", "also_reported_to"),
    ],
)
def test_duplicate_choices_fail_naming_the_path(path) -> None:
    payload = full_payload(0)
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = [target[path[-1]][0], target[path[-1]][0]]
    with pytest.raises(ValidationError) as caught:
        _validate(payload)
    assert path in _locs(caught.value)


def test_only_one_cosmetic_product_type() -> None:
    with pytest.raises(ValidationError) as caught:
        _validate(
            _with(
                ("section_d", "product_1", "product_types"),
                ["cosmetic_retail", "cosmetic_professional"],
            )
        )
    assert ("section_d", "product_1", "product_types") in _locs(caught.value)


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30",
        "2025-02-29",
        "2026-13-01",
        "2026-00",
        "1899-12-31",
        "2101-01-01",
        "10/03/2026",
        "03-Oct-2026",
        "2026-1-5",
        "yesterday",
        20261003,
    ],
)
def test_invalid_dates_fail_naming_the_path(value) -> None:
    with pytest.raises(ValidationError) as caught:
        _validate(_with(("section_b", "event_date"), value))
    assert ("section_b", "event_date") in _locs(caught.value)


DATED_PATHS = [
    ("section_a", "date_of_birth"),
    ("section_b", "event_date"),
    ("section_b", "report_date"),
    ("section_b", "death_date"),
    ("section_b", "tests", 0, "date"),
    ("section_d", "product_1", "therapy_start"),
    ("section_d", "product_1", "therapy_stop"),
    ("section_d", "product_2", "therapy_reduced"),
    ("section_f", "others", 9, "start"),
    ("section_f", "others", 0, "end"),
]


@pytest.mark.parametrize("path", DATED_PATHS)
def test_dates_after_the_save_date_fail_naming_the_path(path) -> None:
    tomorrow = (TODAY + timedelta(days=1)).isoformat()
    payload = _with(path, tomorrow, i=0)
    with pytest.raises(ValidationError) as caught:
        _validate(payload)
    assert path in _locs(caught.value)


def test_save_date_itself_and_this_month_are_allowed() -> None:
    form = _validate(_with(("section_b", "event_date"), TODAY.isoformat()))
    assert form.section_b.event_date == "2026-10-13"
    assert (
        _validate(_with(("section_b", "event_date"), "2026-10")).section_b.event_date == "2026-10"
    )
    with pytest.raises(ValidationError):
        _validate(_with(("section_b", "event_date"), "2026-11"))


def test_save_date_defaults_to_today_in_los_angeles() -> None:
    payload = full_payload(1)
    payload["section_b"]["event_date"] = "2100-01-01"
    with pytest.raises(ValidationError):
        MedWatchFormDataV2.model_validate(payload)


def test_expiration_date_may_be_in_the_future() -> None:
    form = _validate(_with(("section_d", "product_1", "expiration_date"), "2099-12-31"))
    assert form.section_d.product_1.expiration_date == "2099-12-31"


@pytest.mark.parametrize(
    ("start", "stop", "ok"),
    [
        ("2026-05-01", "2026-04-30", False),
        ("2026-05-01", "2026-04", False),
        ("2026-05", "2026-05-01", True),
        ("2026-05-15", "2026-05", True),
        ("2026-05-01", "2026-05-01", True),
    ],
)
def test_therapy_stop_not_before_start(start, stop, ok) -> None:
    payload = _with(("section_d", "product_1", "therapy_start"), start)
    payload["section_d"]["product_1"]["therapy_stop"] = stop
    if ok:
        assert _validate(payload).section_d.product_1.therapy_stop == stop
    else:
        with pytest.raises(ValidationError) as caught:
            _validate(payload)
        assert ("section_d", "product_1", "therapy_stop") in _locs(caught.value)


def test_other_product_end_not_before_start() -> None:
    payload = full_payload(0)
    payload["section_f"]["others"][3] = {"name": "X", "start": "2026-03-02", "end": "2026-03-01"}
    with pytest.raises(ValidationError) as caught:
        _validate(payload)
    assert ("section_f", "others", 3, "end") in _locs(caught.value)


@pytest.mark.parametrize("choice", ["frequency", "route"])
def test_other_text_is_required_exactly_when_other_is_chosen(choice) -> None:
    other = f"{choice}_other"
    missing = full_payload(0)
    missing["section_d"]["product_1"].update({choice: "Other", other: " "})
    with pytest.raises(ValidationError) as caught:
        _validate(missing)
    assert ("section_d", "product_1", other) in _locs(caught.value)

    stray = full_payload(0)
    stray["section_d"]["product_1"].update(
        {choice: "BID" if choice == "frequency" else "Oral", other: "text"}
    )
    with pytest.raises(ValidationError) as caught:
        _validate(stray)
    assert ("section_d", "product_1", other) in _locs(caught.value)


def test_death_date_needs_the_death_outcome() -> None:
    payload = full_payload(1)
    payload["section_b"]["death_date"] = "2026-10-01"
    with pytest.raises(ValidationError) as caught:
        _validate(payload)
    assert ("section_b", "death_date") in _locs(caught.value)


def test_at_most_8_test_rows_and_10_other_products() -> None:
    rows = full_payload(0)
    rows["section_b"]["tests"].append({"test": "ninth"})
    with pytest.raises(ValidationError) as caught:
        _validate(rows)
    assert ("section_b", "tests") in _locs(caught.value)
    others = full_payload(0)
    others["section_f"]["others"].append({"name": "eleventh"})
    with pytest.raises(ValidationError) as caught:
        _validate(others)
    assert ("section_f", "others") in _locs(caught.value)


def test_text_limits_follow_the_template() -> None:
    with pytest.raises(ValidationError) as caught:
        _validate(_with(("section_b", "narrative"), "x" * 4001))
    assert ("section_b", "narrative") in _locs(caught.value)
    assert _validate(_with(("section_b", "narrative"), "x" * 4000))


def test_review_holds_score_and_causality_apart_from_the_form_sections() -> None:
    form = full_form()
    assert form.mediagent_review.naranjo_score == 6
    for section in ("section_a", "section_b", "section_d", "section_f", "section_g"):
        assert "naranjo" not in str(getattr(form, section).model_dump()).casefold()


# Property 13: date encoding round-trips and rejects bad dates.
def test_property_13_every_day_and_month_1900_to_2100_round_trips() -> None:
    with _non_english_time_locale():
        day = date(1900, 1, 1)
        while day.year <= 2100:
            iso = day.isoformat()
            encoded = fda_date(iso)
            assert parse_fda_date(encoded) == iso
            assert encoded[3:6] == MONTH_ABBREVIATIONS[day.month - 1]
            day += timedelta(days=1)
        for year in range(1900, 2101):
            for month in range(1, 13):
                iso = f"{year:04d}-{month:02d}"
                assert fda_date(iso) == f"{MONTH_ABBREVIATIONS[month - 1]}-{year:04d}"
                assert parse_fda_date(fda_date(iso)) == iso


def test_property_13_month_names_are_english_regardless_of_locale() -> None:
    with _non_english_time_locale() as chosen:
        assert fda_date("2026-10-03") == "03-Oct-2026"
        assert fda_date("2026-01") == "Jan-2026"
        assert parse_fda_date("03-Oct-2026") == "2026-10-03"
        if chosen is not None:
            # The process locale really is non-English here, yet the form text is not.
            assert calendar.month_abbr[10] != "Oct" or chosen.startswith("en")


@pytest.mark.parametrize(
    "text",
    [
        "31-Feb-2026",
        "29-Feb-2025",
        "00-Jan-2026",
        "03-Okt-2026",
        "Foo-2026",
        "2026-10-03",
        "03-Oct-1899",
        "03-Oct-2101",
        "",
        "3 October",
    ],
)
def test_property_13_parse_rejects_bad_dates(text) -> None:
    with pytest.raises(ValueError):
        parse_fda_date(text)


@pytest.mark.parametrize("value", ["2026-02-29", "2026-13", "1899-01", "26-10-03", "10/03/2026"])
def test_property_13_encode_rejects_bad_dates(value) -> None:
    with pytest.raises(ValueError):
        fda_date(value)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-03", "2026-10-03"),
        ("2026-10", "2026-10"),
        ("03-Oct-2026", "2026-10-03"),
        ("Oct 2026", "2026-10"),
        ("October 2026", "2026-10"),
        ("October 3, 2026", "2026-10-03"),
        ("10/03/2026", "2026-10-03"),
        ("2026-10-03T07:15:00Z", "2026-10-03"),
        (date(2026, 10, 3), "2026-10-03"),
        ("a few hours after starting", None),
        ("13/45/2026", None),
        ("", None),
        (None, None),
    ],
)
def test_coerce_date_reads_only_unambiguous_shapes(value, expected) -> None:
    assert coerce_date(value) == expected


@pytest.mark.parametrize(
    ("timestamp", "expected"),
    [
        ("2026-10-02T06:30:00+00:00", "2026-10-01"),
        ("2026-10-02T08:30:00Z", "2026-10-02"),
        ("2026-10-02T08:30:00", None),
        ("not a time", None),
    ],
)
def test_clinic_date_uses_los_angeles(timestamp, expected) -> None:
    assert clinic_date_of(timestamp) == expected
