"""Regression coverage for the local-only PAT-005 synthetic document bundle."""

from __future__ import annotations

import pymupdf
from scripts.build_pat005_synthetic_scenario import DEFAULT_MANIFEST, build_scenario, load_manifest


def test_builds_three_labelled_upload_ready_pdfs(tmp_path):
    manifest = load_manifest(DEFAULT_MANIFEST)
    outputs = build_scenario(DEFAULT_MANIFEST, tmp_path)

    assert [path.name for path in outputs] == [
        document["file_name"] for document in manifest["documents"]
    ]
    for output in outputs:
        rendered = pymupdf.open(output)
        assert rendered.page_count >= 1
        assert "SYNTHETIC TEST DOCUMENT ONLY - NOT MEDICAL ADVICE" in rendered[0].get_text()
        rendered.close()
