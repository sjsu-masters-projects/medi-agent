import { api } from "@/services/api";
import { AppointmentStatus, AppointmentType, type Appointment } from "@/types";

/** Wire shape returned by `GET /api/v1/appointments/`. */
export interface AppointmentApiRecord {
    id: string;
    patient_id: string;
    care_team_id: string;
    clinician_name?: string | null;
    scheduled_at: string;
    duration_minutes?: number;
    appointment_type: AppointmentType;
    location?: string | null;
    reason?: string | null;
    notes?: string | null;
    status: AppointmentStatus;
    source_document_id?: string | null;
    created_at: string;
}

export function mapAppointment(record: AppointmentApiRecord): Appointment {
    return {
        id: record.id,
        patientId: record.patient_id,
        careTeamId: record.care_team_id,
        clinicianName: record.clinician_name ?? undefined,
        scheduledAt: record.scheduled_at,
        durationMinutes: record.duration_minutes ?? 30,
        appointmentType: record.appointment_type,
        location: record.location ?? undefined,
        reason: record.reason ?? undefined,
        notes: record.notes ?? undefined,
        status: record.status,
        sourceDocumentId: record.source_document_id ?? undefined,
        createdAt: record.created_at,
    };
}

/**
 * Fetch this patient's appointments.
 *
 * The backend already scopes the query to the authenticated patient, so no
 * patient identifier is sent from the browser.
 */
export async function fetchAppointments(token: string): Promise<Appointment[]> {
    const records = await api.get<AppointmentApiRecord[]>("/api/v1/appointments/", { token });
    return (records ?? []).map(mapAppointment);
}

/** Upcoming visits first; past visits after, most recent first. */
export function sortAppointmentsForDisplay(appointments: Appointment[]): Appointment[] {
    const now = Date.now();
    const isUpcoming = (appointment: Appointment) =>
        new Date(appointment.scheduledAt).getTime() >= now;

    return [...appointments].sort((left, right) => {
        const leftTime = new Date(left.scheduledAt).getTime();
        const rightTime = new Date(right.scheduledAt).getTime();
        const leftUpcoming = isUpcoming(left);

        if (leftUpcoming !== isUpcoming(right)) {
            return leftUpcoming ? -1 : 1;
        }
        return leftUpcoming ? leftTime - rightTime : rightTime - leftTime;
    });
}

export function isUpcomingAppointment(appointment: Appointment): boolean {
    return (
        appointment.status === AppointmentStatus.SCHEDULED
        && new Date(appointment.scheduledAt).getTime() >= Date.now()
    );
}

const APPOINTMENT_TYPE_LABELS: Record<AppointmentType, string> = {
    [AppointmentType.FOLLOW_UP]: "Follow-up",
    [AppointmentType.INITIAL]: "First visit",
    [AppointmentType.ROUTINE]: "Routine check",
    [AppointmentType.URGENT]: "Urgent",
    [AppointmentType.PRE_OP]: "Pre-operative",
};

export function formatAppointmentType(type: AppointmentType): string {
    return APPOINTMENT_TYPE_LABELS[type] ?? "Visit";
}

const APPOINTMENT_STATUS_LABELS: Record<AppointmentStatus, string> = {
    [AppointmentStatus.SCHEDULED]: "Scheduled",
    [AppointmentStatus.COMPLETED]: "Completed",
    [AppointmentStatus.CANCELLED]: "Cancelled",
    [AppointmentStatus.NO_SHOW]: "Missed",
};

export function formatAppointmentStatus(status: AppointmentStatus): string {
    return APPOINTMENT_STATUS_LABELS[status] ?? "Scheduled";
}

export function formatAppointmentDate(scheduledAt: string): string {
    const value = new Date(scheduledAt);
    if (Number.isNaN(value.getTime())) {
        return "Date unavailable";
    }
    return value.toLocaleDateString(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
        year: "numeric",
    });
}

export function formatAppointmentTime(scheduledAt: string, durationMinutes: number): string {
    const start = new Date(scheduledAt);
    if (Number.isNaN(start.getTime())) {
        return "";
    }
    const startLabel = start.toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
    });
    return `${startLabel} • ${durationMinutes} min`;
}
