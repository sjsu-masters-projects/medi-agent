"""Score a recorded synthetic document-extraction JSON payload offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.models.document_extraction import DocumentExtractionResult
from app.services.document_extraction_evaluator import evaluate_recorded_extraction


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True, help="Synthetic source text file")
    parser.add_argument("--expected", type=Path, required=True, help="Gold extraction JSON")
    parser.add_argument("--output", type=Path, required=True, help="Recorded model output JSON")
    parser.add_argument("--latency-ms", type=int)
    parser.add_argument("--estimated-cost-usd", type=float)
    args = parser.parse_args()
    expected = DocumentExtractionResult.model_validate_json(args.expected.read_text())
    output = json.loads(args.output.read_text())
    report = evaluate_recorded_extraction(
        source_pages=[args.source.read_text()],
        expected=expected,
        output=output,
        latency_ms=args.latency_ms,
        estimated_cost_usd=args.estimated_cost_usd,
    )
    print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
