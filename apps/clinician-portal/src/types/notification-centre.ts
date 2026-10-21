export type NotificationCategory = "documents" | "care_plans" | "appointments" | "follow_up" | "safety" | "messages" | "reminders";

export interface CentreItem {
  id: string;
  event_type: string;
  category: NotificationCategory;
  title: string;
  body: string;
  created_at: string;
  is_read: boolean;
  action_url: string | null;
  action_label: string;
  actionable: boolean;
  can_acknowledge: boolean;
  patient_name?: string | null;
  clinic_name?: string | null;
  clinic_id?: string | null;
  source_label?: string | null;
  state_checked_at?: string | null;
}

export interface CentrePage {
  items: CentreItem[];
  next_cursor: string | null;
  read_through: string | null;
  /** Local cache retains the server snapshot for each loaded page. */
  read_snapshots?: string[];
}

export interface CentreSummary {
  unread_count: number;
  action_item_count: number;
}
