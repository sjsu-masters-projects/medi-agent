import { useEffect } from "react";
import { Badge, Button } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { AppointmentStatus, type Appointment } from "@/types";
import { formatSchedulingTime } from "@/utils/appointment-times";
import { ClinicChip } from "./clinic-chip";
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

const TONES: Record<
  Appointment["status"],
  "success" | "info" | "warning" | "danger" | "neutral"
> = {
  scheduled: "success",
  proposed: "info",
  confirmed: "success",
  declined: "warning",
  alternative_requested: "warning",
  withdrawn: "neutral",
  expired: "neutral",
  cancelled: "neutral",
  completed: "success",
  no_show: "danger",
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
  appointmentId,
  patientName,
  showClinic = false,
}: {
  patientName?: string;
  showClinic?: boolean;
  token?: string | null;
  appointmentId?: string | null;
  appointments: Appointment[];
  timezone: string;
  disabled: boolean;
  onRepropose: (appointment: Appointment) => void;
}) {
  useEffect(() => {
    if (appointmentId && appointments.some((visit) => visit.id === appointmentId)) {
      const target = document.getElementById(`appointment-${appointmentId}`);
      target?.scrollIntoView?.({ block: "center" });
      target?.focus({ preventScroll: true });
    }
  }, [appointmentId, appointments]);
  if (!appointments.length)
    return (
      <div className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
        <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-muted">
          <Icon name="cal" className="h-6 w-6" />
        </span>
        <div className="max-w-[48ch] space-y-1">
          <h3 className="text-[15px] font-semibold text-ink">
            No appointments yet
          </h3>
          <p className="text-sm leading-relaxed text-muted">
            Send appointment options to this patient to begin.
          </p>
        </div>
      </div>
    );
  return (
    <ul className="divide-y divide-line" aria-label="Appointment history">
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
          <li
            key={representative.proposalGroupId ?? representative.id}
            className="px-5 py-4 transition-colors hover:bg-[rgba(100,116,139,.05)]"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <h3 className="text-sm font-semibold text-ink">
                  {representative.reason ||
                    (representative.proposalGroupId
                      ? "Appointment offer"
                      : "Appointment")}
                </h3>
                <p className="mt-0.5 text-[13px] text-muted">
                  <span className="font-mono">
                    {representative.durationMinutes}
                  </span>{" "}
                  minutes
                  {representative.location
                    ? ` · ${representative.location}`
                    : ""}
                </p>
              </div>
              <Badge variant={TONES[representative.status]} className="shrink-0">
                {LABELS[representative.status]}
              </Badge>
            </div>
            <ul className="mt-3 space-y-2 text-[13px] text-ink-2">
              {rows.map((row) => (
                <li
                  key={row.id}
                  id={`appointment-${row.id}`}
                  tabIndex={row.id === appointmentId ? -1 : undefined}
                  className={`scroll-mt-6 rounded-[10px] bg-surface-2 px-3 py-2 ${row.id === appointmentId ? "ring-2 ring-primary" : ""}`}
                >
                  <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                    <span className="order-1 min-w-0 flex-1 break-words sm:flex-none">
                      <span className="font-mono text-[12.5px] font-semibold text-ink">
                        {formatSchedulingTime(row.scheduledAt, timezone)}
                      </span>{" "}
                      <span className="text-muted">· {timezone}</span>
                    </span>
                    {(patientName || (showClinic && row.clinicName)) && (
                      <span className="order-3 flex min-w-0 basis-full items-center gap-2 sm:order-2 sm:basis-auto">
                        {patientName && (
                          <span className="min-w-0 break-words text-ink-2">
                            {patientName}
                          </span>
                        )}
                        {showClinic && <ClinicChip name={row.clinicName} />}
                      </span>
                    )}
                    <Badge
                      variant={TONES[row.status]}
                      className="order-2 shrink-0 sm:order-3"
                    >
                      {LABELS[row.status]}
                    </Badge>
                  </span>
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
                      <span className="mt-0.5 block font-mono text-[11px] text-muted">
                        Available until{" "}
                        {formatSchedulingTime(row.proposalExpiresAt, timezone)}{" "}
                        · {timezone}
                      </span>
                    )}
                </li>
              ))}
            </ul>
            {note && (
              <p className="mt-3 whitespace-pre-wrap rounded-[10px] border border-line px-3 py-2 text-[13px] text-ink-2">
                <strong className="font-semibold text-ink">Patient note:</strong>{" "}
                {note}
              </p>
            )}
            {canRepropose && (
              <Button
                className="mt-3"
                size="sm"
                disabled={disabled}
                variant="secondary"
                onClick={() => onRepropose(representative)}
              >
                Offer new times
              </Button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
