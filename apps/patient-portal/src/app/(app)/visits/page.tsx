"use client";

import type { ReactNode } from "react";
import { HiOutlineCalendarDays } from "react-icons/hi2";
import { PageHeader } from "@/components/layouts";
import { Badge, Button, Card, EmptyState, ErrorState } from "@/components/ui";
import { useVisitsData } from "@/hooks/use-visits-data";
import { AppointmentStatus, type Appointment } from "@/types";

const PROPOSED_STATUSES: string[] = [AppointmentStatus.PROPOSED];
const UPCOMING_STATUSES: string[] = [
  AppointmentStatus.CONFIRMED,
  AppointmentStatus.SCHEDULED,
];

type BadgeVariant = "success" | "warning" | "danger" | "info" | "neutral";

const STATUS_META: Record<string, { label: string; variant: BadgeVariant }> = {
  [AppointmentStatus.PROPOSED]: { label: "Proposed", variant: "warning" },
  [AppointmentStatus.CONFIRMED]: { label: "Confirmed", variant: "success" },
  [AppointmentStatus.SCHEDULED]: { label: "Scheduled", variant: "success" },
  [AppointmentStatus.DECLINED]: { label: "Declined", variant: "neutral" },
  [AppointmentStatus.CANCELLED]: { label: "Cancelled", variant: "danger" },
  [AppointmentStatus.COMPLETED]: { label: "Completed", variant: "neutral" },
  [AppointmentStatus.NO_SHOW]: { label: "Missed", variant: "neutral" },
};

function formatWhen(scheduledAt: string): string {
  return new Intl.DateTimeFormat("en-US", {
    dateStyle: "full",
    timeStyle: "short",
  }).format(new Date(scheduledAt));
}

function VisitCard({
  visit,
  onAccept,
  onDecline,
  responding,
}: {
  visit: Appointment;
  onAccept?: () => void;
  onDecline?: () => void;
  responding?: boolean;
}) {
  const meta = STATUS_META[visit.status] ?? {
    label: visit.status,
    variant: "neutral",
  };
  const showActions = Boolean(onAccept && onDecline);

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <p className="text-base font-bold text-[#17233a]">
          {formatWhen(visit.scheduledAt)}
        </p>
        <Badge variant={meta.variant}>{meta.label}</Badge>
      </div>
      <dl className="mt-2 space-y-1 text-sm text-[#5b6b83]">
        {visit.clinicianName ? <dd>With {visit.clinicianName}</dd> : null}
        {visit.reason ? <dd>{visit.reason}</dd> : null}
        {visit.location ? <dd>{visit.location}</dd> : null}
      </dl>
      {showActions ? (
        <div className="mt-4 flex gap-3">
          <Button
            disabled={responding}
            fullWidth
            onClick={onAccept}
            size="sm"
            variant="primary"
          >
            Accept
          </Button>
          <Button
            disabled={responding}
            fullWidth
            onClick={onDecline}
            size="sm"
            variant="secondary"
          >
            Decline
          </Button>
        </div>
      ) : null}
    </Card>
  );
}

function VisitGroup({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h2 className="px-1 text-sm font-black uppercase tracking-[0.16em] text-[#5b6b83]">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default function VisitsPage() {
  const { visits, loading, error, respond, respondingId, refresh } =
    useVisitsData();

  const proposed = visits.filter((visit) =>
    PROPOSED_STATUSES.includes(visit.status),
  );
  const upcoming = visits.filter((visit) =>
    UPCOMING_STATUSES.includes(visit.status),
  );
  const past = visits.filter(
    (visit) =>
      !PROPOSED_STATUSES.includes(visit.status) &&
      !UPCOMING_STATUSES.includes(visit.status),
  );

  return (
    <div className="patient-page space-y-4 pb-8">
      <PageHeader
        subtitle="Review and confirm appointments from your care team."
        title="Visits"
      />

      <div className="patient-stack -mt-4 space-y-6 px-5">
        {loading ? (
          <Card>
            <p className="text-base text-[#64748b]">Loading your visits...</p>
          </Card>
        ) : error ? (
          <ErrorState
            description={error}
            onRetry={refresh}
            title="Could not load your visits"
          />
        ) : visits.length === 0 ? (
          <EmptyState
            description="When your clinician proposes a visit, it will appear here for you to accept or decline."
            icon={<HiOutlineCalendarDays />}
            title="No visits yet"
          />
        ) : (
          <>
            {proposed.length > 0 ? (
              <VisitGroup title="Awaiting your response">
                {proposed.map((visit) => (
                  <VisitCard
                    key={visit.id}
                    onAccept={() => respond(visit.id, "accept")}
                    onDecline={() => respond(visit.id, "decline")}
                    responding={respondingId === visit.id}
                    visit={visit}
                  />
                ))}
              </VisitGroup>
            ) : null}

            {upcoming.length > 0 ? (
              <VisitGroup title="Upcoming">
                {upcoming.map((visit) => (
                  <VisitCard key={visit.id} visit={visit} />
                ))}
              </VisitGroup>
            ) : null}

            {past.length > 0 ? (
              <VisitGroup title="Past & other">
                {past.map((visit) => (
                  <VisitCard key={visit.id} visit={visit} />
                ))}
              </VisitGroup>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
