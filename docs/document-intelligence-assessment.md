# Document intelligence decision record

**Status:** The bounded ingestion worker is implemented. Production synthetic-job acceptance
evidence is still required.

## Decision

Document intelligence is a provenance-first pipeline, not a model that directly edits a
patient record. It reads a source, anchors recoverable evidence, creates candidate facts, and
requires the established clinician review path before any local clinical truth changes.

The worker uses this sequence:

1. Validate the upload, persist its source metadata, and deduplicate by content hash.
2. Read embedded text when available; route scans and images through the configured OCR path.
3. Preserve page and excerpt anchors for every recoverable candidate.
4. Ask the configured extraction route for structured candidates only after the deterministic
   reading and validation steps complete.
5. Validate the returned shape and evidence excerpts. Unverifiable, low-confidence, or failed
   extraction creates no clinical fact and remains reviewable as source provenance.
6. Store candidate facts with source, model, and prompt-version metadata; clinician review owns
   approval, correction, rejection, and deletion.

This prevents the unsafe shortcut of treating a fluent extraction response as evidence or as an
authorized clinical update.

## Why this design

- OCR and embedded-text recovery answer whether a value exists in a source; model structuring
  answers a different question. Neither substitutes for clinician approval.
- Page/excerpt anchors let a reviewer challenge or correct a candidate without reconstructing
  what the worker saw.
- The model route is configuration, not a permanent product claim. The current route and its
  telemetry controls are documented in [the AI runtime decision](decisions/ai-runtime-2026-09.md).
- A failed extraction must be honest. It is safer to retain the source for review than to invent
  candidates or silently mark a document processed.

## Operational design

The HTTP service accepts and queues work; it does not perform unbounded OCR/model work in a
request. A Cloud Run Job runs `python -m app.workers.document_ingestion` with one task,
parallelism/concurrency limited to one, at least 2 GiB memory, and a 300-second task timeout.
The same runtime identity and relevant configuration as the backend are required.

The complete setup, scheduler, monitoring, failure-handling, and verification instructions are
in [the document-ingestion worker guide](document-ingestion-worker.md). Queue and worker
security guarantees are defined by migrations 034 and 036; invocation telemetry is migration
035.

## Acceptance evidence still needed

1. Deploy the Cloud Run Job and scheduler with the documented identity, secrets, and runtime
   configuration.
2. Queue one synthetic supported document and observe one successful job execution.
3. Verify the candidate facts retain the document hash and page/excerpt provenance, while no
   unapproved candidate becomes canonical clinical truth.
4. Verify a malformed, duplicate, or unverifiable source fails safely and leaves an auditable
   review state.

Historic tool comparisons, price snapshots, and preliminary benchmark narratives are retained
in Git history rather than maintained as operating documentation. They are not current product
or deployment guidance.
