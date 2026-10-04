/**
 * Appointments API client — fetch a patient's visits and respond to proposals.
 */

import { api } from "@/services/api";
import type { Appointment, AppointmentStatus } from "@/types";

export type AppointmentResponseAction =
  | "accept"
  | "decline"
  | "request_alternative"
  | "cancel";

interface AppointmentApiRecord {
  id: string;
  patient_id: string;
  care_team_id: string;
  clinician_name?: string | null;
  scheduled_at: string;
  duration_minutes: number;
  appointment_type: Appointment["appointmentType"];
  location?: string | null;
  reason?: string | null;
  notes?: string | null;
  status: AppointmentStatus;
  patient_note?: string | null;
  proposal_group_id?: string | null;
  proposal_expires_at?: string | null;
  source_document_id?: string | null;
  created_at: string;
}

function mapAppointment(record: AppointmentApiRecord): Appointment {
  return {
    id: record.id,
    patientId: record.patient_id,
    careTeamId: record.care_team_id,
    clinicianName: record.clinician_name ?? undefined,
    scheduledAt: record.scheduled_at,
    durationMinutes: record.duration_minutes,
    appointmentType: record.appointment_type,
    location: record.location ?? undefined,
    reason: record.reason ?? undefined,
    notes: record.notes ?? undefined,
    status: record.status,
    patientNote: record.patient_note ?? undefined,
    proposalGroupId: record.proposal_group_id ?? undefined,
    proposalExpiresAt: record.proposal_expires_at ?? undefined,
    sourceDocumentId: record.source_document_id ?? undefined,
    createdAt: record.created_at,
  };
}

export async function fetchVisits(token: string): Promise<Appointment[]> {
  const records = await api.get<AppointmentApiRecord[]>(
    "/api/v1/appointments/",
    {
      token,
    },
  );
  return records.map(mapAppointment);
}

export async function respondToVisit(
  appointmentId: string,
  action: AppointmentResponseAction,
  token: string,
  note?: string,
): Promise<Appointment> {
  const trimmed = note?.trim();
  const record = await api.post<AppointmentApiRecord>(
    `/api/v1/appointments/${appointmentId}/respond`,
    trimmed ? { action, note: trimmed } : { action },
    { token },
  );
  return mapAppointment(record);
}

/** Mirror the atomic response for every slot already loaded in this offer. */
export function applyAppointmentResponse(
  visits: Appointment[],
  updated: Appointment,
  action: AppointmentResponseAction,
): Appointment[] {
  return visits.map((visit) => {
    if (visit.id === updated.id) return updated;
    if (
      action === "cancel" ||
      !updated.proposalGroupId ||
      visit.proposalGroupId !== updated.proposalGroupId ||
      visit.status !== "proposed"
    )
      return visit;
    return {
      ...visit,
      status: action === "accept" ? "withdrawn" : updated.status,
      patientNote: updated.patientNote ?? visit.patientNote,
    };
  });
}
