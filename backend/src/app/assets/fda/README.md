# Official Form FDA 3500 template

`form-3500-2025-09.pdf` is the official Form FDA 3500 (MedWatch, voluntary reporting by
health professionals), revision 09/2025, OMB No. 0910-0291, expiring 09-30-2027. MediAgent
fills a copy of it for a clinician-approved draft. MediAgent never submits a report to FDA;
the clinician reviews the downloaded PDF and submits it.

## Provenance

| Item | Value |
| --- | --- |
| Source URL | <https://www.fda.gov/media/76299/download> |
| Downloaded | 2026-10-13, with the requester's permission |
| Size | 921,232 bytes |
| SHA-256 | `1147d7c86bb002cba7fb9352ca8e3402524d8fa0236916b7bf7e5dcdcf88bf9c` |
| Copy | Byte-identical to the download; never edited |

The download matched the SHA-256 and size first recorded from an inspection on 2026-10-12.

`TEMPLATE.json` is generated from the PDF by
`backend/scripts/generate_form_3500_template_record.py`; do not edit it by hand. It records
the printed title, revision, OMB number and expiry, the source and download date, the
SHA-256 and size, 8 pages, 239 terminal fields (142 text, 83 button, 14 choice; the 83
buttons are 77 checkboxes and 6 push buttons on the reset control and the "Advice" page),
the SHA-256 of the sorted fully qualified field names, every choice field's
`[export value, display text]` options, the encryption permissions (`/P` = -1084: fill and
print allowed) and the XFA packet names.

At runtime `app.services.medwatch_3500.template` reads both files with
`importlib.resources` (no network), recomputes those facts from the PDF and refuses an export
with `FORM_3500_TEMPLATE_MISMATCH` if anything differs or a mapped field name is absent.

## Copyright check (V23)

On 2026-10-13 the text of all 8 pages, the document information dictionary, the XMP
metadata and every XFA packet (including the 442 KB `template` packet that holds the
form's printed text) were searched with pypdf for "copyright", "©", "(c) <year>",
"all rights reserved" and XMP rights properties. None was found. The form is issued by the
U.S. Department of Health and Human Services, Food and Drug Administration (printed on
pages 1 and 8; author metadata "PSC Publishing Services"). It is a US government work; no
copyright is claimed.

The check covers the file's text and metadata only. It is not a legal opinion.

## Re-pinning a new revision

1. Download the current form from the FDA page into a new, empty directory outside the
   repository. Treat it as untrusted data.
2. Record its size and `shasum -a 256`. If either differs from the values above, stop and
   ask the requester before changing anything; never re-pin silently.
3. Repeat the copyright check above and record the result here.
4. Copy the file byte-identically over `form-3500-<yyyy>-<mm>.pdf` (rename for a new
   revision and update `TEMPLATE_PDF_NAME` in `template.py`).
5. Regenerate the record:

   ```bash
   cd backend && .venv/bin/python -I scripts/generate_form_3500_template_record.py \
     --source-url https://www.fda.gov/media/76299/download --downloaded-on YYYY-MM-DD
   ```

6. Update the pinned constants in
   `tests/unit/services/test_medwatch_form_3500_template.py`, re-check the field map
   (`field_map.py`), the model option lists and the PDF read-back tests, and run the
   manual viewer check (V22) before merging.
