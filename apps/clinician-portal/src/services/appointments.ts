import { api } from "@/services/api";
import type { Appointment } from "@/types";

export interface AssignedSchedulingPatient {
  id: string;
  first_name: string;
  last_name: string;
  care_team_id: string;
  clinic_id?: string | null;
  clinic_name?: string | null;
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
  clinic_id?: string | null;
  clinic_name?: string | null;
  proposal_group_id?: string | null;
  proposal_expires_at?: string | null;
  patient_note?: string | null;
  location?: string | null;
  reason?: string | null;
  notes?: string | null;
  cancelled_by?: "patient" | "clinician" | null;
  cancel_reason_code?: Appointment["cancelReasonCode"] | null;
  cancel_reason?: string | null;
  cancelled_at?: string | null;
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
    clinicId: row.clinic_id ?? undefined,
    clinicName: row.clinic_name ?? undefined,
    proposalGroupId: row.proposal_group_id ?? undefined,
    proposalExpiresAt: row.proposal_expires_at ?? undefined,
    patientNote: row.patient_note ?? undefined,
    location: row.location ?? undefined,
    reason: row.reason ?? undefined,
    notes: row.notes ?? undefined,
    cancelledBy: row.cancelled_by ?? undefined,
    cancelReasonCode: row.cancel_reason_code ?? undefined,
    cancelReason: row.cancel_reason ?? undefined,
    cancelledAt: row.cancelled_at ?? undefined,
  };
}

export type CancelReasonCode = NonNullable<Appointment["cancelReasonCode"]>;

export interface VisitDetailsPatch {
  appointment_type?: Appointment["appointmentType"];
  location?: string;
  reason?: string;
  notes?: string;
}

/** Change a visit's type, location, reason or notes. A booked visit's time is never changed here. */
export async function updateVisitDetails(token: string, id: string, patch: VisitDetailsPatch) {
  return mapAppointment(
    await api.put<AppointmentRecord>(`/api/v1/appointments/${encodeURIComponent(id)}`, patch, { token }),
  );
}

export async function cancelVisit(
  token: string,
  id: string,
  body: { reason_code: CancelReasonCode; reason?: string },
) {
  return mapAppointment(
    await api.post<AppointmentRecord>(`/api/v1/appointments/${encodeURIComponent(id)}/cancel`, body, { token }),
  );
}

export async function completeVisit(token: string, id: string) {
  return mapAppointment(
    await api.post<AppointmentRecord>(`/api/v1/appointments/${encodeURIComponent(id)}/complete`, {}, { token }),
  );
}

export async function markVisitNoShow(token: string, id: string) {
  return mapAppointment(
    await api.post<AppointmentRecord>(`/api/v1/appointments/${encodeURIComponent(id)}/no-show`, {}, { token }),
  );
}

export function fetchSchedulingPatients(token: string, clinicId?: string | null) {
  return api.get<AssignedSchedulingPatient[]>(
    `/api/v1/clinicians/me/patients${clinicId ? `?clinic_id=${encodeURIComponent(clinicId)}` : ""}`,
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
  clinicId?: string | null,
): Promise<Appointment[]> {
  const clinic = clinicId ? `?clinic_id=${encodeURIComponent(clinicId)}` : "";
  const rows = await api.get<AppointmentRecord[]>(`/api/v1/appointments/${clinic}`, {
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

/** A visit on the clinician's own schedule (patient name and timezone come with it). */
export interface ScheduleVisit extends Appointment {
  patientName?: string;
  patientTimezone?: string;
}

export type NeedsActionKind = "awaiting_reply" | "change_request" | "expired";

export interface NeedsActionItem {
  kind: NeedsActionKind;
  appointmentId: string;
  proposalGroupId?: string;
  patientId: string;
  patientName?: string;
  clinicId?: string;
  clinicName?: string;
  slotCount: number;
  firstSlotAt: string;
  expiresAt?: string;
  expiringSoon: boolean;
}

export interface MySchedule {
  visits: ScheduleVisit[];
  needsAction: NeedsActionItem[];
  nextVisit: ScheduleVisit | null;
}

export interface BusyInterval {
  startsAt: string;
  endsAt: string;
  clinicId?: string;
  clinicName?: string;
}

type ScheduleVisitRecord = AppointmentRecord & {
  patient_name?: string | null;
  patient_timezone?: string | null;
};

function mapVisit(row: ScheduleVisitRecord): ScheduleVisit {
  return {
    ...mapAppointment(row),
    patientName: row.patient_name ?? undefined,
    patientTimezone: row.patient_timezone ?? undefined,
  };
}

/** The caller's own visits in [from, to), what needs action, and the next visit. */
export async function fetchMySchedule(
  token: string,
  from: string,
  to: string,
  clinicId?: string | null,
  includeCancelled = false,
): Promise<MySchedule> {
  const query = new URLSearchParams({ from, to });
  if (clinicId) query.set("clinic_id", clinicId);
  if (includeCancelled) query.set("include_cancelled", "true");
  const body = await api.get<{
    visits: ScheduleVisitRecord[];
    needs_action: {
      kind: NeedsActionKind;
      appointment_id: string;
      proposal_group_id?: string | null;
      patient_id: string;
      patient_name?: string | null;
      clinic_id?: string | null;
      clinic_name?: string | null;
      slot_count: number;
      first_slot_at: string;
      expires_at?: string | null;
      expiring_soon: boolean;
    }[];
    next_visit?: ScheduleVisitRecord | null;
  }>(`/api/v1/appointments/schedule?${query}`, { token });
  return {
    visits: body.visits.map(mapVisit),
    needsAction: body.needs_action.map((item) => ({
      kind: item.kind,
      appointmentId: item.appointment_id,
      proposalGroupId: item.proposal_group_id ?? undefined,
      patientId: item.patient_id,
      patientName: item.patient_name ?? undefined,
      clinicId: item.clinic_id ?? undefined,
      clinicName: item.clinic_name ?? undefined,
      slotCount: item.slot_count,
      firstSlotAt: item.first_slot_at,
      expiresAt: item.expires_at ?? undefined,
      expiringSoon: item.expiring_soon,
    })),
    nextVisit: body.next_visit ? mapVisit(body.next_visit) : null,
  };
}

/** The caller's own booked intervals in [from, to) at every clinic: times and clinics only. */
export async function fetchBusyTimes(
  token: string,
  from: string,
  to: string,
): Promise<BusyInterval[]> {
  const query = new URLSearchParams({ from, to });
  const rows = await api.get<
    { starts_at: string; ends_at: string; clinic_id?: string | null; clinic_name?: string | null }[]
  >(`/api/v1/appointments/busy?${query}`, { token });
  return rows.map((row) => ({
    startsAt: row.starts_at,
    endsAt: row.ends_at,
    clinicId: row.clinic_id ?? undefined,
    clinicName: row.clinic_name ?? undefined,
  }));
}

/** One patient's visits and offers that the access rule lets the caller see. */
export async function fetchPatientAppointments(
  token: string,
  patientId: string,
): Promise<Appointment[]> {
  const rows = await api.get<AppointmentRecord[]>(
    `/api/v1/appointments/?patient_id=${encodeURIComponent(patientId)}`,
    { token },
  );
  return rows.map(mapAppointment);
}
