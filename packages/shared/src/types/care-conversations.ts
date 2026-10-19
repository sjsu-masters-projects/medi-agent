export interface ConversationRecipient {
  id: string;
  clinic_id?: string | null;
  name: string;
  role: string;
  clinic_name: string;
}

export interface CareConversation {
  id: string;
  clinic_id?: string | null;
  patient_id: string;
  clinician_id: string;
  patient_name: string;
  clinician_name: string;
  clinic_name: string;
  last_message_at: string | null;
  last_message_preview: string | null;
  unread_count: number;
  writable: boolean;
}

export interface CareConversationMessage {
  id: string;
  conversation_id: string;
  sender_id: string;
  sender_role: string;
  sender_name: string;
  body: string;
  created_at: string;
  /** LOC-003: stored translation text, if available. */
  translation?: string | null;
  /** LOC-003: target locale of the translation. */
  translation_locale?: string | null;
  /** LOC-003: whether the LOC-001 guard passed (numbers/names preserved). */
  translation_guard_passed?: boolean | null;
  /** True while the viewer needs a translation that is not stored yet (a read never calls the model). */
  translation_pending?: boolean;
  activity_context?: ConversationActivity | null;
}

export interface ConversationActivity {
  item_id: string;
  plan_id: string;
  title: string;
  frequency: string;
  current: boolean;
  wording?: Record<string, { title: string; frequency: string }>;
}

/** The answer of POST .../messages/{id}/translation. */
export interface MessageTranslationResult {
  message_id: string;
  translation: string | null;
  translation_locale: string | null;
  translation_guard_passed: boolean | null;
  translation_pending: boolean;
}

export interface ConversationMessagePage {
  items: CareConversationMessage[];
  next_cursor: string | null;
}

export interface ConversationDraft {
  body: string;
  carePlanItemId?: string;
  clientMessageId?: string;
  failure?: "uncertain" | "mismatch" | "invalid" | "activityUnavailable";
}
