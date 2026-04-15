-- Align care_teams schema with invite-code workflow used by services.

-- Add the 'pending' lifecycle state if missing.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_type t
        JOIN pg_enum e ON t.oid = e.enumtypid
        WHERE t.typname = 'care_team_status_enum'
          AND e.enumlabel = 'pending'
    ) THEN
        ALTER TYPE care_team_status_enum ADD VALUE 'pending';
    END IF;
END $$;

-- Pending invites are created before a patient is known.
ALTER TABLE care_teams
    ALTER COLUMN patient_id DROP NOT NULL;

-- Invite workflow fields.
ALTER TABLE care_teams
    ADD COLUMN IF NOT EXISTS invite_code text,
    ADD COLUMN IF NOT EXISTS invite_expires_at timestamptz,
    ADD COLUMN IF NOT EXISTS invite_claimed_at timestamptz;

-- Enforce one active invite code value at a time.
CREATE UNIQUE INDEX IF NOT EXISTS uq_care_teams_invite_code
    ON care_teams (invite_code)
    WHERE invite_code IS NOT NULL;

-- Support pending-invite lookups without enum-cast predicates (must be immutable).
CREATE INDEX IF NOT EXISTS idx_care_teams_pending_invites
    ON care_teams (status, invite_code)
    WHERE invite_code IS NOT NULL;
