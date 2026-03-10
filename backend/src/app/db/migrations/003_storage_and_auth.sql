-- ============================================================
-- MediAgent — 003 Storage Buckets
-- Creates Supabase Storage buckets and their RLS policies.
-- ============================================================

-- ════════════════════════════════════════════════════
-- STORAGE BUCKETS
-- ════════════════════════════════════════════════════

-- Medical documents (PDFs, images)
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'documents',
  'documents',
  false,
  20971520,  -- 20MB
  ARRAY['application/pdf', 'image/png', 'image/jpeg', 'image/webp', 'image/tiff']
);

-- Profile photos
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'avatars',
  'avatars',
  true,  -- publicly readable (profile pics)
  2097152,  -- 2MB
  ARRAY['image/png', 'image/jpeg', 'image/webp']
);

-- Voice messages from chat
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'voice-messages',
  'voice-messages',
  false,
  10485760,  -- 10MB
  ARRAY['audio/webm', 'audio/mp4', 'audio/ogg', 'audio/wav']
);


-- ════════════════════════════════════════════════════
-- STORAGE RLS POLICIES
-- ════════════════════════════════════════════════════

-- ── Documents bucket ──────────────────────────────
-- Path convention: documents/{patient_id}/{filename}

-- Patient uploads to their own folder
CREATE POLICY documents_upload ON storage.objects
  FOR INSERT
  WITH CHECK (
    bucket_id = 'documents'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- Patient reads own documents
CREATE POLICY documents_read_own ON storage.objects
  FOR SELECT
  USING (
    bucket_id = 'documents'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- Clinician reads assigned patients' documents
CREATE POLICY documents_read_clinician ON storage.objects
  FOR SELECT
  USING (
    bucket_id = 'documents'
    AND is_assigned_clinician((storage.foldername(name))[1]::uuid)
  );

-- Clinician uploads to assigned patients' folders
CREATE POLICY documents_upload_clinician ON storage.objects
  FOR INSERT
  WITH CHECK (
    bucket_id = 'documents'
    AND is_assigned_clinician((storage.foldername(name))[1]::uuid)
  );


-- ── Avatars bucket ────────────────────────────────
-- Path convention: avatars/{user_id}/{filename}

-- Any authenticated user can upload their own avatar
CREATE POLICY avatars_upload ON storage.objects
  FOR INSERT
  WITH CHECK (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- Any authenticated user can update their own avatar
CREATE POLICY avatars_update ON storage.objects
  FOR UPDATE
  USING (
    bucket_id = 'avatars'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- Avatars are publicly readable (bucket is public)

-- ── Voice messages bucket ─────────────────────────
-- Path convention: voice-messages/{patient_id}/{filename}

-- Patient uploads voice messages
CREATE POLICY voice_upload ON storage.objects
  FOR INSERT
  WITH CHECK (
    bucket_id = 'voice-messages'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- Patient reads own voice messages
CREATE POLICY voice_read_own ON storage.objects
  FOR SELECT
  USING (
    bucket_id = 'voice-messages'
    AND (storage.foldername(name))[1] = auth.uid()::text
  );

-- Clinician reads assigned patients' voice messages
CREATE POLICY voice_read_clinician ON storage.objects
  FOR SELECT
  USING (
    bucket_id = 'voice-messages'
    AND is_assigned_clinician((storage.foldername(name))[1]::uuid)
  );
