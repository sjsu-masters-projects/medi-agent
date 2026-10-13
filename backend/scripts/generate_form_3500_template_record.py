"""Generate ``app/assets/fda/TEMPLATE.json`` from the vendored Form FDA 3500 PDF.

The record is derived from the file with pypdf, never typed by hand. Run it only when
re-pinning a newly downloaded official template (see ``app/assets/fda/README.md``):

    cd backend && .venv/bin/python -I scripts/generate_form_3500_template_record.py \\
        --source-url https://www.fda.gov/media/76299/download --downloaded-on YYYY-MM-DD

The PDF is treated as untrusted data: it is opened through pypdf only and nothing in it
is executed.
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

# `app` is not installed into the virtualenv, so resolve the source root here.
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND / "src"))

from pypdf import PdfReader  # noqa: E402

from app.services.medwatch_3500.template import (  # noqa: E402
    ASSET_DIRECTORY,
    TEMPLATE_PDF_NAME,
    TEMPLATE_RECORD_NAME,
    inspect_template,
)

_ASSET_DIR = _BACKEND / "src" / "app" / Path(*ASSET_DIRECTORY)
_REVISION = re.compile(r"Form FDA-3500 MedWatch \((\d{2}/\d{4})\)")
_OMB = re.compile(r"OMB No\.\s*(\d{4}-\d{4})")
_EXPIRES = re.compile(r"Expires:\s*(\d{2})-(\d{2})-(\d{4})")


def _single(pattern: re.Pattern[str], text: str, label: str) -> re.Match[str]:
    matches = {match.group(0): match for match in pattern.finditer(text)}
    if len(matches) != 1:
        raise SystemExit(f"Expected one {label} in the template text, found {len(matches)}")
    return next(iter(matches.values()))


def build_record(pdf_bytes: bytes, *, source_url: str, downloaded_on: date) -> dict[str, Any]:
    """Pinned facts plus the printed revision, OMB number and expiry."""
    facts = inspect_template(pdf_bytes)
    reader = PdfReader(io.BytesIO(pdf_bytes))
    reader.decrypt("")
    text = "\n".join(page.extract_text() or "" for page in reader.pages)
    expires = _single(_EXPIRES, text, "expiry date")
    metadata = reader.metadata or {}
    return {
        "title": str(metadata.get("/Title", "")),
        "revision": _single(_REVISION, text, "revision footer").group(1),
        "omb_number": _single(_OMB, text, "OMB number").group(1),
        "expires": f"{expires.group(3)}-{expires.group(1)}-{expires.group(2)}",
        "source_url": source_url,
        "downloaded_on": downloaded_on.isoformat(),
        "file": TEMPLATE_PDF_NAME,
        "generated_by": "backend/scripts/generate_form_3500_template_record.py",
        **facts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--downloaded-on", required=True, type=date.fromisoformat)
    args = parser.parse_args()
    # pypdf reports optional font helpers while extracting text; they do not change the record.
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    pdf_bytes = (_ASSET_DIR / TEMPLATE_PDF_NAME).read_bytes()
    record = build_record(pdf_bytes, source_url=args.source_url, downloaded_on=args.downloaded_on)
    target = _ASSET_DIR / TEMPLATE_RECORD_NAME
    target.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {target.relative_to(_BACKEND)} ({record['field_count']} fields)")


if __name__ == "__main__":
    main()
