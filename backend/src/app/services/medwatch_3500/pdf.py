"""Fill the vendored official Form FDA 3500 for an approved draft.

The template is an Adobe LiveCycle hybrid form: values go to both the AcroForm fields and
the XFA ``datasets`` packet, because viewers disagree when only one is written. The output
stays fillable (not flattened), keeps every official field, page and the XMP packet
unchanged apart from the values, and is re-encrypted like the template (AES-256, empty user
password, the template's permissions). Only the document information dictionary gains a
note that MediAgent did not submit the report. The random owner password is never logged or
stored.
"""

from __future__ import annotations

import io
import secrets
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Any, cast
from uuid import UUID

from pypdf import PdfReader, PdfWriter
from pypdf.constants import UserAccessPermissions
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    FloatObject,
    NameObject,
    NumberObject,
    StreamObject,
)

from app.core.exceptions import ExternalServiceError
from app.models.medwatch_form_3500 import MedWatchFormDataV2
from app.services.medwatch_3500.field_map import FIELD_MAP_NAMES, map_form
from app.services.medwatch_3500.template import (
    Form3500Template,
    TemplateMismatchError,
    load_template,
)

XFA_DATA_NAMESPACE = "http://www.xfa.org/schema/xfa-data/1.0/"
SUBJECT_NOTE = "Draft prepared in MediAgent; not submitted to FDA by MediAgent"
KEYWORDS = "fda-3500; not-submitted"
WATERMARK_TEXT = "DRAFT \u2013 not for submission"
WATERMARK_FONT = "MAWatermarkFont"
WATERMARK_STATE = "MAWatermarkState"

# Keep the ``xfa:`` prefix the template uses when the datasets packet is serialised.
ET.register_namespace("xfa", XFA_DATA_NAMESPACE)


class Form3500RenderError(ExternalServiceError):
    """Filling the template failed (HTTP 502). Carries no form values."""

    def __init__(self, draft_id: UUID) -> None:
        super().__init__("Form 3500 renderer")
        self.code = "FORM_3500_RENDER_FAILED"
        self.message = f"Form 3500 PDF could not be produced for draft {draft_id}"


def _xfa_packets(writer: PdfWriter) -> ArrayObject:
    acro_form = cast(DictionaryObject, writer._root_object["/AcroForm"])
    return cast(ArrayObject, acro_form["/XFA"].get_object())


def _datasets_stream(writer: PdfWriter) -> StreamObject:
    packets = _xfa_packets(writer)
    for index in range(0, len(packets) - 1, 2):
        if str(packets[index]) == "datasets":
            return cast(StreamObject, packets[index + 1].get_object())
    raise TemplateMismatchError("the template has no XFA datasets packet")


def _write_datasets(writer: PdfWriter, values: Mapping[str, str]) -> None:
    stream = _datasets_stream(writer)
    # Trusted input: the packet comes from the checksum-pinned template.
    root = ET.fromstring(stream.get_data())
    data_root = root.find(f"{{{XFA_DATA_NAMESPACE}}}data/topmostSubform")
    if data_root is None:
        raise TemplateMismatchError("the XFA datasets packet has no topmostSubform")
    for path, value in values.items():
        elements = data_root.findall(path)
        if len(elements) != 1:
            raise TemplateMismatchError("an XFA datasets path does not resolve to one element")
        elements[0].text = value or None
    stream.set_data(ET.tostring(root, encoding="utf-8", xml_declaration=False))


def _add_not_submitted_note(writer: PdfWriter) -> None:
    metadata: Mapping[str, Any] = writer.metadata or {}
    subject = str(metadata.get("/Subject") or "").strip()
    writer.add_metadata(
        {
            "/Subject": f"{subject}. {SUBJECT_NOTE}" if subject else SUBJECT_NOTE,
            "/Keywords": KEYWORDS,
        }
    )


def _watermark_stream(width: float, height: float) -> bytes:
    """A large grey diagonal label centred on the page, drawn above the form."""
    # 45 degrees; Helvetica averages about half an em per glyph.
    size = min(width, height) * 0.075
    text_width = size * 0.52 * len(WATERMARK_TEXT)
    offset = text_width / 2 * 0.7071
    encoded = WATERMARK_TEXT.encode("cp1252").replace(b"\\", b"\\\\")
    encoded = encoded.replace(b"(", b"\\(").replace(b")", b"\\)")
    return (
        b"Q q /%s gs 0.45 g BT /%s %.2f Tf 0.7071 0.7071 -0.7071 0.7071 %.2f %.2f Tm (%s) Tj ET Q"
        % (
            WATERMARK_STATE.encode(),
            WATERMARK_FONT.encode(),
            size,
            width / 2 - offset,
            height / 2 - offset,
            encoded,
        )
    )


def _add_watermark(writer: PdfWriter) -> None:
    """Stamp the draft label on every page and drop XFA so no viewer redraws it away."""
    acro_form = cast(DictionaryObject, writer._root_object["/AcroForm"])
    if "/XFA" in acro_form:
        del acro_form["/XFA"]
    font = writer._add_object(
        DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica-Bold"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            }
        )
    )
    state = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/ExtGState"),
            NameObject("/ca"): FloatObject("0.35"),
            NameObject("/CA"): FloatObject("0.35"),
        }
    )
    for page in writer.pages:
        resources = cast(DictionaryObject, page.get("/Resources") or DictionaryObject())
        resources = cast(DictionaryObject, resources.get_object())
        fonts = cast(DictionaryObject, resources.get("/Font") or DictionaryObject()).get_object()
        states = cast(
            DictionaryObject, resources.get("/ExtGState") or DictionaryObject()
        ).get_object()
        cast(DictionaryObject, fonts)[NameObject(f"/{WATERMARK_FONT}")] = font
        cast(DictionaryObject, states)[NameObject(f"/{WATERMARK_STATE}")] = state
        resources[NameObject("/Font")] = fonts
        resources[NameObject("/ExtGState")] = states
        page[NameObject("/Resources")] = resources

        before = DecodedStreamObject()
        before.set_data(b"q")
        mark = DecodedStreamObject()
        mark.set_data(_watermark_stream(float(page.mediabox.width), float(page.mediabox.height)))
        existing = page.get("/Contents")
        parts: list[Any] = []
        if existing is not None:
            resolved = existing.get_object()
            parts = list(resolved) if isinstance(resolved, ArrayObject) else [existing]
        page[NameObject("/Contents")] = ArrayObject(
            [writer._add_object(before), *parts, writer._add_object(mark)]
        )


def _signed_32(value: int) -> int:
    return value - (1 << 32) if value >= 1 << 31 else value


def _encrypt_like_template(writer: PdfWriter, template: Form3500Template) -> None:
    writer.encrypt(
        user_password="",
        owner_password=secrets.token_urlsafe(32),
        permissions_flag=UserAccessPermissions(template.encrypt_p & 0xFFFFFFFF),
        algorithm="AES-256",
    )
    # pypdf writes /P unsigned; the template (and the PDF specification) use the signed form.
    entry = cast(Any, writer)._encrypt_entry
    if entry is None:
        raise TemplateMismatchError("the output could not be encrypted")
    entry[NameObject("/P")] = NumberObject(_signed_32(int(entry["/P"])))


def fill_template(
    template: Form3500Template, form: MedWatchFormDataV2, *, watermark: bool = False
) -> bytes:
    """Fill a verified template with one form's values and return the PDF bytes.

    ``watermark`` stamps "DRAFT - not for submission" on every page; only the pre-approval
    preview uses it.
    """
    values = map_form(form, template.record)
    reader = PdfReader(io.BytesIO(template.pdf_bytes))
    if reader.is_encrypted and not reader.decrypt(""):
        raise TemplateMismatchError("the template no longer opens with an empty user password")
    writer = PdfWriter(clone_from=reader)
    # Keep the template's version (1.7): pypdf writes "%PDF-1.3" by default, which is too
    # old for the AES-256 encryption below.
    writer.pdf_header = reader.pdf_header
    for page in writer.pages:
        if "/Annots" in page:
            writer.update_page_form_field_values(page, values.acroform, auto_regenerate=False)
    writer.set_need_appearances_writer(True)
    _write_datasets(writer, values.xfa)
    if watermark:
        _add_watermark(writer)
    _add_not_submitted_note(writer)
    _encrypt_like_template(writer, template)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def render_form_3500(form: MedWatchFormDataV2, draft_id: UUID, *, watermark: bool = False) -> bytes:
    """The official Form 3500 PDF for an approved draft, or a watermarked preview.

    ``TemplateMismatchError`` (503) when the vendored template is not the pinned one;
    ``Form3500RenderError`` (502) for any other failure while filling.
    """
    template = load_template(required_fields=FIELD_MAP_NAMES)
    try:
        return fill_template(template, form, watermark=watermark)
    except TemplateMismatchError:
        raise
    except Exception as exc:
        raise Form3500RenderError(draft_id) from exc
