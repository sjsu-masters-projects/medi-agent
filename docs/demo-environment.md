# Synthetic demonstration environment

This environment is for local, demo, or staging use only. It contains no real patient
data and must never be pointed at a production project.

The precise personas, timeline content, coverage intent, and limitations are recorded
in [`synthetic-data-catalog.md`](synthetic-data-catalog.md). Update that catalog with
any fixture change.

## Provision

Apply the database migrations, configure the local Supabase service credentials, and
provide a password only in the shell that runs the seed:

```bash
export DEMO_ACCOUNT_PASSWORD='choose-a-local-password'
PYTHONPATH=backend/src backend/.venv/bin/python backend/scripts/seed_demo_environment.py
```

The command is idempotent: it creates or updates the reserved clinics, accounts,
care-team assignments, records, medications, allergies, adherence, symptoms,
appointments, and notifications. Preview the content without connecting to Supabase:

```bash
PYTHONPATH=backend/src backend/.venv/bin/python backend/scripts/seed_demo_environment.py --dry-run
```

## Demo accounts

All accounts use the password supplied through `DEMO_ACCOUNT_PASSWORD`; no password is
stored in the repository.

| Account | Role | Clinic |
| --- | --- | --- |
| `dr.avery@demo.mediagent.local` | Clinician | North Valley Chronic Care |
| `nurse.taylor@demo.mediagent.local` | Nurse | North Valley Chronic Care |
| `dr.rivera@demo.mediagent.local` | Clinician | South Bay Care Collaborative |
| `staff.chen@demo.mediagent.local` | Clinic administrator | South Bay Care Collaborative |
| `maria.garcia@demo.mediagent.local` | Patient, American English | North Valley Chronic Care |
| `jose.martinez@demo.mediagent.local` | Patient, Mexican Spanish | South Bay Care Collaborative |

## Reset

Reset is intentionally guarded. It refuses production, requires
`--confirm-demo-reset`, and deletes only accounts in the reserved
`demo.mediagent.local` domain and the two `DEMO-CA-*` clinics.

```bash
export DEMO_ACCOUNT_PASSWORD='choose-a-local-password'
PYTHONPATH=backend/src backend/.venv/bin/python backend/scripts/seed_demo_environment.py \
  --reset --confirm-demo-reset
```

Use reset only for the synthetic local/demo environment. Do not use it as a general
database cleanup tool.
