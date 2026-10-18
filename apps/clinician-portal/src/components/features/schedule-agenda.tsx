"use client";

import { Badge } from "@/components/ui";
import type { ScheduleVisit } from "@/services/appointments";
import { groupByDay, visitTimeLabel, visitZoneNote } from "@/utils/schedule";
import { ClinicChip } from "./clinic-chip";
import { STATUS_LABELS, STATUS_TONES } from "./appointment-offer-history";

export const TYPE_LABELS: Record<ScheduleVisit["appointmentType"], string> = {
  follow_up: "Follow-up",
  initial: "Initial",
  routine: "Routine",
  urgent: "Urgent",
  pre_op: "Pre-op",
};

/** Visits grouped by day under sticky day headers; the whole row opens the visit. */
export function ScheduleAgenda({
  visits,
  showClinic,
  onOpen,
  now,
}: {
  visits: ScheduleVisit[];
  showClinic: boolean;
  onOpen: (visit: ScheduleVisit) => void;
  now: Date;
}) {
  return (
    <div className="space-y-4" aria-label="Agenda">
      {groupByDay(visits, now).map((day) => (
        <section aria-labelledby={`agenda-day-${day.key}`} key={day.key}>
          <h2
            className={`sticky top-0 z-10 -mx-1 bg-background/95 px-1 py-2 text-[13px] font-semibold backdrop-blur ${day.isToday ? "text-primary" : "text-ink-2"}`}
            id={`agenda-day-${day.key}`}
          >
            {day.label}
          </h2>
          <ul className="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
            {day.visits.map((visit) => {
              const zone = visitZoneNote(visit);
              return (
                <li key={visit.id}>
                  <button
                    className="grid min-h-14 w-full grid-cols-[5.5rem_minmax(0,1fr)] items-center gap-x-3 gap-y-1 px-4 py-2 text-left transition-colors hover:bg-surface-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary sm:grid-cols-[5.5rem_minmax(0,1fr)_auto_auto]"
                    onClick={() => onOpen(visit)}
                    type="button"
                  >
                    <span className="font-mono text-sm font-semibold text-ink">
                      {visitTimeLabel(visit)}
                      {zone && <span className="block text-[11px] font-normal text-muted">{zone}</span>}
                    </span>
                    <span className="min-w-0">
                      <span className="block break-words text-sm font-medium text-ink">
                        {visit.patientName ?? "Patient"}
                      </span>
                      {showClinic && <ClinicChip name={visit.clinicName} />}
                    </span>
                    <span className="col-start-2 text-[13px] text-muted sm:col-start-auto">
                      {TYPE_LABELS[visit.appointmentType]} · {visit.durationMinutes} min
                    </span>
                    <Badge className="col-start-2 justify-self-start sm:col-start-auto" variant={STATUS_TONES[visit.status]}>
                      {STATUS_LABELS[visit.status]}
                    </Badge>
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
    </div>
  );
}
