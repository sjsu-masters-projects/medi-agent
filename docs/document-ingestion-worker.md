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
3. Create a Cloud Run Job in `us-central1` from that image with command
   `python -m app.workers.document_ingestion`, at least 2 GiB memory, a 300-second
   task timeout, one task, and no more than one concurrent execution.
4. Give the job the same runtime configuration and service account access as the
   backend service: Supabase URL/keys/JWT secret, Vertex project/location and
   credentials, and the configured model settings. Do not copy credential values
   into source control or Cloud Scheduler payloads.
5. Schedule executions at a cadence that keeps the expected queue delay visible
   to patients (five minutes is the initial operating target). Use Cloud Scheduler
   or an equivalent job scheduler to execute the Job; it must not call the public
   upload API or the application process directly.

## Acceptance check in a synthetic environment

Upload one born-digital PDF and one scanned Spanish image using a synthetic
patient. Confirm each run has a terminal `document_ingestion_runs` row, and that
each created candidate is `pending_review` with a page, bounding box, source
hash, extractor version, model version, and quoted evidence. Try an invented
medication name: it must leave the document in `needs_evidence_review` and create
no candidate. Then use the clinician retry action on a deliberately failed file
and verify it returns to `pending` before the job claims it.

Never use production-like documents for this check.
