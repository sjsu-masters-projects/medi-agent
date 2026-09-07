# Clinical facts and provenance

## Purpose

`clinical_facts` is the evidence-backed registry for clinical candidates derived from
records. It separates extracted or entered information from approved clinical truth:
insertion always starts as `pending_review`; only an explicit clinician review can set
the state to `approved`.

Document and SMART imports register candidates only. Existing product tables such as
`medications`, `conditions`, and `allergies` remain canonical local truth until an
assigned clinician makes an explicit, audited reconciliation decision. Imported
demographics never update the local profile. Care plans, encounters, observations,
diagnostic reports, procedures, document references, and extracted follow-up text are
evidence-only in R2; they do not create obligations or new canonical record types.

## Stored evidence

Each candidate stores a structured value, confidence score/band, and uncertainty. Its
supporting artifact is stored in `source_provenances` with the original source system,
source reference, document identifier and location, extractor version, optional model
version, capture timestamp, and (when withdrawn) the withdrawal timestamp and reason.
`evidence_citations` connects the candidate to precise excerpts and locations within
that artifact.

## Lifecycle, reconciliation, and audit

The permitted states are `pending_review`, `approved`, `rejected`, and `deleted`.
Corrections return a fact to `pending_review`, clearing the old reviewer decision.
Deletion is a soft lifecycle transition so its source and audit history survive.
Creation, correction, approval, rejection, and deletion each write an audit event with
the actor, timestamp, event type, and structured decision context.

`ClinicalFactService.list_approved(patient_id)` is the safe query for clinical-display
consumers. It intentionally excludes pending, rejected, and deleted candidates.

For an imported medication, condition, or allergy, the reconciliation workspace may
record one of `add`, `update selected fields`, `keep existing`, `defer`, or `reject`.
Evidence-only records may instead be marked reviewed. The service-role-only database
operation locks the candidate and requested local target, verifies the active care-team
assignment, applies only clinician-selected non-empty fields, then records the
before/after snapshots and immutable reconciliation event in the same transaction.
Medication updates retain the existing local medication ID, so reminders, adherence,
and ADR references remain attached. Imports never create reminders. Allergy severity is
`unknown` unless the source supplies a reaction severity; FHIR criticality is retained
as evidence and is not treated as severity.

An external FHIR patient is bound to one local patient by issuer and external patient
ID only after a clinician confirms the comparison identity. A mismatch requires a
reason and a binding already attached to another local patient is blocked. A later
external resource version becomes a new candidate; a reconciled candidate is immutable
evidence. An import with only untouched pending candidates may be removed. Once a
clinician has made any reconciliation decision, its source and immutable audit history
are retained and marked withdrawn rather than deleted. If an applied source is
withdrawn, the local record and audit trail remain for clinician follow-up.

## Lineage and access

`ClinicalFactService.get_lineage(fact_id, patient_id)` resolves a fact to its
citations and source artifacts. `list_facts_for_document(document_id, patient_id)`
resolves a source document to the non-deleted candidates it supports.

Row-level policies allow a patient to read only their approved facts and related
evidence. An assigned clinician may read candidates and their audit trail for review.
Direct client mutations are not granted; lifecycle changes go through the backend
service so each transition is audited.

## FHIR provenance and audit representation

Assigned clinicians can request `GET /api/v1/smart/patients/{patient_id}/facts/{fact_id}/fhir-audit`.
It generates, but does not persist or transmit, one validated FHIR R4B `Provenance`
resource and ordered `AuditEvent` resources from the existing local lineage and audit
trail. The response identifies the local fact with a stable identifier, preserves source
artifact references, and represents lifecycle action and timestamp only. It deliberately
excludes clinical-fact values, evidence excerpts, reviewer notes, and private reasoning.

The route first verifies the requesting clinician's existing care-team assignment. It
does not create a FHIR server endpoint, change local review state, or grant authority to
an external SMART identity.

## External-record review

The clinician portal exposes SMART and document candidates in a patient-level external
records workspace. It supports source, mapped-type, review-state, reconciliation-state,
and date filters; paginates large imports; and shows a candidate beside its
conservative local match with field-level selection and before/after preview. The
ordinary list is clinical-language-first; original FHIR JSON or document evidence is
available only through a separate, care-team-authorized source request. See
[`smart-fhir-review-mapping.md`](smart-fhir-review-mapping.md) for the resource-to-field
contract and the EHR-initiated versus standalone launch behavior.
