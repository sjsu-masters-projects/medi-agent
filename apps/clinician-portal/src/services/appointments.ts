import { api } from "@/services/api";
import type { Appointment } from "@/types";

export interface AssignedSchedulingPatient {
  id: string;
  first_name: string;
  last_name: string;
  care_team_id: string;
}

export interface AppointmentOfferDraft {
  care_team_id: string;
  slots: string[];
  duration_minutes: number;
  appointment_type: Appointment["appointmentType"];
  location?: string;
  reason?: string;
}

interface AppointmentRecord {
  id: string;
  patient_id: string;
  care_team_id: string;
  scheduled_at: string;
  duration_minutes: number;
  appointment_type: Appointment["appointmentType"];
  status: Appointment["status"];
  created_at: string;
  clinician_name?: string | null;
  proposal_group_id?: string | null;
  proposal_expires_at?: string | null;
  patient_note?: string | null;
  location?: string | null;
  reason?: string | null;
}

function mapAppointment(row: AppointmentRecord): Appointment {
  return {
    id: row.id,
    patientId: row.patient_id,
    careTeamId: row.care_team_id,
    scheduledAt: row.scheduled_at,
    durationMinutes: row.duration_minutes,
    appointmentType: row.appointment_type,
    status: row.status,
    createdAt: row.created_at,
    clinicianName: row.clinician_name ?? undefined,
    proposalGroupId: row.proposal_group_id ?? undefined,
    proposalExpiresAt: row.proposal_expires_at ?? undefined,
    patientNote: row.patient_note ?? undefined,
    location: row.location ?? undefined,
    reason: row.reason ?? undefined,
  };
}

export function fetchSchedulingPatients(token: string) {
  return api.get<AssignedSchedulingPatient[]>(
    "/api/v1/clinicians/me/patients",
    { token },
  );
}

export function fetchSchedulingProfile(token: string, patientId: string) {
  return api.get<{ timezone?: string | null }>(
    `/api/v1/clinicians/me/patients/${encodeURIComponent(patientId)}`,
    { token },
  );
}

export async function fetchSchedulingAppointments(
  token: string,
): Promise<Appointment[]> {
  const rows = await api.get<AppointmentRecord[]>("/api/v1/appointments/", {
    token,
  });
  return rows.map(mapAppointment);
}

export async function proposeAppointmentOffer(
  token: string,
  draft: AppointmentOfferDraft,
) {
  const rows = await api.post<AppointmentRecord[]>(
    "/api/v1/appointments/propose",
    draft,
    { token },
  );
  return rows.map(mapAppointment);
}
