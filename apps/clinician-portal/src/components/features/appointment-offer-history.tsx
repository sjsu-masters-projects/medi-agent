import { Badge, Button, Card, EmptyState } from "@/components/ui";
import { AppointmentStatus, type Appointment } from "@/types";
import { formatSchedulingTime } from "@/utils/appointment-times";
import { CalendarExportButton } from "./calendar-export-button";

const LABELS: Record<Appointment["status"], string> = {
  scheduled: "Scheduled",
  proposed: "Awaiting patient response",
  confirmed: "Confirmed",
  declined: "Declined",
  alternative_requested: "Different times requested",
  withdrawn: "Withdrawn",
  expired: "Expired",
  cancelled: "Cancelled",
  completed: "Completed",
  no_show: "No-show",
};

export function groupAppointmentHistory(appointments: Appointment[]) {
  const groups = new Map<string, Appointment[]>();
  for (const visit of appointments) {
    const key = visit.proposalGroupId ?? visit.id;
    groups.set(key, [...(groups.get(key) ?? []), visit]);
  }
  return [...groups.values()]
    .map((rows) =>
      rows.sort(
        (a, b) => Date.parse(a.scheduledAt) - Date.parse(b.scheduledAt),
      ),
    )
    .sort((a, b) => Date.parse(b[0]!.createdAt) - Date.parse(a[0]!.createdAt));
}

export function AppointmentOfferHistory({
  appointments,
  timezone,
  disabled,
  onRepropose,
  token,
}: {
  token?: string | null;
  appointments: Appointment[];
  timezone: string;
  disabled: boolean;
  onRepropose: (appointment: Appointment) => void;
}) {
  if (!appointments.length)
    return (
      <EmptyState
        title="No appointments yet"
        description="Send appointment options to this patient to begin."
      />
    );
  return (
    <div className="space-y-4" aria-label="Appointment history">
      {groupAppointmentHistory(appointments).map((rows) => {
        const representative =
          rows.find(
            (row) =>
              row.status === AppointmentStatus.CONFIRMED ||
              row.status === AppointmentStatus.SCHEDULED,
          ) ??
          rows.find((row) => row.status === AppointmentStatus.PROPOSED) ??
          rows.find((row) => row.status !== AppointmentStatus.WITHDRAWN) ??
          rows[0]!;
        const note = rows.find((row) => row.patientNote)?.patientNote;
        const canRepropose =
          representative.status === AppointmentStatus.DECLINED ||
          representative.status === AppointmentStatus.ALTERNATIVE_REQUESTED ||
          rows.every(
            (row) =>
              row.status === AppointmentStatus.EXPIRED ||
              row.status === AppointmentStatus.WITHDRAWN,
          );
        return (
          <Card key={representative.proposalGroupId ?? representative.id}>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="font-semibold text-gray-900">
                {representative.reason ||
                  (representative.proposalGroupId
                    ? "Appointment offer"
                    : "Appointment")}
              </h3>
              <Badge
                variant={
                  representative.status === AppointmentStatus.CONFIRMED
                    ? "success"
                    : "info"
                }
              >
                {LABELS[representative.status]}
              </Badge>
            </div>
            <p className="mt-2 text-sm text-gray-600">
              {representative.durationMinutes} minutes
              {representative.location ? ` · ${representative.location}` : ""}
            </p>
            <ul className="mt-3 space-y-2 text-sm text-gray-700">
              {rows.map((row) => (
                <li key={row.id}>
                  {formatSchedulingTime(row.scheduledAt, timezone)} · {timezone}{" "}
                  — {LABELS[row.status]}
                  {(row.status === AppointmentStatus.CONFIRMED ||
                    row.status === AppointmentStatus.SCHEDULED) && (
                    <CalendarExportButton
                      token={token}
                      appointmentId={row.id}
                      locale="en-US"
                      disabled={disabled}
                    />
                  )}
                  {row.status === AppointmentStatus.PROPOSED &&
                    row.proposalExpiresAt && (
                      <span className="block text-xs text-gray-500">
                        Available until{" "}
                        {formatSchedulingTime(row.proposalExpiresAt, timezone)}{" "}
                        · {timezone}
                      </span>
                    )}
                </li>
              ))}
            </ul>
            {note && (
              <p className="mt-3 whitespace-pre-wrap text-sm text-gray-700">
                <strong>Patient note:</strong> {note}
              </p>
            )}
            {canRepropose && (
              <Button
                className="mt-4"
                disabled={disabled}
                variant="secondary"
                onClick={() => onRepropose(representative)}
              >
                Offer new times
              </Button>
            )}
          </Card>
        );
      })}
    </div>
  );
}
