export interface PatientNotification {
  id: string;
  event_type: string;
  category: string;
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
}

export interface NotificationPage {
  items: PatientNotification[];
  next_cursor: string | null;
  read_through: string | null;
}

export interface NotificationSummary {
  unread_count: number;
  action_item_count: number;
}
