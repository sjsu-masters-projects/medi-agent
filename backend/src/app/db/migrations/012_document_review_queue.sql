-- Phase 6 PR 3: patient-upload review workflow
--
-- Adds shared clinician review state for patient-uploaded documents.
-- Review is intentionally non-blocking: documents remain stored/visible,
-- while clinicians can approve or reject them for workflow/audit purposes.

alter table if exists public.documents
    add column if not exists review_status text,
    add column if not exists reviewed_by uuid references public.clinicians(id),
    add column if not exists reviewed_at timestamptz,
    add column if not exists review_note text;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conname = 'documents_review_status_check'
    ) then
        alter table public.documents
            add constraint documents_review_status_check
            check (
                review_status is null
                or review_status in ('pending', 'approved', 'rejected')
            );
    end if;
end $$;

update public.documents
set review_status = 'pending'
where uploaded_by_role = 'patient'
  and review_status is null;

create index if not exists idx_documents_review_queue
    on public.documents (uploaded_by_role, review_status, created_at desc);

create index if not exists idx_documents_reviewed_by
    on public.documents (reviewed_by)
    where reviewed_by is not null;
