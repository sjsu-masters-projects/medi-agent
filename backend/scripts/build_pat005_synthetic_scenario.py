"""Build the synthetic PDF source bundle for the PAT-005 controlled-care demo.

The script is intentionally local-only: it reads the committed synthetic manifest and
writes upload-ready PDFs to a caller-selected directory. It never connects to
Supabase, creates an account, or uploads a document.

    PYTHONPATH=backend/src backend/.venv/bin/python \\
      backend/scripts/build_pat005_synthetic_scenario.py --out-dir tmp/pat-005-scenario
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pymupdf

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = (
    REPOSITORY_ROOT / "backend/tests/fixtures/pat005/synthetic_today_feed_scenario.json"
)
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "tmp/pat-005-synthetic-scenario"
PAGE_RECT = pymupdf.paper_rect("letter")
MARGIN = 54


def load_manifest(path: Path) -> dict[str, Any]:
    """Load the version-controlled, synthetic-only scenario definition."""
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("synthetic_only") is not True or manifest.get("not_medical_advice") is not True:
        raise ValueError("PAT-005 scenario manifest must be explicitly synthetic and non-clinical")
    documents = manifest.get("documents")
    if not isinstance(documents, list) or len(documents) != 3:
        raise ValueError("PAT-005 scenario manifest must define exactly three source documents")
    return manifest


def _page_text(title: str, lines: list[str], page_number: int, page_count: int) -> str:
    return "\n\n".join(
        [
            "SYNTHETIC TEST DOCUMENT ONLY - NOT MEDICAL ADVICE",
            title.upper(),
            *lines,
            f"PAT-005 synthetic demonstration | Page {page_number} of {page_count}",
        ]
    )


def build_scenario(manifest_path: Path, output_directory: Path) -> list[Path]:
    """Create one well-labelled PDF for each source document in the manifest."""
    manifest = load_manifest(manifest_path)
    output_directory.mkdir(parents=True, exist_ok=True)
    outputs: list[Path] = []

    for document_spec in manifest["documents"]:
        file_name = document_spec["file_name"]
        pages = document_spec["pages"]
        if not isinstance(file_name, str) or not file_name.endswith(".pdf"):
            raise ValueError("PAT-005 source documents must be named PDFs")
        if not isinstance(pages, list) or not pages:
            raise ValueError(f"{file_name} must include at least one page")

        pdf = pymupdf.open()
        for index, page_spec in enumerate(pages, start=1):
            page = pdf.new_page(width=PAGE_RECT.width, height=PAGE_RECT.height)
            lines = page_spec.get("lines")
            title = page_spec.get("title")
            if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
                raise ValueError(f"{file_name} page {index} must contain text lines")
            if not isinstance(title, str) or not title:
                raise ValueError(f"{file_name} page {index} must contain a title")
            text = _page_text(title, lines, index, len(pages))
            remaining = page.insert_textbox(
                pymupdf.Rect(MARGIN, MARGIN, PAGE_RECT.width - MARGIN, PAGE_RECT.height - MARGIN),
                text,
                fontname="helv",
                fontsize=12,
                lineheight=1.5,
                color=(0.05, 0.1, 0.2),
            )
            if remaining < 0:
                raise ValueError(f"{file_name} page {index} text does not fit the page")

        output_path = output_directory / file_name
        pdf.save(output_path)
        pdf.close()
        outputs.append(output_path)

    return outputs


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    args = parser.parse_args()

    outputs = build_scenario(args.manifest.resolve(), args.out_dir.resolve())
    for output in outputs:
        print(f"{output.name}\t{sha256(output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
