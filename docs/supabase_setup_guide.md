# Supabase Setup Guide

> For any team member setting up MediAgent locally or reviewing the database.

## Supabase Project

| Key | Value |
|-----|-------|
| Organization | `medi-agent` |
| Project | `MediAgent` |
| Region | Check dashboard |
| Dashboard | [supabase.com/dashboard](https://supabase.com/dashboard) |

## Connection

```
postgresql://postgres:[PASSWORD]@db.tsbjrzlzrejzlfkmhxpz.supabase.co:5432/postgres
```

Get the password from the team lead or `.env` file (never commit it).

## Running Migrations

Migrations live in `backend/src/app/db/migrations/` and must be run in order:

```bash
# Set your connection string
export DB_URL="postgresql://postgres:YOUR_PASSWORD@db.tsbjrzlzrejzlfkmhxpz.supabase.co:5432/postgres"

# 1. Schema: enums, tables, indexes, triggers
psql "$DB_URL" -f backend/src/app/db/migrations/001_initial_schema.sql

# 2. RLS: row-level security policies
psql "$DB_URL" -f backend/src/app/db/migrations/002_rls_policies.sql

# 3. Storage: buckets + storage RLS
psql "$DB_URL" -f backend/src/app/db/migrations/003_storage_and_auth.sql
```

> [!IMPORTANT]
> These migrations are **idempotent-safe on first run only**. If re-running, you'll need to drop existing objects first or use the Supabase dashboard SQL editor to reset.

## Database Overview

### Tables (16)

| Table | Purpose | FK Parent |
|-------|---------|-----------|
| `patients` | Patient profiles | `auth.users` |
| `clinicians` | Clinician profiles | `auth.users` |
| `care_teams` | Patient ↔ Clinician junction | patients, clinicians |
| `documents` | Uploaded medical records | patients |
| `medications` | Active/past medications | patients, care_teams |
| `obligations` | Diet/exercise/custom tasks | patients, care_teams |
| `adherence_logs` | Med taken / obligation done | patients |
| `conditions` | Diagnoses (ICD-10) | patients |
| `allergies` | Known allergies | patients |
| `symptom_reports` | Patient-reported symptoms | patients, medications |
| `adr_assessments` | Adverse drug reaction flags | patients, symptom_reports |
| `medwatch_drafts` | FDA 3500A form drafts | adr_assessments |
| `appointments` | Scheduled visits | patients, care_teams |
| `chat_messages` | Chat history | patients |
| `notifications` | Push/in-app alerts | patients |
| `clinician_messages` | Clinician → Patient messages | clinicians, patients |

### Enum Types (20)

All enum types mirror `backend/src/app/models/enums.py`. If you add a new enum value in Python, you must also `ALTER TYPE ... ADD VALUE` in PostgreSQL.

### RLS Model

- **Patients** see only their own data (`patient_id = auth.uid()`)
- **Clinicians** see only their assigned patients (checked via `care_teams` junction where `status = 'active'`)
- **Service role** bypasses RLS (used by backend agents and cron jobs)
- Helper function: `is_assigned_clinician(patient_id)` is used across all policies

### Storage Buckets

| Bucket | Purpose | Max Size | Public |
|--------|---------|----------|--------|
| `documents` | Medical PDFs/images | 20MB | No |
| `avatars` | Profile photos | 2MB | Yes |
| `voice-messages` | Chat voice recordings | 10MB | No |

Path convention: `{bucket}/{user_id}/{filename}`

## Auth Configuration (Dashboard)

These settings should be configured in the Supabase Dashboard under **Authentication → Providers**:

1. **Email provider**: Enabled
   - Confirm email: **On**
   - Secure email change: **On**
2. **Magic link**: Enabled (patient signup flow)
3. **MFA (TOTP)**: Enabled (optional for clinicians)

### Custom JWT Claims

Add a `user_role` claim to the JWT via an auth hook (Dashboard → Auth → Hooks):

```sql
-- Function to add user_role to JWT
CREATE OR REPLACE FUNCTION custom_access_token_hook(event jsonb)
RETURNS jsonb AS $$
DECLARE
  claims jsonb;
  user_role text;
BEGIN
  claims := event->'claims';

  IF EXISTS (SELECT 1 FROM patients WHERE id = (event->>'user_id')::uuid) THEN
    user_role := 'patient';
  ELSIF EXISTS (SELECT 1 FROM clinicians WHERE id = (event->>'user_id')::uuid) THEN
    user_role := 'clinician';
  ELSE
    user_role := 'unknown';
  END IF;

  claims := jsonb_set(claims, '{user_role}', to_jsonb(user_role));
  event := jsonb_set(event, '{claims}', claims);
  RETURN event;
END;
$$ LANGUAGE plpgsql;
```

## Environment Variables

Add these to your `.env` file (see `.env.example`):

```bash
SUPABASE_URL=https://tsbjrzlzrejzlfkmhxpz.supabase.co
SUPABASE_ANON_KEY=<from dashboard → Settings → API>
SUPABASE_SERVICE_ROLE_KEY=<from dashboard → Settings → API>
```

## Verification

After running migrations, verify in the Supabase Dashboard:
1. **Table Editor** → all 16 tables visible
2. **Authentication → Policies** → RLS enabled on all tables
3. **Storage** → 3 buckets (documents, avatars, voice-messages)
4. **SQL Editor** → run: `SELECT count(*) FROM pg_policies WHERE schemaname = 'public';` → should return **56**
