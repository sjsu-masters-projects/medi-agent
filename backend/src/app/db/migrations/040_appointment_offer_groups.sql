-- Add grouped offers before the transactional functions in 041 consume withdrawn.
-- Apply 039, 040 and 041 before deploying grouped-offer writes.
ALTER TYPE appointment_status_enum ADD VALUE IF NOT EXISTS 'withdrawn';
ALTER TABLE public.appointments ADD COLUMN IF NOT EXISTS proposal_group_id uuid;
CREATE INDEX IF NOT EXISTS idx_appointment_proposal_group
  ON public.appointments(proposal_group_id) WHERE proposal_group_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_appointment_group_confirmation
  ON public.appointments(proposal_group_id)
  WHERE proposal_group_id IS NOT NULL AND status = 'confirmed';

-- Direct portal writes cannot bypass the backend's atomic grouped-offer workflow.
CREATE POLICY appointments_group_insert_backend_only ON public.appointments
  AS RESTRICTIVE FOR INSERT TO authenticated
  WITH CHECK (proposal_group_id IS NULL);
CREATE POLICY appointments_group_update_backend_only ON public.appointments
  AS RESTRICTIVE FOR UPDATE TO authenticated
  USING (proposal_group_id IS NULL) WITH CHECK (proposal_group_id IS NULL);
