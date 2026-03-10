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

---

## Running Migrations

Migrations live in `backend/src/app/db/migrations/` and must be run in order:

```bash
export DB_URL="postgresql://postgres:YOUR_PASSWORD@db.tsbjrzlzrejzlfkmhxpz.supabase.co:5432/postgres"

# 1. Schema: enums, tables, indexes, triggers
psql "$DB_URL" -f backend/src/app/db/migrations/001_initial_schema.sql

# 2. RLS: row-level security policies
psql "$DB_URL" -f backend/src/app/db/migrations/002_rls_policies.sql

# 3. Storage: buckets + storage RLS
psql "$DB_URL" -f backend/src/app/db/migrations/003_storage_and_auth.sql

# 4. JWT claims hook: adds user_role to every JWT
psql "$DB_URL" -f backend/src/app/db/migrations/004_jwt_claims_hook.sql
```

> [!IMPORTANT]
> These migrations are **idempotent-safe on first run only**. If re-running, you'll need to drop existing objects first or use the Supabase dashboard SQL editor to reset.

### Migration Index

| File | What it does |
|------|-------------|
| `001_initial_schema.sql` | 20 PostgreSQL enum types, 16 tables, indexes, constraints, `updated_at` trigger |
| `002_rls_policies.sql` | Enables RLS on all tables, creates 56 policies + 3 helper functions |
| `003_storage_and_auth.sql` | 3 storage buckets (documents, avatars, voice-messages) + 9 storage RLS policies |
| `004_jwt_claims_hook.sql` | Custom JWT hook — injects `user_role` claim into every token |

### Adding New Migrations

When you need to change the schema:
1. Create a new file: `005_descriptive_name.sql`
2. Always number sequentially — never reorder existing files
3. If adding a new enum value: `ALTER TYPE my_enum ADD VALUE 'new_value';`
4. If adding a new column: `ALTER TABLE my_table ADD COLUMN new_col type;`
5. Update this guide's migration index table

---

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

All PostgreSQL enum types mirror `backend/src/app/models/enums.py` 1:1. If you add a new value in Python, you must also run:

```sql
ALTER TYPE my_enum_name ADD VALUE 'new_value';
```

### RLS Model

- **Patients** see only their own data (`patient_id = auth.uid()`)
- **Clinicians** see only assigned patients (via `care_teams` junction where `status = 'active'`)
- **Service role** bypasses RLS (used by backend agents and cron jobs)
- Helper functions: `is_assigned_clinician(patient_id)`, `is_patient()`, `is_clinician()`

### Storage Buckets

| Bucket | Purpose | Max Size | Public |
|--------|---------|----------|--------|
| `documents` | Medical PDFs/images | 20MB | No |
| `avatars` | Profile photos | 2MB | Yes |
| `voice-messages` | Chat voice recordings | 10MB | No |

Path convention: `{bucket}/{user_id}/{filename}`

---

## Auth Configuration

### Dashboard Settings

Configure in Supabase Dashboard → **Authentication → Providers**:

| Setting | Value | Why |
|---------|-------|-----|
| Email provider | Enabled | Primary sign-in method |
| Confirm email | On | Verify email ownership |
| Secure email change | On | Requires old + new email confirmation |
| Secure password change | On | Forces re-auth before changing password |
| Min password length | 8 | Healthcare app — stricter than default |
| Password requirements | Letters and digits | Basic complexity |
| Email OTP expiration | 900s (15 min) | Shorter window for PHI security |
| MFA (TOTP) | Enabled | Optional for clinicians |

### JWT Claims Hook

Every JWT token includes a `user_role` claim (`"patient"` or `"clinician"`) so the frontend can determine which portal to show without an extra API call.

**How it works:** Migration `004_jwt_claims_hook.sql` creates a function that checks whether the user ID exists in the `patients` or `clinicians` table and injects the result into the JWT.

**Dashboard setup** (after running the migration):
1. Go to **Auth → Hooks**
2. Click **Add a new hook** → **Customize Access Token (JWT) Claims**
3. Enable the hook
4. Hook type: **Postgres**
5. Schema: **public**
6. Function: **custom_access_token_hook**
7. Click **Create hook**

The dashboard will automatically run the required permission grants (execute for `supabase_auth_admin`, revoke from `authenticated`/`anon`/`public`).

### Reading the Role in Code

**Backend (Python):**
```python
# The JWT payload will include: {"user_role": "patient"} or {"user_role": "clinician"}
role = jwt_payload.get("user_role")
```

**Frontend (TypeScript):**
```typescript
const { data: { session } } = await supabase.auth.getSession();
const role = session?.user?.app_metadata?.user_role;
// "patient" | "clinician" | "unknown"
```

---

## Environment Variables

Add these to your `.env` file (see `.env.example`):

```bash
SUPABASE_URL=https://tsbjrzlzrejzlfkmhxpz.supabase.co
SUPABASE_ANON_KEY=<from dashboard → Settings → API>
SUPABASE_SERVICE_ROLE_KEY=<from dashboard → Settings → API>
```

---

## Verification Checklist

After running all 4 migrations:

- [ ] **Table Editor** → all 16 tables visible
- [ ] **Auth → Policies** → RLS enabled on all tables
- [ ] **Storage** → 3 buckets (documents, avatars, voice-messages)
- [ ] **Auth → Hooks** → JWT claims hook active
- [ ] **SQL Editor** → `SELECT count(*) FROM pg_policies WHERE schemaname = 'public';` → **56**
