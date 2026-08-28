# Supabase Recreation and Verification Guide

Use this guide to recreate the project after an inactive instance is removed. It is environment-neutral: do not copy credentials, project references, or synthetic seed data between environments.

## Create the project

1. Create a new development project in the required region and record its URL, anon key, service-role key, and JWT secret in the team secret store.
2. Copy `.env.example` to `.env` locally. Set `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `SUPABASE_JWT_SECRET`; never commit that file.
3. Configure clinician and patient portal environment variables with the new public URL and anon key.
   Leave `NEXT_PUBLIC_ENABLE_DASHBOARD_REALTIME=false` until the Realtime publication,
   RLS behavior, and clinician JWT path have been verified end to end. The clinician
   dashboard remains functional through its authenticated backend API while it is disabled.
4. Enable email authentication and MFA for clinician accounts. After migrations complete, configure **Authentication → Auth Hooks → Customize Access Token (JWT) Claims hook** to use `public.custom_access_token_hook` and confirm it shows as enabled. This Auth control-plane setting is not recorded by a SQL migration.

## Apply migrations

Apply every SQL file through the repository migration ledger against an empty development database. The ledger records the complete filename and SHA-256 checksum, so a rerun skips unchanged files and stops if an applied migration was edited. Do not run a reset, seed, or migration command against a production database.

```bash
# In Dashboard → Connect, copy the Session pooler URI (port 5432) to the
# local secret store, then set MEDIAGENT_DB_URL from that value without
# echoing, committing, or reconstructing the password-bearing URI.
./scripts/apply-supabase-migrations.sh
./scripts/verify-supabase-schema.sh
```

Copy the URI rather than assembling it: the pooler tenant, host, and password encoding are project-specific. The Session Pooler supports IPv4 clients and is required here because the migration command maintains a session while applying each SQL file.

This currently applies migrations `001` through `025`, including canonical clinical facts (`017`), SMART/FHIR import envelopes (`018`), clinical-action approval controls (`019`), database-security hardening (`020`), and the least-privilege server-only grants used by the synthetic fixture, A2A retry worker, patient feed, reminder schedules, and adherence statistics (`021`–`025`). The history contains two `011` filenames; the migration ledger uses full filenames and checksums, making the ordering unambiguous.

## Configure SMART staging

Cloud Run staging must expose a stable HTTPS backend URL. Set these server-side values there:

```bash
SMART_CLIENT_ID=<registered SMART sandbox client id>
SMART_CLIENT_SECRET=<only if the sandbox registration requires one>
SMART_REDIRECT_URI=https://YOUR_BACKEND/api/v1/smart/callback
SMART_STATE_ENCRYPTION_KEY=<a Fernet-compatible key generated in the secret store>
SMART_ALLOWED_ISSUERS=https://launch.smarthealthit.org/v/r4/fhir
# The backend adds `launch` for EHR launch or `launch/patient launch/encounter`
# for standalone launch. Keep this value to least-privilege resource reads.
SMART_SCOPES="patient/Patient.read patient/Encounter.read patient/Condition.read patient/AllergyIntolerance.read patient/MedicationRequest.read patient/MedicationStatement.read patient/Observation.read patient/DiagnosticReport.read patient/Procedure.read patient/CarePlan.read patient/DocumentReference.read"
```

Register the exact `SMART_REDIRECT_URI` with the sandbox. For an EHR launch, separately
register the clinician portal's launch route (for example,
`https://clinician.mediagent.live/smart-import`) as the app launch URL. The portal receives
the EHR's `iss` and opaque `launch` handle, then requires local clinician sign-in and local
care-team/patient selection before the backend begins authorization. Tokens and authorization
codes remain server-side; the browser receives only a short-lived, single-use review handoff.

## Verification checklist

- [ ] Every committed migration is recorded with its exact filename and SHA-256 checksum in `public.schema_migrations`.
- [ ] Tables include `clinical_facts`, `source_provenances`, `fhir_imports`, `fhir_import_resources`, and SMART session/handoff tables.
- [ ] RLS is enabled for clinical facts and FHIR import tables.
- [ ] `public.custom_access_token_hook` is enabled in **Authentication → Auth Hooks**, not merely present in the database.
- [ ] A fresh password sign-in for a synthetic patient produces a JWT with `user_role=patient`, and the backend accepts that JWT. Repeat for a clinician before a clinician demo.
- [ ] Authentication → URL Configuration uses the intended portal site URL and includes the approved patient and clinician redirect URLs required for password-reset or email-link flows.
- [ ] A clinician has an active care-team assignment to a synthetic patient.
- [ ] Cloud Run staging callback is HTTPS and registered with the SMART sandbox.
- [ ] A sandbox import creates raw resource envelopes and pending facts only.
- [ ] A clinician can inspect lineage and explicitly approve, reject, or correct each candidate.

Use synthetic or deidentified sandbox records only. This project does not accept real patient data for this demo.
