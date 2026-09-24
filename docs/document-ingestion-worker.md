# Document-ingestion worker

Document upload is request-only. The API records a `pending` document, and the
Cloud Run Job runs `python -m app.workers.document_ingestion` to atomically claim
a bounded batch. It is the only process allowed to download source files, run
OCR, call extraction, and write candidate facts.

## Before enabling it

1. Apply migrations `034_document_ingestion_safety.sql` through
   `039_document_summary_retry_schedule.sql` using the normal reviewed migration path.
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

Upload one born-digital PDF, one scanned Spanish image, and one multi-frame TIFF using a synthetic
patient. Confirm each run has a terminal `document_ingestion_runs` row, and that
each created candidate is `pending_review` with a page, bounding box, source
hash, extractor version, model version, and quoted evidence. Try an invented
medication name: it must leave the document in `needs_evidence_review` and create
no candidate. Then use the clinician retry action on a deliberately failed file
and verify it returns to `pending` before the job claims it.

For the TIFF, also confirm that `preview_status` becomes `ready`, the derived PDF is stored under
the document's private preview path, and both the patient and an assigned clinician can open the
same pages without receiving a permanent storage URL. A preview failure must preserve the original
for download and review; it must not turn the clinical extraction into a fabricated success.

Never use production-like documents for this check.

## Verification queries

`document_ingestion_runs` owns execution state. `clinical_facts` deliberately does
not have a `status` or `source_document_id` column: pending candidates use
`review_state`, and document lineage is held through `source_provenances` and
`evidence_citations`.

```sql
-- Recent Job outcomes (use this after a manual execution).
select status, attempt, candidate_fact_count, failure_code, page_count,
       extraction_method, extractor_version, started_at, completed_at
from public.document_ingestion_runs
order by created_at desc
limit 10;

-- Candidate review state and the source evidence for one document.
select cf.review_state, cf.fact_type, sp.document_id,
       ec.location, ec.excerpt, cf.created_at
from public.clinical_facts cf
join public.evidence_citations ec on ec.fact_id = cf.id
join public.source_provenances sp on sp.id = ec.provenance_id
where sp.document_id = '<synthetic-document-uuid>'
order by cf.created_at desc;
```

## Scheduling after acceptance

Do **not** create a Scheduler trigger until every synthetic acceptance check above has
passed and the execution duration has been observed. Then create a Cloud Scheduler
trigger for this Job with the following initial contract:

- name: `mediagent-document-ingestion-every-5m`
- Scheduler region: `us-central1`
- schedule: `*/5 * * * *`
- timezone: `America/Los_Angeles`
- invoker: a dedicated service account granted only `roles/run.invoker` on
  `mediagent-document-ingestion`

Cloud Scheduler invokes the Job's `:run` endpoint with OAuth. The Job's one task and
parallelism limit apply within an execution, not across executions. The database claim
prevents the same document from being processed twice, but a five-minute trigger can
still overlap a long-running execution. If the observed synthetic run approaches the
cadence, keep the Job manual or choose a slower schedule before enabling the trigger.

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

## The patient explanation has its own lifecycle

Ingestion does not generate the patient explanation. It records the clinical result and
leaves `summary_status = 'pending'`; the same Job execution then claims owed explanations
separately through `claim_pending_document_summary` and builds each one from the candidate
facts that document already has. Nothing in this second phase downloads the source, runs
OCR, or writes a candidate, so a failure here cannot duplicate facts or alter the clinical
record — and a retry costs one generation call, not another extraction.

| `summary_status` | Meaning |
|---|---|
| `not_required` | The document has no grounded candidate to explain. Generating prose here would be invention, so none is attempted. |
| `pending` | Owed. The next eligible Job execution claims it; `summary_failure_code` names why the previous attempt did not finish. |
| `processing` | Claimed by a running execution. |
| `ready` | `ai_summary` holds the explanation and `summary_prompt_version` records what produced it. |
| `failed` | Not retried automatically. A clinician assigned to the patient can requeue it. |

A provider outage leaves the row `pending` with `summary_failure_code =
'provider_unavailable'` and `summary_next_attempt_at`. Automatic retries wait for recorded
two- then five-minute backoff. A third provider failure becomes the visible terminal
`attempt_limit_reached` state; it does not schedule a fourth model call. Fresh first attempts
normally take priority over retries, but a retry that has been due for 15 minutes moves into an
anti-starvation lane ahead of fresh work. This prevents one provider-failed document from
repeatedly consuming a small batch while a newly extracted document waits, without allowing a
sustained upload stream to strand an eligible retry. The claim uses a ten-minute lease: an
execution that stops after claiming work is returned safely to `pending`.
An empty model response fails immediately, because repeating an identical prompt over
identical candidates would only repeat it.

`enqueue_document_summary_retry` backs the clinician retry action and resets the attempt
counter, which the ingestion retry deliberately does not: re-running ingestion spends OCR
and re-proposes candidates, while a summary retry only re-reads candidates that already
exist. Each clinician action buys one bounded cycle.

Both portals show the reason rather than an empty panel. Patients see it in their own
locale; clinicians additionally see that extraction and review candidates are unaffected,
plus the retry action when the row is `failed`.

```sql
-- Explanations that are owed or unavailable, and why.
select id, parse_status, summary_status, summary_failure_code,
       summary_attempts, summary_last_attempt_at, summary_next_attempt_at,
       summary_prompt_version
from public.documents
where parse_status = 'completed'
  and summary_status in ('pending', 'processing', 'failed')
order by summary_last_attempt_at desc nulls first
limit 20;
```

### Deploy ordering

`deploy-backend.yml` ships the image before migrations are applied by hand, so the code
reaches production before these columns do. Every write and clinician-facing read of the
summary lifecycle degrades safely during that window: if `038` is absent, documents still
reach their clinical terminal state; if only `039` is absent, the existing `038` lifecycle
continues without scheduling metadata. The clinician document list still loads, and owed
explanations stay unclaimed only until the matching migration is applied.

When a patient selects a document in chat, the server authorizes the document first and supplies
only its bounded patient-facing summary to that single agent invocation. The model cannot choose a
document ID or receive a storage URL. A document without a usable summary must be described as
unavailable rather than answered from general medical knowledge as though it were the patient's
record.
