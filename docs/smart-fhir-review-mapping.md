# SMART FHIR import review mapping

MediAgent uses the SMART Health IT public R4 sandbox only with synthetic data.
An external resource is imported as a provenance-backed **candidate**, never as
an automatic update to the local patient record. An assigned clinician must
explicitly select fields and record an audited reconciliation decision before
an imported medication, condition, or allergy can change local truth.

## What clinicians see

The patient detail page has an **External records** tab. It separates candidates
from the existing local profile and shows the following for each candidate:

- mapped fields that can be reviewed without interpreting the original payload;
- review state, uncertainty, and any validation or mapping warning;
- source issuer, FHIR resource type, external resource identifier, and version;
- the original FHIR JSON only after the clinician explicitly chooses **Source**.

Approval, correction, and rejection are recorded in the clinical-fact audit
trail. Imported candidates begin with **unknown** clinical confidence:
structured source fidelity is not a clinical assessment. A clinician may add a
new medication, condition, or allergy, or update selected non-empty fields on
a conservatively matched local record. No imported value clears a local field;
medication updates retain the existing medication ID and therefore preserve
reminders, adherence, and ADR links. Imported demographics and every other
resource type remain evidence-only. A correction changes only the pending
candidate and preserves the original resource envelope.

## Supported R4-compatible resource mappings

| FHIR resource | Candidate type | Clinician-visible mapped fields | R2 canonical destination | Deliberately not inferred |
| --- | --- | --- | --- | --- |
| `Patient` | `patient_demographics` | name, birth date, administrative gender | None — comparison-only identity confirmation | identity match, account creation, local demographic overwrite |
| `Encounter` | `encounter` | status, class, type, period | None — evidence-only | billing interpretation or care-team assignment |
| `Condition` | `condition` | name, recognized ICD-10, clinical status | `conditions.name`, `icd10_code`, `status`, `notes` — selected fields only | diagnostic certainty beyond the source |
| `AllergyIntolerance` | `allergy` | allergen, clinical status, criticality, reactions, reaction severity | `allergies.allergen`, `reaction`, `severity` — selected fields only | severity from FHIR criticality; a missing severity becomes `unknown` |
| `MedicationRequest`, `MedicationStatement` | `medication` | name, RxCUI, dosage, frequency, route, instructions, dates, status | `medications` selected fields; source status can become `is_active` only when known | automatic prescription reconciliation or reminder creation |
| `Observation` | `observation` | code, quantity or coded value, effective time, status, interpretation, reference range | None — evidence-only | trend or clinical interpretation |
| `DiagnosticReport` | `diagnostic_report` | report code, conclusion, status, effective and issued times, result count | None — evidence-only | a diagnosis based on report text |
| `Procedure` | `procedure` | procedure code, status, performed time, reason, body site | None — evidence-only | outcome or follow-up plan |
| `CarePlan` | `care_plan` | title/category, narrative description, status, intent, period, activities, addressed conditions | None — evidence-only | acceptance as a local plan of care or an obligation |
| `DocumentReference` | `document_reference` | type, description, date, status, authors, content types | None — evidence-only | document download, OCR, or new local document storage |

Unsupported resource types are preserved in the import envelope with a warning
but do not create a candidate fact. Missing or partial source fields are shown
as `Not supplied`; the review UI does not manufacture a value.

The review screen can be filtered by source, mapped candidate type, review
state, reconciliation state, and import date. It uses the
candidate fields above for clinician-facing review; the **Source** action is
the only place raw FHIR JSON is shown. Corrections use individual mapped fields
where possible. Structured fields retain JSON only when preserving that source
structure is necessary.

FHIR instants in the review screen are rendered in the selected local patient's
configured IANA timezone (falling back to UTC if it is unavailable). Date-only
FHIR values stay date-only and are never shifted by timezone conversion.

## Reconciliation lifecycle

Importing only creates a candidate. An assigned clinician must explicitly choose
whether to add a new medication, condition, or allergy; update selected non-empty
fields on a matched local record; keep the existing local record; defer; or reject.
Evidence-only resources can be marked reviewed but cannot create or alter local truth.
The decision records the candidate snapshot, selected fields, target, before/after
snapshots, actor, source version, and note atomically. A reconciled candidate becomes
immutable evidence; a later source version creates a separate pending candidate.

Mappings are applied only when a resource is imported. Existing candidates are not
silently rewritten when a later mapper version exposes more source fields, because that
could overwrite a clinician correction or obscure what was reviewed.

### Mapper re-projection for untouched candidates

When a mapper gains clinically useful display fields, an operator may run
`backend/scripts/reproject_fhir_candidates.py --dry-run` to produce a deterministic
report from the stored FHIR envelopes. Applying a report requires its reviewed SHA-256
value and an actively assigned clinician ID. The service-role-only database transaction
locks the candidate and re-checks that it is still pending, unreconciled, source-version
matched, and has no audit event beyond creation. It then records an append-only mapping
revision containing both candidate snapshots before refreshing the candidate display
value. This never changes a canonical clinical record or an external source envelope.
For envelopes without `meta.versionId`, the stored resource-content hash is the exact
source version used for the same comparison, matching import-time version semantics.
Some pre-R2 candidates have a legacy version marker that does not match their directly
cited stored envelope. They are eligible only when that citation resolves to the exact
resource ID and its content hash still matches the dry-run snapshot; the mapping audit
records both the legacy marker and the envelope's actual version.
After re-projection, a later source withdrawal retains the candidate and mapping revision
as withdrawn evidence rather than deleting that audit history.

## Source withdrawal

An untouched pending import can be removed. Once any candidate has a clinician
decision or mapper re-projection, its source and immutable audit history are retained
instead and marked withdrawn. A withdrawn candidate cannot be reconciled again;
clinicians can still inspect its provenance and the affected local record.

## Two valid launch paths

### EHR-initiated launch

1. The sandbox EHR selects a patient and practitioner, then opens
   `https://clinician.mediagent.live/smart-import` with its `iss` and opaque
   `launch` context.
2. A locally signed-in clinician selects an already assigned local synthetic
   patient. This local selection is an import target, not an external patient
   match.
3. MediAgent starts a server-side authorization-code flow with PKCE, then the
   sandbox redirects to the backend callback.
4. The backend exchanges the code, reads the permitted external resources,
   stores original envelopes, and creates pending candidates.
5. The portal redeems a short-lived handoff ticket and opens SMART import
   review.

The return to the sandbox after the first portal visit is expected: the EHR
launch supplies context, while the authorization-code flow separately obtains
the scoped read permission.

### Standalone launch from the portal

Opening `/smart-import` with no query string does **not** reuse an old EHR
selection. After the clinician chooses a local patient and presses **Launch
sandbox import**, MediAgent starts a fresh standalone SMART authorization. The
sandbox then supplies its own patient and encounter launch context. The same
candidate/provenance/review rules apply.

## Standards references

- [SMART App Launch](https://www.hl7.org/fhir/smart-app-launch/app-launch.html)
- [SMART scopes and launch context](https://hl7.org/fhir/smart-app-launch/scopes-and-launch-context.html)
- [FHIR R4 Provenance](https://www.hl7.org/fhir/R4/provenance.html)
- [FHIR R4 AuditEvent](https://www.hl7.org/fhir/R4/auditevent.html)
