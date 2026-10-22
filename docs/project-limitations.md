# Academic project explanation and limitations

## Problem and contribution

Outpatient care often spans source documents, medicines, follow-up activities and
several care teams. MediAgent demonstrates one attributable loop: import evidence,
review a candidate, publish approved care instructions, collect the patient's
response and return follow-up to the authorized care team.

The contribution is the connected workflow and its boundaries, not autonomous
clinical judgment. Presenters operate fictional patient and clinician accounts.
The modelled setting is California outpatient chronic care and polypharmacy;
it is not proof that the application has been evaluated in actual clinical practice.

## Architecture and authority

The patient portal is a mobile-first web app/PWA, not a native iOS/Android app.
The clinician portal is a desktop-first web workspace. A FastAPI backend handles
authorization, schedules, notifications and review operations. Supabase provides
Auth, PostgreSQL and document storage. A worker handles durable Nora turns; an
ingestion job reads uploaded synthetic documents. External model, speech, public
reference and email providers can be unavailable independently.

The [architecture contract](../.agent/ARCHITECTURE.md) and
[backend reference](../backend/README.md) describe actual boundaries. The critical
distinction is evidence versus authority: imported/extracted values are candidates.
Explicit authorized clinical review remains required to alter local truth.
Notification read state, alert acknowledgement, a model reply and successful
document processing never imply clinical approval.

## What the evidence supports

Automated tests and dated synthetic journeys support the particular software
contracts they exercised: authorization, saved state, retry/deduplication,
approval boundaries, source lineage and selected bilingual presentation paths.
The [evidence index](evidence/README.md) gives the underlying reports. Test counts,
CI success and deployment success are different from live acceptance.

They do not establish diagnostic accuracy, treatment safety, professional
translation validation, user adoption, improved health outcomes, HIPAA compliance,
regulatory clearance or commercial production readiness. No real-provider
research campaign or independent professional clinician review is required for
this master's-project scope, and none should be implied.

## Specific limits to disclose

| Area | Demonstrated scope | Do not claim |
| --- | --- | --- |
| Clinical reasoning | Bounded assistance with source context and deterministic safety rules | Diagnosis, prescribing or comprehensive clinical correctness |
| Medicines | Source-based comparison and authorized reconciliation | A comprehensive interaction or therapeutic-equivalence engine |
| Records | Supported imported resource types, provenance and candidate review | Every document, scan or medical meaning can be extracted correctly |
| FHIR | Bounded imports and a validated canonical clinical-core collection; separately reviewed handoff export | A complete longitudinal chart export, EHR write-back, full R4 profile certification or general interoperability |
| SMART | Recorded public-sandbox integration; standalone journey has its own acceptance | Production EHR connectivity or blanket launch certification |
| Language | en-US/es-MX UI, source-preserving translations and reviewed plan wording | Every draft is approved, every translation preserves all meaning, or changing language changes schedules |
| Voice | Transport/playback implementation with text fallback | Real-phone acceptance until the actual device/browser is tested |
| Safety | Rule-based guidance and supervised review boundaries | Continuous monitoring, guaranteed escalation delivery or a substitute for emergency services |
| ADR / MedWatch | Patient testimony, clinician review and draft/preview/export | Confirmed causality from a report, automated regulatory submission or FDA transmission |
| Notifications / email | In-app events and selected generic opt-in email notices | Direct clinician email of clinical content, guaranteed inbox receipt or every reminder sent by email |
| Runtime | Durable turns and recorded recovery paths | No outages, unlimited concurrency or a proven explanation for every historical intermittent failure |

The generic action-tier service is infrastructure, not a new production executor.
Its hardening does not replace feature-specific care-plan publication or imply
every possible clinical action has a supported route. Preserve explicit open
scope in [TASKS.md](../.agent/TASKS.md), including the guarded OpenTelemetry
dependency exception; a CI exception is not a patched dependency.

## How to present results honestly

State the revision, scenario and evidence actually observed. Distinguish prepared
history from live actions, deterministic application behavior from generated
content, and successful synthetic acceptance from clinical validation. Disclose
known failures and use the [recovery procedure](expo-recovery.md) rather than
presenting an unavailable service as a successful live response.
