export interface ConversationRecipient {
  id: string;
  name: string;
  role: string;
  clinic_name: string;
}

export interface CareConversation {
  id: string;
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
}

export interface ConversationMessagePage {
  items: CareConversationMessage[];
  next_cursor: string | null;
}

export interface ConversationDraft {
  body: string;
  clientMessageId?: string;
  failure?: "uncertain" | "mismatch" | "invalid";
}
