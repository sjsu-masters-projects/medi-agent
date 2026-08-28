# SMART FHIR import review mapping

MediAgent uses the SMART Health IT public R4 sandbox only with synthetic data.
An external resource is imported as a provenance-backed **candidate**, never as
an automatic update to the local patient record. Clinician review is required
before a candidate can be approved.

## What clinicians see

The patient detail page has a **SMART imports** tab. It separates candidates
from the existing local profile and shows the following for each candidate:

- mapped fields that can be reviewed without interpreting the original payload;
- review state, uncertainty, and any validation or mapping warning;
- source issuer, FHIR resource type, external resource identifier, and version;
- the original FHIR JSON only after the clinician explicitly chooses **Source**.

Approval, correction, and rejection are recorded in the existing clinical-fact
audit trail. Imported candidates begin with **unknown** clinical confidence:
structured source fidelity is not a clinical assessment. Approval does not overwrite existing local medications,
conditions, allergies, or demographics. A correction changes only the pending
candidate and preserves the original resource envelope.

## Supported R4-compatible resource mappings

| FHIR resource | Candidate type | Clinician-visible mapped fields | Deliberately not inferred |
| --- | --- | --- | --- |
| `Patient` | `patient_demographics` | name, birth date, administrative gender | identity match, account creation, local demographic overwrite |
| `Encounter` | `encounter` | status, class, type, period | billing interpretation or care-team assignment |
| `Condition` | `condition` | condition name, clinical status, onset | diagnostic certainty beyond the source |
| `AllergyIntolerance` | `allergy` | allergen, clinical status, reactions | severity if the source does not state it |
| `MedicationRequest`, `MedicationStatement` | `medication` | medication name, status, dosage instructions | medication reconciliation or an active local prescription |
| `Observation` | `observation` | code, value, effective time, status | trend or clinical interpretation |
| `DiagnosticReport` | `diagnostic_report` | report code, conclusion, status | a diagnosis based on report text |
| `Procedure` | `procedure` | procedure code, status, performed time | outcome or follow-up plan |
| `CarePlan` | `care_plan` | title, description, status, intent | acceptance as a local plan of care |
| `DocumentReference` | `document_reference` | type, description, date, status | document download, OCR, or new local document storage |

Unsupported resource types are preserved in the import envelope with a warning
but do not create a candidate fact. Missing or partial source fields are shown
as `Not supplied`; the review UI does not manufacture a value.

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
