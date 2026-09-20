-- Derived previews make browser-unsupported clinical source formats viewable without
-- replacing the immutable original artifact.

ALTER TABLE public.documents
  ADD COLUMN IF NOT EXISTS preview_path text,
  ADD COLUMN IF NOT EXISTS preview_mime_type text,
  ADD COLUMN IF NOT EXISTS preview_status text NOT NULL DEFAULT 'not_required',
  ADD COLUMN IF NOT EXISTS preview_failure_code text;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'documents_preview_status_check'
      AND conrelid = 'public.documents'::regclass
  ) THEN
    ALTER TABLE public.documents
      ADD CONSTRAINT documents_preview_status_check
      CHECK (preview_status IN ('not_required', 'pending', 'ready', 'failed'));
  END IF;
END
$$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'documents_preview_shape_check'
      AND conrelid = 'public.documents'::regclass
  ) THEN
    ALTER TABLE public.documents
      ADD CONSTRAINT documents_preview_shape_check
      CHECK (
        (preview_status = 'ready' AND preview_path IS NOT NULL AND preview_mime_type = 'application/pdf')
        OR (preview_status <> 'ready' AND preview_path IS NULL AND preview_mime_type IS NULL)
      );
  END IF;
END
$$;

UPDATE public.documents
SET preview_status = 'pending'
WHERE mime_type = 'image/tiff'
  AND file_path IS NOT NULL
  AND preview_status = 'not_required';
