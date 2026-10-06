"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { HiOutlineCalendarDays } from "react-icons/hi2";
import { VisitOfferCard } from "@/components/features/visit-offer-card";
import { CalendarExportButton } from "@/components/features/calendar-export-button";
import { PageHeader } from "@/components/layouts";
import { Badge, Button, Card, EmptyState, ErrorState } from "@/components/ui";
import {
  getVisitsCopy,
  formatUpcomingVisitCount,
  formatVisitTime,
  resolveVisitsTimezone,
  type VisitsCopy,
} from "@/content/visits-copy";
import { usePatientProfileState } from "@/hooks/use-patient-profile";
import { useVisitsData } from "@/hooks/use-visits-data";
import type { AppointmentResponseAction } from "@/services/appointments";
import {
  AppointmentStatus,
  normalizeLocale,
  type Locale,
  type Appointment,
} from "@/types";
import { isUpcomingVisit, orderVisits } from "@/utils/visits-order";

const PROPOSED_STATUSES: string[] = [AppointmentStatus.PROPOSED];
const UPCOMING_STATUSES: string[] = [
  AppointmentStatus.CONFIRMED,
  AppointmentStatus.SCHEDULED,
];
const WAITING_STATUSES: string[] = [AppointmentStatus.ALTERNATIVE_REQUESTED];

type BadgeVariant = "success" | "warning" | "danger" | "info" | "neutral";

const STATUS_VARIANTS: Record<string, BadgeVariant> = {
  proposed: "warning",
  confirmed: "success",
  scheduled: "success",
  declined: "neutral",
  alternative_requested: "info",
  cancelled: "danger",
  completed: "neutral",
  no_show: "neutral",
  withdrawn: "neutral",
  expired: "neutral",
};
type ComposeAction = "request_alternative" | "cancel";

function VisitCard({
  visit,
  copy,
  locale,
  timezone,
  now,
  onRespond,
  responding,
  token,
}: {
  token?: string | null;
  visit: Appointment;
  copy: VisitsCopy;
  locale: Locale;
  timezone: string;
  now: number;
  onRespond?: (action: AppointmentResponseAction, note?: string) => void;
  responding?: boolean;
}) {
  const [composing, setComposing] = useState<ComposeAction | null>(null);
  const [note, setNote] = useState("");

  const label = copy.statuses[visit.status];
  const variant = STATUS_VARIANTS[visit.status] ?? "neutral";
  const isProposed = visit.status === AppointmentStatus.PROPOSED;
  const isUpcoming = UPCOMING_STATUSES.includes(visit.status);
  const canAct = Boolean(onRespond) && (isProposed || isUpcoming);

  function startCompose(action: ComposeAction) {
    setComposing(action);
    setNote("");
  }

  function cancelCompose() {
    setComposing(null);
    setNote("");
  }

  function submitCompose() {
    if (composing) {
      onRespond?.(composing, note);
    }
  }

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <p className="text-base font-bold text-[#17233a]">
          {formatVisitTime(visit.scheduledAt, locale, timezone) ??
            copy.invalidDate}
          <span className="block text-sm font-normal text-slate-600">
            {timezone}
          </span>
        </p>
        <Badge variant={variant}>{label}</Badge>
      </div>
      <p className="mt-2 text-sm text-slate-600">
        {copy.types[visit.appointmentType]} · {visit.durationMinutes}{" "}
        {copy.minutes}
      </p>
      <dl className="mt-2 space-y-1 text-sm text-[#5b6b83]">
        {visit.clinicianName ? (
          <dd>
            {copy.with} {visit.clinicianName}
          </dd>
        ) : null}
        {visit.reason ? <dd>{visit.reason}</dd> : null}
        {visit.location ? <dd>{visit.location}</dd> : null}
      </dl>
      {isUpcomingVisit(visit, now) && visit.notes ? (
        <div className="mt-3 rounded-xl bg-blue-50 p-3 text-sm text-slate-700">
          <p className="font-semibold">{copy.preparationNotes}</p>
          <p className="mt-1 whitespace-pre-wrap">{visit.notes}</p>
        </div>
      ) : null}
      {visit.patientNote ? (
        <p className="mt-2 text-sm italic text-[#5b6b83]">
          {copy.note} {visit.patientNote}
        </p>
      ) : null}
      {isProposed && visit.proposalExpiresAt ? (
        <p className="mt-2 text-sm text-slate-600">
          {copy.availableUntil}{" "}
          {formatVisitTime(visit.proposalExpiresAt, locale, timezone)} ·{" "}
          {timezone}
        </p>
      ) : null}
      {visit.status === AppointmentStatus.EXPIRED ? (
        <p className="mt-2 text-sm text-slate-600">{copy.expiredDetail}</p>
      ) : null}

      {isUpcoming && (
        <CalendarExportButton
          token={token}
          appointmentId={visit.id}
          locale={locale}
          disabled={responding}
        />
      )}

      {canAct ? (
        composing ? (
          <div className="mt-4 space-y-3">
            <label
              className="block text-sm font-semibold text-[#30415f]"
              htmlFor={`note-${visit.id}`}
            >
              {copy.compose[composing].label}
            </label>
            <textarea
              className="w-full rounded-2xl border border-[#d9cbc0] bg-white px-3 py-2 text-sm text-[#17233a] shadow-[inset_0_1px_0_rgba(255,255,255,0.8)] focus:border-[#147465] focus:outline-none"
              id={`note-${visit.id}`}
              disabled={responding}
              maxLength={1000}
              onChange={(event) => setNote(event.target.value)}
              placeholder={copy.compose[composing].placeholder}
              rows={3}
              value={note}
            />
            <div className="flex gap-3">
              <Button
                disabled={responding}
                fullWidth
                onClick={submitCompose}
                size="sm"
                variant={composing === "cancel" ? "danger" : "primary"}
              >
                {copy.compose[composing].confirm}
              </Button>
              <Button
                disabled={responding}
                onClick={cancelCompose}
                size="sm"
                variant="ghost"
              >
                {copy.back}
              </Button>
            </div>
          </div>
        ) : (
          <div className="mt-4 flex flex-wrap gap-3">
            {isProposed ? (
              <>
                <Button
                  disabled={responding}
                  onClick={() => onRespond?.("accept")}
                  size="sm"
                  variant="primary"
                >
                  {copy.accept}
                </Button>
                <Button
                  disabled={responding}
                  onClick={() => onRespond?.("decline")}
                  size="sm"
                  variant="secondary"
                >
                  {copy.decline}
                </Button>
                <Button
                  disabled={responding}
                  onClick={() => startCompose("request_alternative")}
                  size="sm"
                  variant="secondary"
                >
                  {copy.request}
                </Button>
                <Button
                  disabled={responding}
                  onClick={() => startCompose("cancel")}
                  size="sm"
                  variant="danger"
                >
                  {copy.cancel}
                </Button>
              </>
            ) : (
              <Button
                disabled={responding}
                onClick={() => startCompose("cancel")}
                size="sm"
                variant="danger"
              >
                {copy.cancelVisit}
              </Button>
            )}
          </div>
        )
      ) : null}
    </Card>
  );
}

function VisitGroup({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3">
      <h2 className="px-1 text-sm font-black uppercase tracking-[0.16em] text-[#5b6b83]">
        {title} ({count})
      </h2>
      {children}
    </section>
  );
}

export default function VisitsPage() {
  const router = useRouter();
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const updateClock = () => setNow(Date.now());
    const timer = window.setInterval(updateClock, 60000);
    window.addEventListener("focus", updateClock);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", updateClock);
    };
  }, []);
  const settings = usePatientProfileState();
  const locale = normalizeLocale(settings.profile?.preferredLanguage);
  const copy = getVisitsCopy(locale);
  const zone = resolveVisitsTimezone(
    settings.timezoneMissing ? undefined : settings.profile?.timezone,
  );
  const {
    accessToken,
    visits,
    loading,
    error,
    actionError,
    respond,
    respondingId,
    refresh,
  } = useVisitsData();
  const cardSettings = {
    copy,
    locale,
    timezone: zone.timezone,
    now,
    token: accessToken,
  };
  const actionMessages: Record<string, string> = {
    RESPONSE_SAVED_REFRESH_FAILED: copy.responseSavedRefreshError,
    APPOINTMENT_CONFLICT: copy.conflictError,
    APPOINTMENT_EXPIRED: copy.expiredError,
    APPOINTMENT_UNAVAILABLE: copy.unavailableError,
    APPOINTMENT_PAST: copy.pastError,
  };
  const actionMessage = actionMessages[actionError ?? ""] ?? copy.actionError;
  const actionsDisabled = Boolean(respondingId) || loading || Boolean(error);

  const proposed = orderVisits(
    visits.filter((visit) => PROPOSED_STATUSES.includes(visit.status)),
    "ascending",
  );
  const offers = new Map<string, Appointment[]>();
  for (const visit of proposed) {
    if (visit.proposalGroupId) {
      const slots = offers.get(visit.proposalGroupId) ?? [];
      slots.push(visit);
      offers.set(visit.proposalGroupId, slots);
    }
  }
  const standaloneProposals = proposed.filter(
    (visit) => !visit.proposalGroupId,
  );
  const upcoming = orderVisits(
    visits.filter((visit) => isUpcomingVisit(visit, now)),
    "ascending",
  );
  const waiting = orderVisits(
    visits.filter((visit) => WAITING_STATUSES.includes(visit.status)),
    "ascending",
  );
  const past = orderVisits(
    visits.filter(
      (visit) =>
        !PROPOSED_STATUSES.includes(visit.status) &&
        !isUpcomingVisit(visit, now) &&
        !WAITING_STATUSES.includes(visit.status),
    ),
    "descending",
  );

  return (
    <div className="patient-page space-y-4 pb-8" lang={locale}>
      <PageHeader
        subtitle={
          upcoming.length
            ? formatUpcomingVisitCount(upcoming.length, locale)
            : copy.subtitle
        }
        title={copy.title}
      />

      <div className="patient-stack -mt-4 space-y-6 px-5">
        {!settings.loading && zone.fallback ? (
          <Card>
            <p role="status">{copy.fallback}</p>
            <Button onClick={settings.refresh} variant="ghost">
              {copy.retry}
            </Button>
          </Card>
        ) : null}
        {settings.loading || (loading && visits.length === 0) ? (
          <Card>
            <p className="text-base text-[#64748b]">
              {settings.loading ? copy.loadingSettings : copy.loading}
            </p>
          </Card>
        ) : error && visits.length === 0 ? (
          <ErrorState
            description={copy.loadErrorDetail}
            action={<Button onClick={refresh}>{copy.retry}</Button>}
            title={copy.loadError}
          />
        ) : visits.length === 0 ? (
          <EmptyState
            description={copy.emptyDetail}
            icon={<HiOutlineCalendarDays />}
            title={copy.emptyTitle}
          />
        ) : (
          <>
            {loading ? (
              <p role="status" className="text-sm text-slate-600">
                {copy.loading}
              </p>
            ) : error ? (
              <Card>
                <p role="alert">{copy.loadErrorDetail}</p>
                <Button onClick={refresh} variant="ghost">
                  {copy.retry}
                </Button>
              </Card>
            ) : null}
            {actionError ? (
              <div
                className="rounded-[20px] border border-[#efbeb5] bg-[#fff2ef] px-4 py-3 text-sm font-semibold text-[#b94032]"
                role="alert"
              >
                {actionMessage}
                <Button
                  onClick={refresh}
                  disabled={loading || Boolean(respondingId)}
                  variant="ghost"
                >
                  {copy.refreshVisits}
                </Button>
              </div>
            ) : null}

            {proposed.length > 0 ? (
              <VisitGroup
                title={copy.proposed}
                count={offers.size + standaloneProposals.length}
              >
                {Array.from(offers, ([groupId, slots]) => (
                  <VisitOfferCard
                    key={groupId}
                    {...cardSettings}
                    slots={slots}
                    responding={actionsDisabled}
                    onRespond={respond}
                  />
                ))}
                {standaloneProposals.map((visit) => (
                  <VisitCard
                    {...cardSettings}
                    key={visit.id}
                    onRespond={(action, note) =>
                      respond(visit.id, action, note)
                    }
                    responding={actionsDisabled}
                    visit={visit}
                  />
                ))}
              </VisitGroup>
            ) : null}

            {upcoming.length > 0 ? (
              <VisitGroup title={copy.upcoming} count={upcoming.length}>
                {upcoming.map((visit) => (
                  <VisitCard
                    {...cardSettings}
                    key={visit.id}
                    onRespond={(action, note) =>
                      respond(visit.id, action, note)
                    }
                    responding={actionsDisabled}
                    visit={visit}
                  />
                ))}
              </VisitGroup>
            ) : null}

            {waiting.length > 0 ? (
              <VisitGroup title={copy.waiting} count={waiting.length}>
                {waiting.map((visit) => (
                  <VisitCard {...cardSettings} key={visit.id} visit={visit} />
                ))}
              </VisitGroup>
            ) : null}

            {past.length > 0 ? (
              <VisitGroup title={copy.past} count={past.length}>
                {past.map((visit) => (
                  <VisitCard {...cardSettings} key={visit.id} visit={visit} />
                ))}
              </VisitGroup>
            ) : null}
          </>
        )}
        {!loading && !settings.loading && !error ? (
          <Card>
            <h2 className="font-semibold text-slate-900">
              {copy.chatHelp.title}
            </h2>
            <p className="mt-2 text-sm text-slate-600">
              {copy.chatHelp.description}
            </p>
            <Button
              className="mt-4"
              onClick={() => router.push("/chat")}
              disabled={Boolean(respondingId)}
            >
              {copy.chatHelp.open}
            </Button>
          </Card>
        ) : null}
      </div>
    </div>
  );
}
