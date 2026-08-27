# INT-002 and INT-003 interoperability plan

## Goal

Demonstrate a clinician-facing SMART on FHIR R4 launch against a public sandbox,
import a bounded synthetic patient record, preserve the original FHIR resources as
provenance, and show the imported context in the clinician portal. This is a sandbox
demonstration only; it does not claim production EHR connectivity or real-PHI support.

## Verified starting point

- The backend has an extraction-oriented FHIR builder for Condition,
  AllergyIntolerance, and MedicationRequest. It did not import/export a FHIR record.
- The maintained Python dependency provides FHIR R5 by default and FHIR R4B as a
  subpackage. The project uses R4-compatible fields and R4B validation; exact R4
  sandbox conformance is required evidence, not an assumption.
- No SMART discovery, launch/callback route, OAuth state store, PKCE handling, token
  exchange, FHIR bundle persistence, or portal launch-context screen exists.
- Current portal authentication is local. A SMART token must not be treated as a local
  clinician credential or bypass care-team authorization.
- The prior Supabase project no longer exists. All database work remains migration-led
  and can be tested with fakes/fixtures until a new development project is available.

## Security and product decisions

1. Use OAuth authorization code flow with PKCE. Discover endpoints only from an
   allowlisted `iss` value and its `.well-known/smart-configuration` document.
2. Bind `state`, PKCE verifier, requested scopes, issuer, redirect URI, and expiry to
   one short-lived, single-use launch session. Store the verifier and any refresh token
   encrypted; never send either to the portal.
3. Validate the authorization response state exactly. Validate token-response scope and
   expiry; when an ID token is present, validate its signature, issuer, audience, nonce,
   and expiry using the issuer's discovery/JWK metadata. Do not assume an access token
   is a JWT.
4. Keep internal and external identities separate. A sandbox launch can create an
   imported-record session; a clinician must still be authenticated locally and assigned
   to the local patient before any local clinical action is available.
5. Start read-only with least-privilege resource scopes. Do not request write, offline,
   or broad wildcard scopes for the demonstration.
6. Persist the original synthetic FHIR resource JSON, source URL, version/last-updated
   data, import timestamp, and validation outcome. Derived local records remain
   `pending_review` clinical-fact candidates until explicitly approved.

## Phase A — FHIR mapping and validation boundary (INT-002)

### Deliverables

- A single resource registry that accepts only the supported resource types:
  Patient, Practitioner, Organization, CareTeam, Condition, AllergyIntolerance,
  MedicationRequest, MedicationStatement, Observation, DocumentReference,
  Appointment, Communication, CarePlan, Provenance, and AuditEvent.
- Domain-to-FHIR export mappers and FHIR-to-normalized import mappers. Each mapper must
  preserve identifiers, distinguish unknown from absent values, and reject unsupported
  shapes without partial persistence.
- FHIR R4-compatible payload validation through the maintained R4B models, plus a
  narrow compatibility fixture set validated against the chosen R4 sandbox.
- Bundle pagination, resource-count, payload-size, and resource-type limits.
- Identifier and duplicate rules: issuer + resource type + resource id + version (or a
  stable payload hash when no version exists) is the import idempotency key.
- Provenance and audit resource generation from the new clinical-fact registry without
  exposing private reasoning or fabricated confidence.

### Data work

Add migration-led tables for a FHIR import source, resource envelope, and launch/import
audit trail. The envelope must retain the raw FHIR JSON and validation result separately
from normalized local facts. Add RLS so patients see only approved imported facts and
assigned clinicians see the review/import record. Do not mutate existing medication,
condition, or allergy rows directly from an import.

### Evidence

- Unit fixtures cover every supported resource, missing required data, unsupported type,
  malformed identifier, duplicate resource, and pagination limit.
- Round-trip fixtures prove export -> validate -> import for the supported subset.
- Integration tests prove a rejected bundle writes no normalized facts, and a successful
  bundle creates only pending clinical-fact candidates with source lineage.

## Phase B — SMART launch service (INT-003)

### Configuration

Add explicit settings for the sandbox issuer allowlist, client ID, optional confidential
client secret, public callback URL, portal completion URL, encryption key, launch TTL,
and import limits. Production defaults must disable SMART until all mandatory settings
are present. Do not reuse Supabase JWT configuration for SMART validation.

### Backend flow

1. The clinician portal launch route accepts the EHR's `iss` and opaque `launch` handle.
   It requires an existing local clinician session and a selected, locally assigned patient,
   then sends them to protected `POST /api/v1/smart/launch`. The backend validates the
   issuer, retrieves SMART configuration, creates a short-lived launch session, generates
   PKCE values and state, encrypts the opaque handle at rest, and redirects to the
   authorization endpoint. In standalone mode, the same protected endpoint omits the
   opaque handle and requests patient/encounter launch context instead.
2. `GET /api/v1/smart/callback` rejects provider errors, missing or mismatched state,
   expired/replayed sessions, an unexpected issuer/audience, and insufficient scopes.
   It exchanges the code server-side and captures patient and encounter context.
3. The callback performs a bounded, read-only patient import through the INT-002
   registry. It stores a launch summary and produces a short-lived, single-use portal
   handoff ticket; browser-visible URLs must not contain access or refresh tokens.
4. Authenticated clinician-portal users redeem the ticket through a protected backend
   endpoint. The endpoint enforces local clinician identity and care-team access before
   returning the launch context and imported provenance.

### Supported sandbox import

Import Patient first, then the supported patient-scoped resources. Resolve referenced
Practitioner, Organization, and CareTeam records only when present in the returned
bundle or bounded follow-up reads. Retain unsupported resources as import warnings,
not silent drops or hard failures of the whole launch.

## Phase C — clinician portal and demonstration

- Add a clinician settings entry point for standalone sandbox launch and a launch-status
  page that handles expired or consumed handoff tickets safely.
- Add a patient-context banner showing sandbox source, external patient/encounter IDs,
  import time, source resource counts, warnings, and a clear synthetic-data label.
- Add a provenance panel that links an imported candidate fact to the original FHIR
  resource and mapped local candidate. It must show `pending_review`, never imply
  approval.
- Add a reproducible manual script: launch through SMART Health IT's R4 sandbox,
  select a synthetic patient, return to the deployed callback, and verify the imported
  context and lineage in the clinician portal.

## External prerequisites

The code and fixture work can proceed without Supabase. End-to-end launch requires:

1. A replacement Supabase development project with migrations through the SMART/import
   migrations applied.
2. A deployed HTTPS backend callback URL and matching clinician-portal URL; localhost
   is insufficient for the public sandbox unless tunneled.
3. A registered public or confidential sandbox client and the exact redirect URI.
4. A configured sandbox issuer and synthetic test patient. Initial target: SMART Health
   IT App Launcher R4. Inferno SMART App Launch testing is the conformance check.

## Recommended implementation order

1. Complete INT-002 registry, mappers, import envelope migration, fixtures, and
   provenance integration.
2. Add SMART configuration, discovery, PKCE/state service, and route tests using a mock
   authorization server.
3. Add callback token exchange, context validation, and bounded bundle import.
4. Add portal handoff/status/provenance UI and browser tests.
5. Recreate Supabase, deploy the callback, perform the public sandbox launch, then run
   the reproducible conformance script.

## Exit evidence

INT-002 is complete only when all supported mappings round-trip, malformed/duplicate
resources are handled safely, and imported candidates retain lineage. INT-003 is
complete only when the public sandbox launch validates state/PKCE/token context, imports
a synthetic patient bundle, and shows the source and provenance to an authenticated
clinician without granting clinical authority automatically.
