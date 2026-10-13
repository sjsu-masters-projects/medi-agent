"""Pin tests for the vendored official Form FDA 3500 template (R15.2, R15.4, R15.7).

These fail when the PDF, its ``TEMPLATE.json`` record or the field inventory changes
without the pinned values below changing in the same commit.
"""

import hashlib
import json
import socket
from importlib import resources

import pytest

from app.services.medwatch_3500 import template as template_module
from app.services.medwatch_3500.field_map import FIELD_MAP_NAMES
from app.services.medwatch_3500.template import (
    TemplateMismatchError,
    inspect_template,
    inventory_sha256,
    load_template,
    load_template_record,
    verify_template,
)

PINNED_SHA256 = "1147d7c86bb002cba7fb9352ca8e3402524d8fa0236916b7bf7e5dcdcf88bf9c"
PINNED_SIZE = 921_232
PINNED_INVENTORY_SHA256 = "69de974ab0d9d9e7be66e5a317b0fec091257b0e2a18a3731c3c9742fa61516e"


def _asset_bytes(name: str) -> bytes:
    return resources.files("app").joinpath("assets", "fda", name).read_bytes()


@pytest.fixture(scope="module")
def pdf_bytes() -> bytes:
    return _asset_bytes("form-3500-2025-09.pdf")


@pytest.fixture(scope="module")
def record() -> dict:
    return json.loads(_asset_bytes("TEMPLATE.json"))


def test_vendored_file_matches_the_pinned_checksum_and_size(pdf_bytes) -> None:
    assert hashlib.sha256(pdf_bytes).hexdigest() == PINNED_SHA256
    assert len(pdf_bytes) == PINNED_SIZE


def test_revision_record_is_form_3500_09_2025(record) -> None:
    assert record["title"] == "FORM FDA 3500"
    assert record["revision"] == "09/2025"
    assert record["omb_number"] == "0910-0291"
    assert record["expires"] == "2027-09-30"
    assert record["source_url"] == "https://www.fda.gov/media/76299/download"
    assert record["downloaded_on"] == "2026-10-13"
    assert record["sha256"] == PINNED_SHA256
    assert record["size_bytes"] == PINNED_SIZE
    assert "3500A" not in json.dumps(record)


def test_record_counts_and_inventory_hash_are_pinned(record) -> None:
    assert record["page_count"] == 8
    assert record["field_count"] == 239
    assert record["field_type_counts"] == {"button": 83, "choice": 14, "text": 142}
    assert record["button_kinds"] == {"checkbox": 77, "pushbutton": 6}
    assert record["encrypt_p"] == -1084
    assert record["field_inventory_sha256"] == PINNED_INVENTORY_SHA256
    assert inventory_sha256(record["fields"]) == PINNED_INVENTORY_SHA256
    assert len(record["choice_options"]) == 14
    assert "datasets" in record["xfa_packets"]


def test_record_equals_what_pypdf_derives_from_the_file(pdf_bytes, record) -> None:
    facts = inspect_template(pdf_bytes)
    for key, value in facts.items():
        assert record[key] == value, key


def test_load_template_verifies_once_and_needs_every_mapped_name() -> None:
    template = load_template(required_fields=FIELD_MAP_NAMES)
    assert template.sha256 == PINNED_SHA256
    assert template.revision == "09/2025"
    assert template.encrypt_p == -1084
    assert template.field_names >= FIELD_MAP_NAMES
    assert load_template() is template


def test_tampered_bytes_raise_a_mismatch(pdf_bytes, record) -> None:
    tampered = bytearray(pdf_bytes)
    tampered[-10] ^= 0xFF
    with pytest.raises(TemplateMismatchError) as caught:
        verify_template(bytes(tampered), record)
    assert caught.value.code == "FORM_3500_TEMPLATE_MISMATCH"


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("page_count", 9),
        ("field_count", 240),
        ("field_inventory_sha256", "0" * 64),
        ("encrypt_p", -4),
        ("field_type_counts", {"button": 82, "choice": 14, "text": 143}),
    ],
)
def test_a_changed_record_raises_a_mismatch(pdf_bytes, record, key, value) -> None:
    changed = {**record, key: value}
    with pytest.raises(TemplateMismatchError):
        verify_template(pdf_bytes, changed)


def test_a_changed_record_checksum_raises_a_mismatch(pdf_bytes, record) -> None:
    with pytest.raises(TemplateMismatchError):
        verify_template(pdf_bytes, {**record, "sha256": "f" * 64})


def test_a_missing_required_field_name_raises_a_mismatch(pdf_bytes, record) -> None:
    missing = "topmostSubform[0].Page1[0].SecA_Patient[0].NotAField[0]"
    with pytest.raises(TemplateMismatchError):
        verify_template(pdf_bytes, record, required_fields={missing})
    with pytest.raises(TemplateMismatchError):
        load_template(required_fields={missing})


def test_loading_makes_no_network_call(monkeypatch) -> None:
    def _refuse(*_args, **_kwargs):
        raise AssertionError("the template must never be fetched over the network")

    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)
    template_module._verified_template.cache_clear()
    load_template_record.cache_clear()
    try:
        template = load_template(required_fields=FIELD_MAP_NAMES)
    finally:
        template_module._verified_template.cache_clear()
        load_template_record.cache_clear()
    assert template.sha256 == PINNED_SHA256


def test_an_unreadable_template_file_raises_a_mismatch(monkeypatch) -> None:
    def _missing(_name: str) -> bytes:
        raise FileNotFoundError("form-3500-2025-09.pdf")

    template_module._verified_template.cache_clear()
    monkeypatch.setattr(template_module, "_asset", _missing)
    try:
        with pytest.raises(TemplateMismatchError):
            load_template()
    finally:
        template_module._verified_template.cache_clear()
