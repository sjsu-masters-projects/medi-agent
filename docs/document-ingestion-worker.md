# Document-ingestion worker

Document upload is request-only. The API records a `pending` document, and the
Cloud Run Job runs `python -m app.workers.document_ingestion` to atomically claim
a bounded batch. It is the only process allowed to download source files, run
OCR, call extraction, and write candidate facts.

## Before enabling it

1. Apply migrations `034_document_ingestion_safety.sql` through
   `036_document_ingestion_worker.sql` using the normal reviewed migration path.
   Do not apply them from a developer machine against a shared environment.
2. Build the normal backend image. It now includes Tesseract plus `eng` and
   `spa` language data; the worker uses the same image with a different command.
3. The `Deploy Backend to Cloud Run` workflow declares and updates the Job in
   `us-central1` from that image. It pins 2 GiB memory, a 300-second task timeout,
   one task, parallelism one, no platform retries, and the command
   `python -m app.workers.document_ingestion`. It also supplies only the worker's
   required Supabase secret references and Vertex settings; never copy credential
   values into source control or Cloud Scheduler payloads.
4. Run one execution manually before creating a schedule. Start at
   `DOCUMENT_INGESTION_BATCH_SIZE=1`; raise it only after observed execution
   durations show the chosen schedule will not overlap.
5. Schedule executions at a cadence that keeps the expected queue delay visible
   to patients (five minutes is the initial operating target). Use Cloud Scheduler
   or an equivalent job scheduler to execute the Job; it must not call the public
   upload API or the application process directly.

The workflow includes the Job because Cloud Run resolves an image tag to an
immutable digest at deployment. A Job created manually from `:latest` would
otherwise remain on its old digest after a later backend release.

## Acceptance check in a synthetic environment

Upload one born-digital PDF and one scanned Spanish image using a synthetic
patient. Confirm each run has a terminal `document_ingestion_runs` row, and that
each created candidate is `pending_review` with a page, bounding box, source
hash, extractor version, model version, and quoted evidence. Try an invented
medication name: it must leave the document in `needs_evidence_review` and create
no candidate. Then use the clinician retry action on a deliberately failed file
and verify it returns to `pending` before the job claims it.

Never use production-like documents for this check.

## Model-output boundary

The worker treats model output as an untrusted proposal. It uses the LLM to extract the
source-grounded clinical phrase and preserves that wording exactly in the pending candidate:
for example, `by mouth`, `P.O.`, `sublingual`, and `vía oral` remain the route values. The
worker does not normalize them through a keyword list or pretend that a fixed enum is a
medical ontology. Any coding belongs to a later terminology-backed, clinician-reviewed step
that records its provenance.

Before writing a candidate, the worker independently locates every proposed source field in
the recovered page text. A field it cannot locate is omitted and shown as an uncertainty;
the worker never guesses a nearby clinical value. Malformed or incomplete model output ends
as `needs_evidence_review`, creates no unreviewed fact, and does not spend a retry that
would merely repeat the same validation failure.

Extraction prompts are clinician-facing and evidence-bound. Patient summaries are a
separate, plain-language workload: they retain names, doses, frequency, and route while
not diagnosing, prescribing, or adding facts that were absent from the extraction.
