# Clinical facts and provenance

## Purpose

`clinical_facts` is the evidence-backed registry for clinical candidates derived from
records. It separates extracted or entered information from approved clinical truth:
insertion always starts as `pending_review`; only an explicit clinician review can set
the state to `approved`.

The initial integration registers document-extraction imports. Existing product tables
such as `medications`, `conditions`, `allergies`, and `obligations` remain their own
workflow records while the registry supplies reviewable provenance for records derived
from a document.

## Stored evidence

Each candidate stores a structured value, confidence score/band, and uncertainty. Its
supporting artifact is stored in `source_provenances` with the original source system,
source reference, document identifier and location, extractor version, optional model
version, and capture timestamp. `evidence_citations` connects the candidate to precise
excerpts and locations within that artifact.

## Lifecycle and audit

The permitted states are `pending_review`, `approved`, `rejected`, and `deleted`.
Corrections return a fact to `pending_review`, clearing the old reviewer decision.
Deletion is a soft lifecycle transition so its source and audit history survive.
Creation, correction, approval, rejection, and deletion each write an audit event with
the actor, timestamp, event type, and structured decision context.

`ClinicalFactService.list_approved(patient_id)` is the safe query for clinical-display
consumers. It intentionally excludes pending, rejected, and deleted candidates.

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
