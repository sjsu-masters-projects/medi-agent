"""Filling the official Form 3500 PDF (R15.4, R21.1 to R21.5, R21.7, R21.8)."""

import io
import logging
import secrets
import xml.etree.ElementTree as ET
from uuid import UUID

import pytest
from pypdf import PdfReader, PdfWriter

from app.services.medwatch_3500 import pdf as pdf_module
from app.services.medwatch_3500.field_map import FIELD_MAP, map_form
from app.services.medwatch_3500.pdf import (
    KEYWORDS,
    SUBJECT_NOTE,
    Form3500RenderError,
    render_form_3500,
)
from app.services.medwatch_3500.template import TemplateMismatchError, load_template
from tests.unit.services.medwatch_3500_fixtures import empty_form, full_form

DRAFT_ID = UUID("0f1e2d3c-4b5a-4968-8776-655443322110")
XFA_NS = "{http://www.xfa.org/schema/xfa-data/1.0/}"
CORPUS_SIZE = 35  # enough for both products together to use every route and unit


def _open(data: bytes) -> PdfReader:
    reader = PdfReader(io.BytesIO(data))
    assert reader.is_encrypted
    assert reader.decrypt("") != 0, "the empty user password must open the PDF"
    return reader


def _packets(reader: PdfReader) -> dict[str, bytes]:
    array = reader.trailer["/Root"]["/AcroForm"]["/XFA"]
    return {
        str(array[index]): array[index + 1].get_object().get_data()
        for index in range(0, len(array) - 1, 2)
    }


def _datasets_leaves(reader: PdfReader) -> list[tuple[str, str]]:
    root = ET.fromstring(_packets(reader)["datasets"])
    top = root.find(f"{XFA_NS}data/topmostSubform")
    leaves: list[tuple[str, str]] = []

    def walk(element: ET.Element, path: str) -> None:
        children = list(element)
        if not children:
            leaves.append((path, element.text or ""))
        for child in children:
            walk(child, f"{path}/{child.tag}" if path else child.tag)

    walk(top, "")
    return leaves


def _terminal_values(reader: PdfReader) -> dict[str, object]:
    return {
        name: field.get("/V")
        for name, field in reader.get_fields().items()
        if field.get("/FT") is not None
    }


@pytest.fixture(scope="module")
def template_reader() -> PdfReader:
    return _open(load_template().pdf_bytes)


@pytest.fixture(scope="module")
def rendered() -> bytes:
    return render_form_3500(full_form(0), DRAFT_ID)


def test_output_keeps_all_239_fields_8_pages_and_the_xfa(rendered, template_reader) -> None:
    reader = _open(rendered)
    assert len(reader.pages) == 8
    assert len(_terminal_values(reader)) == 239
    assert set(_packets(reader)) == set(_packets(template_reader))
    for name in ("template", "config", "localeSet", "xmpmeta", "form"):
        assert _packets(reader)[name] == _packets(template_reader)[name], name


def test_output_is_aes_256_with_the_template_permissions(rendered, template_reader) -> None:
    encrypt = _open(rendered).trailer["/Encrypt"].get_object()
    original = template_reader.trailer["/Encrypt"].get_object()
    assert encrypt["/P"] == original["/P"] == -1084
    assert (encrypt["/V"], encrypt["/R"]) == (5, 6)
    assert encrypt["/CF"]["/StdCF"]["/CFM"] == "/AESV3"


def test_output_keeps_the_template_pdf_version(rendered, template_reader) -> None:
    # AES-256 (V5/R6) needs PDF 1.7 or later; pypdf would otherwise write 1.3.
    assert rendered.startswith(b"%PDF-1.7")
    assert _open(rendered).pdf_header == template_reader.pdf_header == "%PDF-1.7"


def test_only_the_information_dictionary_notes_it_was_not_submitted(
    rendered, template_reader
) -> None:
    reader = _open(rendered)
    metadata, original = reader.metadata, template_reader.metadata
    assert metadata["/Title"] == original["/Title"] == "FORM FDA 3500"
    assert metadata["/Subject"] == f"{original['/Subject']}. {SUBJECT_NOTE}"
    assert metadata["/Keywords"] == KEYWORDS == "fda-3500; not-submitted"
    xmp = reader.trailer["/Root"]["/Metadata"].get_object().get_data()
    assert xmp == template_reader.trailer["/Root"]["/Metadata"].get_object().get_data()


def test_no_official_page_content_changes(rendered, template_reader) -> None:
    reader = _open(rendered)
    for page, original in zip(reader.pages, template_reader.pages, strict=True):
        assert page.get_contents().get_data() == original.get_contents().get_data()


def test_output_stays_fillable_and_fda_use_fields_stay_blank(rendered) -> None:
    reader = _open(rendered)
    values = _terminal_values(reader)
    for name in ("Page1[0].Header[0].TriageNum[0]", "Page1[0].Header[0].RecDate[0]"):
        assert values[f"topmostSubform[0].{name}"] in (None, "")
    assert bool(reader.trailer["/Root"]["/AcroForm"]["/NeedAppearances"])
    annotations = sum(len(page["/Annots"]) for page in reader.pages if "/Annots" in page)
    assert annotations >= 239
    writer = PdfWriter(clone_from=reader)
    name = "topmostSubform[0].Page3[0].TestDataTable[0].EvalYes[0]"
    for page in writer.pages:
        if "/Annots" in page:
            writer.update_page_form_field_values(page, {name: "/1"}, auto_regenerate=False)
    refilled = io.BytesIO()
    writer.write(refilled)
    assert PdfReader(io.BytesIO(refilled.getvalue())).get_fields()[name]["/V"] == "/1"


def test_owner_password_is_random_and_never_logged(monkeypatch, caplog) -> None:
    sentinel = "owner-password-sentinel-value"
    real = secrets.token_urlsafe
    calls: list[int] = []

    def _token(nbytes: int | None = None) -> str:
        calls.append(nbytes or 0)
        return sentinel

    monkeypatch.setattr(pdf_module.secrets, "token_urlsafe", _token)
    with caplog.at_level(logging.DEBUG):
        data = render_form_3500(empty_form(), DRAFT_ID)
    assert calls == [32]
    assert sentinel not in caplog.text
    assert sentinel.encode() not in data
    monkeypatch.setattr(pdf_module.secrets, "token_urlsafe", real)
    first = _open(render_form_3500(empty_form(), DRAFT_ID)).trailer["/Encrypt"].get_object()
    second = _open(render_form_3500(empty_form(), DRAFT_ID)).trailer["/Encrypt"].get_object()
    assert first["/O"] != second["/O"]


def test_fill_failure_raises_the_render_error_without_form_values(monkeypatch) -> None:
    def _broken(*_args, **_kwargs):
        raise RuntimeError("synthetic failure Maya Patel")

    monkeypatch.setattr(pdf_module, "map_form", _broken)
    with pytest.raises(Form3500RenderError) as caught:
        render_form_3500(full_form(0), DRAFT_ID)
    assert caught.value.code == "FORM_3500_RENDER_FAILED"
    assert "Maya" not in caught.value.message


def test_template_mismatch_is_not_reported_as_a_render_failure(monkeypatch) -> None:
    def _mismatch(**_kwargs):
        raise TemplateMismatchError("synthetic")

    monkeypatch.setattr(pdf_module, "load_template", _mismatch)
    with pytest.raises(TemplateMismatchError):
        render_form_3500(full_form(0), DRAFT_ID)


def test_blank_draft_writes_blank_values(template_reader) -> None:
    reader = _open(render_form_3500(empty_form(), DRAFT_ID))
    values = _terminal_values(reader)
    for entry in FIELD_MAP:
        if entry.kind == "checkbox":
            assert values[entry.acroform] in ("/Off", None), entry.acroform
        else:
            assert values[entry.acroform] in ("", None), entry.acroform
    assert _datasets_leaves(reader) == _datasets_leaves(template_reader)


# Property 10: PDF read-back equals the mapping.
@pytest.mark.slow
@pytest.mark.parametrize("i", range(CORPUS_SIZE))
def test_property_10_read_back_equals_the_mapping(i, template_reader) -> None:
    form = full_form(i)
    mapped = map_form(form)
    reader = _open(render_form_3500(form, DRAFT_ID))

    values = _terminal_values(reader)
    original = _terminal_values(template_reader)
    assert len(values) == 239
    assert reader.trailer["/Encrypt"].get_object()["/P"] == -1084
    for name, value in values.items():
        expected = mapped.acroform.get(name)
        if expected is None:
            assert value == original[name], name
        elif expected == "":
            assert value in ("", None), name
        else:
            assert value == expected, name

    xfa = dict(mapped.xfa)
    expected_leaves = [
        (path, xfa.get(path, text)) for path, text in _datasets_leaves(template_reader)
    ]
    assert _datasets_leaves(reader) == expected_leaves


def test_property_10_corpus_sets_every_mapped_field_and_option() -> None:
    corpus = [map_form(full_form(i)) for i in range(CORPUS_SIZE)]
    for entry in FIELD_MAP:
        seen = {values.acroform[entry.acroform] for values in corpus}
        if entry.kind == "checkbox":
            assert seen == {"/1", "/Off"}, entry.acroform
        else:
            assert seen - {""}, entry.acroform
    record = load_template().record
    for stem in ("Freq", "Route", "StrengthUnit", "DoseUnit", "TherapyDurUnit", "Occupation"):
        names = [
            e.acroform
            for e in FIELD_MAP
            if e.kind == "choice" and e.acroform.endswith(f"{stem}[0]")
        ]
        seen = {values.acroform[name] for values in corpus for name in names}
        options = {
            export
            for export, display in record["choice_options"][names[0]]
            if display.strip() and display != "AS NECESSARY - AN"
        }
        assert seen == options, stem
