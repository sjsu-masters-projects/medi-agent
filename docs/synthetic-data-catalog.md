# Synthetic data catalog

**Owner:** Platform lane  
**Last reviewed:** 2026-08-20  
**Source:** `backend/src/app/db/seed/demo_data.py` and
`backend/scripts/seed_demo_environment.py`

## Purpose and boundary

This catalog defines the deterministic fixture used for development, demonstrations,
and regression checks. Every person, organization, date, identifier, and clinical
event is fictional. The fixture is educational test data, not medical advice,
clinical guidance, or a substitute for a reviewed patient record.

It must never be mixed with real data or seeded into production. The reset command
refuses production and only targets the reserved `demo.mediagent.local` accounts and
`DEMO-CA-*` clinics.

## Fixture inventory

| Type | Count | Contents |
| --- | ---: | --- |
| Clinics | 2 | North Valley Chronic Care and South Bay Care Collaborative |
| Clinician/staff accounts | 4 | Two providers, one nurse, one clinic administrator |
| Patient accounts | 2 | One American-English and one Mexican-Spanish preference |
| Care-team assignments | 2 | Each patient assigned to a clinic provider |
| Documents per patient | 2 | Historical medication reconciliation and current care summary metadata |
| Medication timeline per patient | 3 | Active metformin; historical lisinopril 20 mg; active lisinopril 10 mg after change |
| Conditions per patient | 2 | Synthetic diabetes and hypertension records |
| Other timeline events per patient | 1 allergy, 1 exercise obligation, 2 adherence logs, 1 symptom report, 1 appointment, 1 notification |

## Personas and intended coverage

| Fixture | Language | Care-loop coverage |
| --- | --- | --- |
| Maria Garcia | `en-US` | Document review, active medication list, historical dose change, allergy visibility, adherence, follow-up appointment |
| Jose Martinez | `es-MX` | The same longitudinal workflow with Mexican-Spanish preference for portal and notification contract coverage |
| Dr. Avery Morgan / Nurse Taylor Reed | — | North clinic clinician and staff assignment/access paths |
| Dr. Lucia Rivera / Morgan Chen | — | South clinic clinician and administrator assignment/access paths |

The dose change is deliberately represented as two separate medication rows: an
inactive historical 20 mg lisinopril record ending 2026-08-15 and an active 10 mg
record starting 2026-08-16. The associated dizziness report is only a review cue; it
does not assert causality or provide a diagnosis.

## Representation limits

- Seeded document rows are metadata and synthetic storage paths (`demo/...`); the
  seed does not upload binary files. Extraction regression fixtures remain under
  `backend/tests/fixtures/`.
- The data does not claim FHIR conformance, provenance approval, an ADR conclusion,
  a prescribing decision, or real notification delivery.
- Account passwords are provided at runtime through `DEMO_ACCOUNT_PASSWORD` and are
  never written to source control.

## Change control

Any fixture change must update this catalog, the seed tests, and the relevant
demonstration steps. Preserve determinism: use fixed values and explicit dates rather
than current time, random identifiers, or network-sourced content. Add a scenario only
when it supports a named product journey or regression path.
