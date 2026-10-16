"""The explicit Form 3500 field map and ``map_form`` (R16.2, R16.3, R21.2, R21.3)."""

import io
import xml.etree.ElementTree as ET
from collections import Counter
from typing import get_args

import pytest
from pypdf import PdfReader

from app.models.medwatch_form_3500 import (
    AgeUnit,
    AlsoReportedTo,
    DoseUnit,
    DurationUnit,
    Frequency,
    Occupation,
    Outcome,
    ProductType,
    Race,
    ReportType,
    Route,
    YesNo,
    YesNoNotApplicable,
)
from app.services.medwatch_3500.field_map import (
    CHECKBOX_OFF,
    CHECKBOX_ON,
    FIELD_MAP,
    FIELD_MAP_NAMES,
    INCONSISTENT_CHOICE_PAIRS,
    acroform_name,
    choice_export_values,
    map_form,
    model_value,
)
from app.services.medwatch_3500.template import load_template, load_template_record
from tests.unit.services.medwatch_3500_fixtures import countries, empty_form, full_form

XFA_NS = "{http://www.xfa.org/schema/xfa-data/1.0/}"
RECORD = load_template_record()
TEMPLATE_KIND = {"text": "text", "date": "text", "checkbox": "button", "choice": "choice"}
UNMAPPED_MARKERS = (
    ".Header[0].",
    "ResetForm",
    "CharCounter",
    ".Advice[0].",
    ".SecE_Device[0].",
    ".EvalYes[0]",
    ".EvalNo[0]",
    ".EvalRetd[0]",
    ".ReturnDate[0]",
    ".PicYes[0]",
    "PlaceName",
    "Address[0]",
    "Country[0]",
    "City[0]",
    "State[0]",
    "ZipCode[0]",
    "Website",
    "PurchaseDate",
)


def _template_datasets() -> ET.Element:
    reader = PdfReader(io.BytesIO(load_template().pdf_bytes))
    reader.decrypt("")
    packets = reader.trailer["/Root"]["/AcroForm"]["/XFA"]
    for index in range(0, len(packets) - 1, 2):
        if packets[index] == "datasets":
            root = ET.fromstring(packets[index + 1].get_object().get_data())
            return root.find(f"{XFA_NS}data/topmostSubform")
    raise AssertionError("no datasets packet")


def test_every_mapped_name_exists_in_the_template_with_the_right_type() -> None:
    fields = RECORD["fields"]
    for entry in FIELD_MAP:
        assert entry.acroform in fields, entry.acroform
        assert fields[entry.acroform] == TEMPLATE_KIND[entry.kind], entry.acroform


def test_one_entry_per_field_and_per_xfa_path() -> None:
    assert len(FIELD_MAP) == len(FIELD_MAP_NAMES) == 185
    assert len({entry.xfa for entry in FIELD_MAP}) == len(FIELD_MAP)


def test_every_xfa_path_resolves_to_exactly_one_datasets_element() -> None:
    data_root = _template_datasets()
    for entry in FIELD_MAP:
        assert len(data_root.findall(entry.xfa)) == 1, entry.xfa


def test_xfa_paths_pin_the_template_quirks() -> None:
    by_name = {entry.acroform: entry.xfa for entry in FIELD_MAP}
    assert by_name[acroform_name("Page4.Prod1.Prod1Name")] == "Prod1Name"
    assert by_name[acroform_name("Page4.Prod1.Prod1Dose")] == "Prod1Dose"
    assert by_name[acroform_name("Page4.Prod1.Prod1Diagnosis")] == "Prod1Diagnosis"
    assert by_name[acroform_name("Page5.Prod2.Prod2FreqOther")] == "Prod2FreqOther"
    assert by_name[acroform_name("Page4.Prod1.Prod1Strength")] == "Prod1/Prod1Strength"
    assert by_name[acroform_name("Page2.SecB_Adverse.DescEvent")] == "Page2/SecB_Adverse/DescEvent"
    assert by_name[acroform_name("Page3.TestDataTable.Row8.THighRange7")] == (
        "TestDataTable/Row8/THighRange7"
    )
    assert by_name[acroform_name("Page6.SecF_Other.Table1.Row1.Prod1")] == (
        "SecF_Other/Table1/Row1/Prod1"
    )
    assert by_name[acroform_name("Page6.SecF_Other.Table1.Row10.Cell4")] == (
        "SecF_Other/Table1/Row10/Cell4"
    )
    assert by_name[acroform_name("Page5.Prod2.pdt2CosmProf")] == "Prod2/pdt2CosmProf"


def test_weight_units_follow_the_printed_labels_not_the_swapped_tooltips() -> None:
    by_name = {entry.acroform: entry for entry in FIELD_MAP}
    assert by_name[acroform_name("Page1.SecA_Patient.WeightKG")].checked_when == "kg"
    assert by_name[acroform_name("Page1.SecA_Patient.WeightLB")].checked_when == "lb"


def test_b6_dates_and_f_end_dates_follow_the_irregular_nesting() -> None:
    by_path = {entry.model_path: entry.acroform for entry in FIELD_MAP}
    assert by_path["section_b.tests[0].date"] == acroform_name("Page3.TestDataTable.Row1.TDate1")
    assert by_path["section_b.tests[2].date"] == acroform_name("Page3.TestDataTable.Row8.TDate3")
    assert by_path["section_b.tests[7].date"] == acroform_name("Page3.TestDataTable.Row8.TDate8")
    assert by_path["section_f.others[1].end"] == acroform_name("Page6.SecF_Other.Table1.Row2.End2")
    assert by_path["section_f.others[2].end"] == acroform_name("Page6.SecF_Other.Table1.Row3.Cell4")


def test_no_section_c_e_header_advice_or_purchase_field_is_mapped() -> None:
    for name in FIELD_MAP_NAMES:
        if ".SecG_Reporter[0]." in name:
            continue  # the reporter's own address and country are Section G items
        assert not any(marker in name for marker in UNMAPPED_MARKERS), name
    unmapped = set(RECORD["fields"]) - FIELD_MAP_NAMES
    assert len(unmapped) == 239 - 185
    for name in unmapped:
        assert any(marker in name for marker in UNMAPPED_MARKERS), name


def test_mediagent_review_and_legacy_are_never_mapped() -> None:
    for entry in FIELD_MAP:
        assert not entry.model_path.startswith(("mediagent_review", "legacy")), entry


def test_every_model_path_resolves_on_a_full_form() -> None:
    form = full_form(0)
    for entry in FIELD_MAP:
        assert model_value(form, entry.model_path) is not None, entry.model_path


CHOICE_LITERALS = {
    "StrengthUnit": DoseUnit,
    "DoseUnit": DoseUnit,
    "Freq": Frequency,
    "Route": Route,
    "TherapyDurUnit": DurationUnit,
    "Occupation": Occupation,
}


def test_every_model_literal_equals_the_template_option_list() -> None:
    choice_entries = [entry for entry in FIELD_MAP if entry.kind == "choice"]
    assert len(choice_entries) == 12  # all 14 except the two purchase-place countries
    for entry in choice_entries:
        pairs = [tuple(pair) for pair in RECORD["choice_options"][entry.acroform]]
        usable = [
            display
            for export, display in pairs
            if display.strip() and (export, display) not in INCONSISTENT_CHOICE_PAIRS
        ]
        suffix = entry.acroform.rsplit(".", 1)[1].removesuffix("[0]")
        if suffix == "Country":
            assert usable == countries()
            continue
        literal = next(lit for key, lit in CHOICE_LITERALS.items() if suffix.endswith(key))
        assert list(get_args(literal)) == usable, entry.acroform


def test_the_inconsistent_unit_pair_is_the_only_excluded_named_option() -> None:
    excluded = Counter()
    for pairs in RECORD["choice_options"].values():
        for export, display in pairs:
            if (export, display) in INCONSISTENT_CHOICE_PAIRS:
                excluded[display] += 1
    assert excluded == {"AS NECESSARY - AN": 4}


CHECKBOX_GROUPS = {
    "section_a.age_unit": AgeUnit,
    "section_a.race": Race,
    "section_b.report_types": ReportType,
    "section_b.outcomes": Outcome,
    "section_d.product_1.product_types": ProductType,
    "section_d.product_2.product_types": ProductType,
    "section_d.product_1.ongoing": YesNo,
    "section_d.product_1.abated": YesNoNotApplicable,
    "section_d.product_2.reappeared": YesNoNotApplicable,
    "section_g.health_professional": YesNo,
    "section_g.also_reported_to": AlsoReportedTo,
}


@pytest.mark.parametrize(("path", "literal"), CHECKBOX_GROUPS.items())
def test_every_enumerated_checkbox_value_has_one_box(path, literal) -> None:
    values = [entry.checked_when for entry in FIELD_MAP if entry.model_path == path]
    assert sorted(values) == sorted(get_args(literal))


def test_map_form_encodes_dates_checkboxes_and_choices() -> None:
    values = map_form(full_form(1))
    a = values.acroform
    assert a[acroform_name("Page1.SecA_Patient.EventDate")] == "01-Oct-2026"
    assert a[acroform_name("Page1.SecA_Patient.SexF")] == CHECKBOX_ON
    assert a[acroform_name("Page1.SecA_Patient.SexM")] == CHECKBOX_OFF
    assert a[acroform_name("Page4.Prod1.Prod1TherapyStopDate")] == "30-Sep-2026"
    assert values.xfa["SecA_Patient/SexF"] == "1"
    assert values.xfa["SecA_Patient/SexM"] == "0"
    assert set(a) == FIELD_MAP_NAMES
    assert set(values.xfa) == {entry.xfa for entry in FIELD_MAP}


def test_month_and_year_dates_are_encoded_without_a_day() -> None:
    values = map_form(full_form(0))
    assert values.acroform[acroform_name("Page1.SecA_Patient.EventDate")] == "Sep-2026"


def test_blank_form_maps_to_blank_text_and_unchecked_boxes() -> None:
    values = map_form(empty_form())
    for entry in FIELD_MAP:
        expected = CHECKBOX_OFF if entry.kind == "checkbox" else ""
        assert values.acroform[entry.acroform] == expected, entry.acroform


def test_every_choice_option_maps_to_its_paired_export_value() -> None:
    exports = choice_export_values()
    for entry in (entry for entry in FIELD_MAP if entry.kind == "choice"):
        pairs = RECORD["choice_options"][entry.acroform]
        for export, display in pairs:
            if not display.strip() or (export, display) in INCONSISTENT_CHOICE_PAIRS:
                assert display not in exports[entry.acroform] or not display.strip()
                continue
            assert exports[entry.acroform][display] == export
    duration = exports[acroform_name("Page4.Prod1.Prod1TherapyDurUnit")]
    assert duration["Day(s)"] == "5"
    assert exports[acroform_name("Page4.Prod1.Prod1DoseUnit")]["MILLIGRAM(S) - MG"] == "25"
