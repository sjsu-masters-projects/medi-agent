"""Benchmark extraction candidates on the synthetic document corpus and write a report.

`REC-003` selects an OCR / document-intelligence architecture per document class from
measured results, not assumption. This script builds the synthetic corpus, runs each
locally runnable candidate over it, and measures classification accuracy, routing,
character and word error rate, field recoverability, page-citation accuracy,
confidence calibration, table-cell recovery, latency, and failure handling.

    python backend/scripts/benchmark_document_intelligence.py
    python backend/scripts/benchmark_document_intelligence.py --tessdata-dir /path/with/spa
    python backend/scripts/benchmark_document_intelligence.py --engines baseline,embedded_only

Candidates that need credentials or dependencies not in the lockfile (managed OCR,
deep-learning OCR, multimodal review) are listed as not run with the reason; the
harness accepts any ``OcrEngine`` so they can be measured with the same corpus later.
Runs offline; nothing is uploaded and no model is called.
"""

from __future__ import annotations

import argparse
import json
import platform
import resource
import sys
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.document_intelligence_corpus import (  # noqa: E402
    DEFAULT_SEED,
    BuiltCase,
    build_corpus,
)

REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports"
DEFAULT_ENGINES = ("baseline", "eng_only", "embedded_only")
CALIBRATION_BINS = 10

NOT_RUN_CANDIDATES: dict[str, str] = {
    "google_document_ai": (
        "Managed OCR/layout for the Cloud Run deployment provider. Needs a GCP project, "
        "an enabled Document AI processor, credentials, and the google-cloud-documentai "
        "package, none of which are in the lockfile or the team environment. Adapter "
        "contract: implement OcrEngine.recognize returning word boxes and confidence."
    ),
    "rapidocr_onnx_or_doctr": (
        "Maintained open-source deep-learning OCR (PaddleOCR-derived ONNX models or "
        "docTR). Not in the lockfile; adds 100-500 MB of model weights and a runtime that "
        "exceeds the 512 MiB Cloud Run allocation without a dedicated worker. Same "
        "OcrEngine contract; measure before adopting."
    ),
    "gemini_multimodal_review": (
        "Secondary review over the page image only after deterministic extraction. Not "
        "an OCR candidate: no per-word coordinates or calibrated confidence, and output "
        "must be anchored to OCR text before it can cite a page. Requires Vertex "
        "credentials; evaluate with run_ai_eval.py document_extraction scenarios."
    ),
}


# ── Text metrics ──────────────────────────────────────────────────────────────


def normalize_text(text: str) -> str:
    folded = unicodedata.normalize("NFKC", text).casefold()
    folded = folded.replace("—", "-").replace("–", "-")
    return " ".join(folded.split())


def levenshtein(source: Sequence[str], target: Sequence[str]) -> int:
    """Edit distance over characters or tokens with two rolling rows."""
    if not source:
        return len(target)
    if not target:
        return len(source)
    previous = list(range(len(target) + 1))
    for i, item in enumerate(source, start=1):
        current = [i]
        for j, other in enumerate(target, start=1):
            cost = 0 if item == other else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1]


def character_error_rate(reference: str, hypothesis: str) -> float:
    ref = normalize_text(reference)
    hyp = normalize_text(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    return min(1.0, levenshtein(ref, hyp) / len(ref))


def word_error_rate(reference: str, hypothesis: str) -> float:
    ref = normalize_text(reference).split()
    hyp = normalize_text(hypothesis).split()
    if not ref:
        return 0.0 if not hyp else 1.0
    return min(1.0, levenshtein(ref, hyp) / len(ref))


# ── Engines ───────────────────────────────────────────────────────────────────


def build_engine(name: str, tessdata_dir: str | None) -> tuple[Any, str | None]:
    """Return a configured service, or ``(None, reason)`` when it cannot run here."""
    from app.services.document_intelligence import (
        DocumentIntelligencePolicy,
        DocumentIntelligenceService,
        OcrEngineUnavailableError,
        TesseractOcrEngine,
    )

    if name == "embedded_only":
        policy = DocumentIntelligencePolicy(ocr_enabled=False)
        return DocumentIntelligenceService(policy=policy), None
    if name in ("rapidocr", "nim_paddleocr", "nim_nemotron_ocr", "nim_nemotron_parse"):
        try:
            from scripts.document_intelligence_engines import (
                NemotronParseEngine,
                NimOcrEngine,
                RapidOcrEngine,
            )

            engine: Any
            if name == "rapidocr":
                engine = RapidOcrEngine()
            elif name == "nim_paddleocr":
                engine = NimOcrEngine("paddleocr")
            elif name == "nim_nemotron_ocr":
                engine = NimOcrEngine("nemotron-ocr-v1")
            else:
                engine = NemotronParseEngine()
        except Exception as exc:  # noqa: BLE001 - optional candidates report why they cannot run
            return None, f"{type(exc).__name__}: {exc}"
        return DocumentIntelligenceService(ocr_engine=engine), None
    try:
        ocr = TesseractOcrEngine(tessdata_dir=tessdata_dir)
    except OcrEngineUnavailableError as exc:
        return None, exc.message
    if name == "baseline":
        return DocumentIntelligenceService(ocr_engine=ocr), None
    if name == "eng_only":
        policy = DocumentIntelligencePolicy(languages=["eng"])
        return DocumentIntelligenceService(ocr_engine=ocr, policy=policy), None
    return None, f"unknown engine {name!r}"


# ── Per-case evaluation ───────────────────────────────────────────────────────


def evaluate_case(service: Any, built: BuiltCase) -> dict[str, Any]:
    from app.services.document_intelligence import anchor_value, normalize_for_match

    case = built.case
    content = built.path.read_bytes()
    record: dict[str, Any] = {
        "case_id": case.case_id,
        "category": case.category,
        "language": case.language,
        "expected_document_class": case.expected_document_class,
        "acceptable_routes": list(case.acceptable_routes),
    }
    try:
        extraction = service.extract(content, mime_type=case.mime_type, file_name=case.file_name)
    except Exception as exc:  # noqa: BLE001 - an exception is a failure-handling result
        record.update({"ok": False, "exception": f"{type(exc).__name__}: {exc}"})
        return record

    pages = extraction.pages
    record.update(
        {
            "ok": True,
            "document_class": extraction.document_class.value,
            "class_correct": case.accepts_document_class(extraction.document_class.value),
            "repaired": extraction.repaired,
            "route": extraction.route.value,
            "route_reason": extraction.route_reason,
            "route_acceptable": extraction.route.value in case.acceptable_routes,
            "failure_kind": extraction.failure_kind.value,
            "page_classes": [page.page_class.value for page in pages],
            "page_class_correct": (
                [page.page_class.value for page in pages] == list(case.expected_page_classes)
                if case.expected_page_classes
                else case.accepts_document_class(extraction.document_class.value)
            ),
            "page_count": extraction.page_count,
            "latency_ms": extraction.latency_ms,
            "latency_ms_per_page": round(extraction.latency_ms / max(1, extraction.page_count)),
            "warnings": list(extraction.warnings)
            + [f"p{page.page_number}: {w}" for page in pages for w in page.warnings],
            "rotation_applied": [page.rotation_applied for page in pages],
            "page_confidence": [page.confidence for page in pages],
            "page_quality": [page.quality.value for page in pages],
            "word_count": sum(len(page.words) for page in pages),
            "text_chars": sum(len(page.text) for page in pages),
        }
    )
    record["pages"] = _page_metrics(extraction, case)
    record["fields"] = _field_metrics(extraction, case, anchor_value, service.policy)
    record["cells"] = _cell_metrics(extraction, case)
    record["calibration_samples"] = _calibration_samples(extraction, case, normalize_for_match)
    record["rejected_cleanly"] = (
        extraction.route.value == "rejected"
        and extraction.failure_kind.value == "permanent"
        and record["word_count"] == 0
    )
    return record


def _page_metrics(extraction: Any, case: Any) -> list[dict[str, Any]]:
    metrics = []
    for page in extraction.pages:
        index = page.page_number - 1
        reference = case.page_texts[index] if index < len(case.page_texts) else ""
        metrics.append(
            {
                "page": page.page_number,
                "method": page.method.value,
                "quality": page.quality.value,
                "confidence": page.confidence,
                "cer": round(character_error_rate(reference, page.text), 4),
                "wer": round(word_error_rate(reference, page.text), 4),
                "has_reference": bool(reference),
                "latency_ms": page.latency_ms,
            }
        )
    return metrics


def _field_metrics(
    extraction: Any, case: Any, anchor_value: Any, policy: Any
) -> list[dict[str, Any]]:
    results = []
    for field in case.fields:
        anchor = anchor_value(extraction, field.value, policy=policy)
        results.append(
            {
                "fact_type": field.fact_type,
                "field": field.field,
                "value": field.value,
                "expected_page": field.page,
                "found": anchor is not None,
                "page_correct": bool(anchor and anchor.page_number == field.page),
                "match_score": anchor.match_score if anchor else None,
                "word_confidence": anchor.word_confidence if anchor else None,
                "quote": anchor.quote if anchor else None,
            }
        )
    return results


def _cell_metrics(extraction: Any, case: Any) -> dict[str, Any] | None:
    if not case.cells:
        return None
    found: dict[tuple[int, int, int], str] = {}
    for page in extraction.pages:
        for table in page.tables:
            for cell in table.cells:
                found[(page.page_number, cell.row, cell.col)] = normalize_text(cell.text)
    matched = sum(
        1
        for cell in case.cells
        if found.get((cell.page, cell.row, cell.col)) == normalize_text(cell.text)
    )
    return {
        "total": len(case.cells),
        "matched": matched,
        "accuracy": round(matched / len(case.cells), 4),
        "tables_detected": sum(len(page.tables) for page in extraction.pages),
    }


def _calibration_samples(extraction: Any, case: Any, normalize: Any) -> list[tuple[float, bool]]:
    """Pair each OCR word's confidence with whether it appears in the page's ground truth."""
    samples: list[tuple[float, bool]] = []
    for page in extraction.pages:
        if page.method.value != "ocr":
            continue
        index = page.page_number - 1
        reference = case.page_texts[index] if index < len(case.page_texts) else ""
        available = Counter(normalize(reference).split())
        for word in page.words:
            for piece in normalize(word.text).split():
                correct = available[piece] > 0
                if correct:
                    available[piece] -= 1
                samples.append((word.confidence, correct))
    return samples


# ── Aggregation ───────────────────────────────────────────────────────────────


def _mean(values: Sequence[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def calibration_report(samples: Sequence[tuple[float, bool]]) -> dict[str, Any]:
    if not samples:
        return {"samples": 0, "bins": [], "ece": None}
    bins: list[dict[str, Any]] = []
    ece = 0.0
    for bucket in range(CALIBRATION_BINS):
        low, high = bucket / CALIBRATION_BINS, (bucket + 1) / CALIBRATION_BINS
        members = [
            s
            for s in samples
            if low <= s[0] < high or (bucket == CALIBRATION_BINS - 1 and s[0] == 1.0)
        ]
        if not members:
            continue
        accuracy = sum(1 for _, correct in members if correct) / len(members)
        mean_confidence = sum(confidence for confidence, _ in members) / len(members)
        ece += (len(members) / len(samples)) * abs(accuracy - mean_confidence)
        bins.append(
            {
                "range": f"{low:.1f}-{high:.1f}",
                "count": len(members),
                "mean_confidence": round(mean_confidence, 4),
                "accuracy": round(accuracy, 4),
            }
        )
    thresholds = {}
    for label, (low, high) in {
        "high_>=0.90": (0.90, 1.01),
        "medium_0.75-0.90": (0.75, 0.90),
        "low_0.50-0.75": (0.50, 0.75),
        "unusable_<0.50": (0.0, 0.50),
    }.items():
        members = [s for s in samples if low <= s[0] < high]
        thresholds[label] = {
            "count": len(members),
            "accuracy": round(sum(1 for _, c in members if c) / len(members), 4)
            if members
            else None,
        }
    return {
        "samples": len(samples),
        "bins": bins,
        "ece": round(ece, 4),
        "by_policy_band": thresholds,
    }


def aggregate(records: Sequence[dict[str, Any]]) -> dict[str, Any]:
    ok = [r for r in records if r.get("ok")]
    pages = [p for r in ok for p in r["pages"] if p["has_reference"]]
    fields = [f for r in ok for f in r["fields"]]
    cells = [r["cells"] for r in ok if r.get("cells")]
    adversarial = [r for r in records if r["acceptable_routes"] == ["rejected"]]
    found = [f for f in fields if f["found"]]
    return {
        "cases": len(records),
        "exceptions": len(records) - len(ok),
        "class_accuracy": _mean([1.0 if r["class_correct"] else 0.0 for r in ok]),
        "page_class_accuracy": _mean([1.0 if r["page_class_correct"] else 0.0 for r in ok]),
        "route_acceptable_rate": _mean([1.0 if r["route_acceptable"] else 0.0 for r in ok]),
        "mean_cer": _mean([p["cer"] for p in pages]),
        "mean_wer": _mean([p["wer"] for p in pages]),
        "field_found_rate": _mean([1.0 if f["found"] else 0.0 for f in fields]),
        "field_found_on_correct_page_rate": _mean(
            [1.0 if f["page_correct"] else 0.0 for f in fields]
        ),
        "page_citation_accuracy_of_found": _mean(
            [1.0 if f["page_correct"] else 0.0 for f in found]
        ),
        "table_cell_accuracy": _mean([c["accuracy"] for c in cells]),
        "mean_latency_ms_per_page": _mean([r["latency_ms_per_page"] for r in ok]),
        "rejected_cleanly_rate": _mean(
            [1.0 if r.get("rejected_cleanly") else 0.0 for r in adversarial if r.get("ok")]
        ),
        "calibration": calibration_report([s for r in ok for s in r["calibration_samples"]]),
    }


def aggregate_by_category(records: Sequence[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    categories = sorted({r["category"] for r in records})
    return {c: aggregate([r for r in records if r["category"] == c]) for c in categories}


# ── Report ────────────────────────────────────────────────────────────────────


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Document intelligence benchmark",
        "",
        f"Generated {report['generated_at']} on {report['platform']}; corpus seed "
        f"{report['corpus']['seed']} with {report['corpus']['case_count']} synthetic cases.",
        "",
        "All content is synthetic and fictional. Engines are the locally runnable "
        + "candidates; managed and deep-learning candidates are listed under *Not run*.",
        "",
        "## Engines",
        "",
        "| Engine | Description | Versions |",
        "| --- | --- | --- |",
    ]
    for name, meta in report["engines"].items():
        memory = (
            f"; peak RSS {meta['peak_rss_mb_after']} MiB" if "peak_rss_mb_after" in meta else ""
        )
        lines.append(
            f"| {name} | {meta['description']} | {meta.get('versions') or meta.get('skipped')}{memory} |"
        )
    lines += [
        "",
        "## Overall",
        "",
        "| Metric | " + " | ".join(report["results"]) + " |",
        "| --- |" + " --- |" * len(report["results"]),
    ]
    metrics = [
        "class_accuracy",
        "page_class_accuracy",
        "route_acceptable_rate",
        "mean_cer",
        "mean_wer",
        "field_found_rate",
        "field_found_on_correct_page_rate",
        "page_citation_accuracy_of_found",
        "table_cell_accuracy",
        "mean_latency_ms_per_page",
        "rejected_cleanly_rate",
        "exceptions",
    ]
    for metric in metrics:
        row = [
            _fmt(report["results"][engine]["overall"].get(metric)) for engine in report["results"]
        ]
        lines.append(f"| {metric} | " + " | ".join(row) + " |")
    for engine, data in report["results"].items():
        lines += [
            "",
            f"## {engine} by category",
            "",
            "| Category | cases | class acc | route ok | CER | WER | fields found | on correct page | latency/page ms |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for category, agg in data["by_category"].items():
            lines.append(
                f"| {category} | {agg['cases']} | {_fmt(agg['class_accuracy'])} | {_fmt(agg['route_acceptable_rate'])} | "
                f"{_fmt(agg['mean_cer'])} | {_fmt(agg['mean_wer'])} | {_fmt(agg['field_found_rate'])} | "
                f"{_fmt(agg['field_found_on_correct_page_rate'])} | {_fmt(agg['mean_latency_ms_per_page'])} |"
            )
        calibration = data["overall"]["calibration"]
        if calibration["samples"]:
            lines += [
                "",
                f"### {engine} OCR word confidence calibration (ECE {_fmt(calibration['ece'])}, {calibration['samples']} words)",
                "",
                "| Confidence bin | words | mean confidence | accuracy |",
                "| --- | --- | --- | --- |",
            ]
            for b in calibration["bins"]:
                lines.append(
                    f"| {b['range']} | {b['count']} | {_fmt(b['mean_confidence'])} | {_fmt(b['accuracy'])} |"
                )
            lines += ["", "| Policy band | words | accuracy |", "| --- | --- | --- |"]
            for band, stats in calibration["by_policy_band"].items():
                lines.append(f"| {band} | {stats['count']} | {_fmt(stats['accuracy'])} |")
        lines += [
            "",
            f"### {engine} per case",
            "",
            "| Case | class | route | CER | fields found/total | on page | rot | conf | ms |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in data["cases"]:
            if not r.get("ok"):
                lines.append(f"| {r['case_id']} | EXCEPTION | {r.get('exception')} | | | | | | |")
                continue
            cers = [p["cer"] for p in r["pages"] if p["has_reference"]]
            found = sum(1 for f in r["fields"] if f["found"])
            on_page = sum(1 for f in r["fields"] if f["page_correct"])
            mark = "" if r["class_correct"] else " (expected " + r["expected_document_class"] + ")"
            route_mark = "" if r["route_acceptable"] else " (!)"
            lines.append(
                f"| {r['case_id']} | {r['document_class']}{mark} | {r['route']}{route_mark} | {_fmt(_mean(cers))} | "
                f"{found}/{len(r['fields'])} | {on_page} | {r['rotation_applied']} | "
                f"{[round(c, 2) for c in r['page_confidence']]} | {r['latency_ms']} |"
            )
    lines += ["", "## Not run", "", "| Candidate | Reason |", "| --- | --- |"]
    for name, reason in report["not_run"].items():
        lines.append(f"| {name} | {reason} |")
    return "\n".join(lines) + "\n"


def _peak_rss_mb() -> float:
    """Peak resident memory of this process so far, in MiB (platform units differ)."""
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return round(peak / divisor, 1)


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--engines", default=",".join(DEFAULT_ENGINES), help="Comma-separated engine names"
    )
    parser.add_argument(
        "--tessdata-dir", default=None, help="Directory holding eng/spa/osd traineddata"
    )
    parser.add_argument(
        "--corpus-dir", type=Path, default=None, help="Keep the generated corpus here"
    )
    parser.add_argument("--report-dir", type=Path, default=REPORTS_DIR)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--stem", default=None, help="Report file stem (default: timestamped)")
    return parser.parse_args(argv)


def _load_local_env() -> None:
    """Load NVIDIA_API_KEY from the repository .env without printing anything."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - python-dotenv ships with pydantic-settings
        return
    load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    _load_local_env()
    corpus_dir = args.corpus_dir or Path(tempfile.mkdtemp(prefix="mediagent-doc-corpus-"))
    built = build_corpus(corpus_dir, seed=args.seed)
    engines: dict[str, dict[str, Any]] = {}
    results: dict[str, dict[str, Any]] = {}
    descriptions = {
        "baseline": "PyMuPDF embedded text + Tesseract OCR (eng+spa) with rotation and upscaling",
        "eng_only": "Same pipeline with only the English Tesseract model, to price the Spanish pack",
        "embedded_only": "PyMuPDF embedded text only, OCR disabled (today's production behaviour)",
        "rapidocr": "Same pipeline with PaddleOCR PP-OCRv5 (Latin) on CPU via RapidOCR/ONNX",
        "nim_paddleocr": "Same pipeline with the hosted NVIDIA NIM PaddleOCR trial endpoint",
        "nim_nemotron_ocr": "Same pipeline with the hosted NVIDIA Nemotron OCR v1 trial endpoint",
        "nim_nemotron_parse": "Same pipeline with hosted Nemotron-Parse (layout elements, no confidence)",
    }
    for name in [e.strip() for e in args.engines.split(",") if e.strip()]:
        service, reason = build_engine(name, args.tessdata_dir)
        if service is None:
            engines[name] = {"description": descriptions.get(name, name), "skipped": reason}
            print(f"[skip] {name}: {reason}")
            continue
        engines[name] = {
            "description": descriptions.get(name, name),
            "versions": service.extractor_version,
        }
        records = []
        engines[name]["peak_rss_mb_before"] = _peak_rss_mb()
        for item in built:
            record = evaluate_case(service, item)
            records.append(record)
            status = record.get("route", record.get("exception"))
            print(
                f"[{name}] {item.case.case_id:45s} {record.get('document_class', '-'):18s} {status}"
            )
        engines[name]["peak_rss_mb_after"] = _peak_rss_mb()
        results[name] = {
            "overall": aggregate(records),
            "by_category": aggregate_by_category(records),
            "cases": [{k: v for k, v in r.items() if k != "calibration_samples"} for r in records],
        }
    report = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "platform": f"{platform.system()} {platform.machine()} Python {platform.python_version()}",
        "corpus": {
            "seed": args.seed,
            "case_count": len(built),
            "dir": str(corpus_dir),
            "cases": [b.to_dict() for b in built],
        },
        "engines": engines,
        "results": results,
        "not_run": NOT_RUN_CANDIDATES,
    }
    args.report_dir.mkdir(parents=True, exist_ok=True)
    stem = (
        args.stem
        or f"document_intelligence_benchmark_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
    )
    (args.report_dir / f"{stem}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
    (args.report_dir / f"{stem}.md").write_text(render_markdown(report))
    print(f"\nReport: {args.report_dir / stem}.md")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
