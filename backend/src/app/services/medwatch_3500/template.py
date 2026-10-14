"""The vendored, checksum-pinned official Form FDA 3500 template.

The PDF and its ``TEMPLATE.json`` record ship inside the ``app`` package
(``app/assets/fda``) and are read with ``importlib.resources``; nothing is fetched at
runtime. Any difference between the file, the record and the field names the field map
needs raises ``TemplateMismatchError`` so no export can be produced from an unknown form.
"""

from __future__ import annotations

import hashlib
import io
import json
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any, cast

from pypdf import PdfReader

from app.core.exceptions import ServiceUnavailableError

ASSET_PACKAGE = "app"
ASSET_DIRECTORY = ("assets", "fda")
TEMPLATE_PDF_NAME = "form-3500-2025-09.pdf"
TEMPLATE_RECORD_NAME = "TEMPLATE.json"

# PDF field types as the record names them.
_FIELD_TYPES = {"/Tx": "text", "/Btn": "button", "/Ch": "choice"}
_PUSHBUTTON_FLAG = 1 << 16

# Facts derived from the PDF bytes that the record must repeat exactly.
VERIFIED_RECORD_KEYS = (
    "sha256",
    "size_bytes",
    "page_count",
    "field_count",
    "field_type_counts",
    "button_kinds",
    "field_inventory_sha256",
    "fields",
    "choice_options",
    "encrypt_p",
    "xfa_packets",
)


class TemplateMismatchError(ServiceUnavailableError):
    """The vendored template, its record or the field map disagree (HTTP 503)."""

    def __init__(self, detail: str) -> None:
        super().__init__(
            "The Form 3500 template does not match its pinned record",
            code="FORM_3500_TEMPLATE_MISMATCH",
        )
        self.detail = detail


@dataclass(frozen=True)
class Form3500Template:
    """Verified template bytes and record."""

    pdf_bytes: bytes
    record: Mapping[str, Any]

    @property
    def revision(self) -> str:
        return str(self.record["revision"])

    @property
    def expires(self) -> str:
        return str(self.record["expires"])

    @property
    def sha256(self) -> str:
        return str(self.record["sha256"])

    @property
    def encrypt_p(self) -> int:
        return int(self.record["encrypt_p"])

    @property
    def field_names(self) -> frozenset[str]:
        return frozenset(cast(Mapping[str, str], self.record["fields"]))

    def choice_options(self, field_name: str) -> list[tuple[str, str]]:
        """``(export value, display text)`` pairs for one choice field, in form order."""
        options = cast(Mapping[str, list[list[str]]], self.record["choice_options"])
        return [(export, display) for export, display in options[field_name]]


def _asset(name: str) -> bytes:
    return resources.files(ASSET_PACKAGE).joinpath(*ASSET_DIRECTORY, name).read_bytes()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory_sha256(field_names: Iterable[str]) -> str:
    """SHA-256 of the sorted, newline-joined fully qualified terminal field names."""
    return _sha256("\n".join(sorted(field_names)).encode("utf-8"))


def _text(value: object) -> str:
    return str(value)


def inspect_template(pdf_bytes: bytes) -> dict[str, Any]:
    """Derive the pinned facts from template bytes with pypdf (no text extraction)."""
    reader = PdfReader(io.BytesIO(pdf_bytes))
    if reader.is_encrypted and not reader.decrypt(""):
        raise TemplateMismatchError("the template no longer opens with an empty user password")
    fields: dict[str, str] = {}
    choice_options: dict[str, list[list[str]]] = {}
    buttons: Counter[str] = Counter()
    for name, field in (reader.get_fields() or {}).items():
        field_type = field.get("/FT")
        if field_type is None:
            continue
        kind = _FIELD_TYPES.get(str(field_type), str(field_type))
        fields[name] = kind
        if kind == "button":
            flags = int(cast(Any, field.get("/Ff") or 0))
            buttons["pushbutton" if flags & _PUSHBUTTON_FLAG else "checkbox"] += 1
        if kind == "choice":
            choice_options[name] = [
                [_text(item[0]), _text(item[1])]
                if isinstance(item, list | tuple)
                else [_text(item), _text(item)]
                for item in cast(list[Any], field.get("/Opt") or [])
            ]
    root = cast(Mapping[str, Any], reader.trailer["/Root"])
    acro_form = cast(Mapping[str, Any], root["/AcroForm"])
    xfa = cast(list[Any], acro_form.get("/XFA") or [])
    encrypt = reader.trailer.get("/Encrypt")
    encrypt_p = int(cast(Mapping[str, Any], encrypt.get_object())["/P"]) if encrypt else 0
    return {
        "sha256": _sha256(pdf_bytes),
        "size_bytes": len(pdf_bytes),
        "page_count": len(reader.pages),
        "field_count": len(fields),
        "field_type_counts": dict(sorted(Counter(fields.values()).items())),
        "button_kinds": dict(sorted(buttons.items())),
        "field_inventory_sha256": inventory_sha256(fields),
        "fields": dict(sorted(fields.items())),
        "choice_options": dict(sorted(choice_options.items())),
        "encrypt_p": encrypt_p,
        "xfa_packets": [_text(xfa[index]) for index in range(0, len(xfa), 2)],
    }


def verify_template(
    pdf_bytes: bytes,
    record: Mapping[str, Any],
    required_fields: Iterable[str] = (),
) -> Form3500Template:
    """Check bytes against the record, then the record against the bytes' own facts."""
    if _sha256(pdf_bytes) != record.get("sha256"):
        raise TemplateMismatchError("the template SHA-256 differs from the pinned record")
    facts = inspect_template(pdf_bytes)
    for key in VERIFIED_RECORD_KEYS:
        if facts[key] != record.get(key):
            raise TemplateMismatchError(f"the template {key} differs from the pinned record")
    missing = sorted(set(required_fields) - set(facts["fields"]))
    if missing:
        raise TemplateMismatchError(f"{len(missing)} mapped field names are absent")
    return Form3500Template(pdf_bytes=pdf_bytes, record=record)


@cache
def load_template_record() -> Mapping[str, Any]:
    """The pinned ``TEMPLATE.json`` record, read once per process."""
    return cast(Mapping[str, Any], json.loads(_asset(TEMPLATE_RECORD_NAME)))


@cache
def _verified_template() -> Form3500Template:
    return verify_template(_asset(TEMPLATE_PDF_NAME), load_template_record())


def load_template(required_fields: Iterable[str] = ()) -> Form3500Template:
    """The verified template; also checks that every required field name exists."""
    try:
        template = _verified_template()
    except OSError as exc:
        raise TemplateMismatchError("the vendored template file could not be read") from exc
    missing = sorted(set(required_fields) - template.field_names)
    if missing:
        raise TemplateMismatchError(f"{len(missing)} mapped field names are absent")
    return template
