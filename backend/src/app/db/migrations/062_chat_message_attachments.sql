-- AI-005: server-built attachments on chat messages, starting with document results.
--
-- When Nora's reply cites one of the patient's documents that has extracted test results,
-- the server snapshots those results (the same rows Records shows) onto the reply, so the
-- patient sees them as a clear card instead of only as prose. The values come from the
-- source-checked document facts, never from the model's text. Existing messages keep an
-- empty list. Additive; the backend tolerates the column's absence until this is applied.

ALTER TABLE public.chat_messages
  ADD COLUMN attachments jsonb NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(attachments) = 'array' AND jsonb_array_length(attachments) <= 5);
