"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Icon } from "@/components/ui/icons";
import { PullToRefresh } from "@/components/ui/pull-to-refresh";
import { VisitOfferCard } from "@/components/features/visit-offer-card";
import { CalendarExportButton } from "@/components/features/calendar-export-button";
import { PageHeader } from "@/components/layouts";
import { Button, Card, ErrorState } from "@/components/ui";
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

const STATUS_STYLES: Record<string, string> = {
  proposed: "bg-note-tint text-note-ink",
  confirmed: "bg-brand-tint text-brand-ink",
  scheduled: "bg-brand-tint text-brand-ink",
  alternative_requested: "bg-lab-tint text-lab-ink",
  cancelled: "bg-danger-tint text-danger-ink",
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
  const statusStyle = STATUS_STYLES[visit.status] ?? "bg-surface-2 text-muted";
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
    <article id={`visit-${visit.id}`} tabIndex={-1} className="border-b border-line px-[14px] py-[13px] last:border-b-0">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="min-w-0 break-words font-mono text-[15px] font-medium leading-6 text-ink">
          {formatVisitTime(visit.scheduledAt, locale, timezone) ??
            copy.invalidDate}
          <span className="block font-sans text-[13px] font-normal text-muted">
            {timezone}
          </span>
        </p>
        <span
          className={`max-w-full rounded-full px-2.5 py-1 text-xs font-medium ${statusStyle}`}
        >
          {label}
        </span>
      </div>
      {visit.clinicName ? (
        <p className="mt-1 break-words text-sm text-muted">
          {copy.atClinic(visit.clinicName)}
        </p>
      ) : null}
      <p className="mt-2 text-sm text-muted">
        {copy.types[visit.appointmentType]} · {visit.durationMinutes}{" "}
        {copy.minutes}
      </p>
      <dl className="mt-2 space-y-1 break-words text-sm text-ink-2">
        {visit.clinicianName ? (
          <dd>
            {copy.with} {visit.clinicianName}
          </dd>
        ) : null}
        {visit.reason ? <dd>{visit.reason}</dd> : null}
        {visit.location ? <dd>{visit.location}</dd> : null}
      </dl>
      {isUpcomingVisit(visit, now) && visit.notes ? (
        <div className="mt-3 rounded-xl bg-surface-2 p-3 text-sm text-ink-2">
          <p className="font-semibold">{copy.preparationNotes}</p>
          <p className="mt-1 whitespace-pre-wrap break-words">{visit.notes}</p>
        </div>
      ) : null}
      {visit.status === AppointmentStatus.CANCELLED && visit.cancelledBy === "clinician" ? (
        <div className="mt-2 rounded-xl bg-danger-tint p-3 text-sm text-danger-ink" role="note">
          <p className="font-semibold">{copy.cancelledByCare}</p>
          {visit.cancelReasonCode ? (
            <p className="mt-1 break-words">
              {copy.cancelReasonLabel} {copy.cancelReasons[visit.cancelReasonCode]}
              {visit.cancelReason ? ` — ${visit.cancelReason}` : ""}
            </p>
          ) : null}
        </div>
      ) : null}
      {visit.patientNote ? (
        <p className="mt-2 break-words text-sm italic text-muted">
          {copy.note} {visit.patientNote}
        </p>
      ) : null}
      {isProposed && visit.proposalExpiresAt ? (
        <p className="mt-2 break-words text-sm text-muted">
          {copy.availableUntil}{" "}
          {formatVisitTime(visit.proposalExpiresAt, locale, timezone)} ·{" "}
          {timezone}
        </p>
      ) : null}
      {visit.status === AppointmentStatus.EXPIRED ? (
        <p className="mt-2 text-sm text-muted">{copy.expiredDetail}</p>
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
              className="block text-sm font-semibold text-ink-2"
              htmlFor={`note-${visit.id}`}
            >
              {copy.compose[composing].label}
            </label>
            <textarea
              className="min-h-24 w-full rounded-2xl border border-line-strong bg-surface px-4 py-3 text-base text-ink outline-none transition placeholder:text-muted focus:border-brand focus:ring-4 focus:ring-brand/15"
              id={`note-${visit.id}`}
              disabled={responding}
              maxLength={1000}
              onChange={(event) => setNote(event.target.value)}
              placeholder={copy.compose[composing].placeholder}
              rows={3}
              value={note}
            />
            <div className="flex flex-wrap gap-3 [&_button]:min-h-11">
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
          <div className="mt-4 flex flex-wrap gap-2 [&_button]:min-h-11">
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
    </article>
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
    <section className="space-y-2">
      <h2 className="px-1.5 font-mono text-xs uppercase tracking-[0.08em] text-muted">
        {title} ({count})
      </h2>
      <div className="overflow-hidden rounded-[22px] bg-surface">
        {children}
      </div>
    </section>
  );
}

export default function VisitsPage() {
  const router = useRouter();
  const appointmentId = useSearchParams().get("appointmentId");
  const focusedAppointment = useRef<string | null>(null);
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
  const unavailableAppointment = Boolean(appointmentId && !loading && !error && !visits.some((visit) => visit.id === appointmentId));
  useEffect(() => {
    if (!appointmentId) { focusedAppointment.current = null; return; }
    if (loading || error || focusedAppointment.current === appointmentId) return;
    const target = document.getElementById(`visit-${appointmentId}`);
    if (!target) return;
    focusedAppointment.current = appointmentId;
    target.focus();
    target.scrollIntoView?.({ block: "center", behavior: window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  }, [appointmentId, loading, error, visits]);

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
    <PullToRefresh
      onRefresh={refresh}
      busy={loading || settings.loading || Boolean(respondingId)}
      label={copy.refreshVisits}
    >
      <div
        className="patient-page space-y-4 pb-6"
        lang={locale}
        aria-busy={loading || settings.loading}
      >
        <PageHeader
          rightAction={
            !actionError ? (
              <button
                type="button"
                aria-label={copy.refreshVisits}
                title={copy.refreshVisits}
                className="ma-press flex h-11 w-11 items-center justify-center rounded-[14px] text-ink-2 hover:bg-surface disabled:opacity-50"
                disabled={loading || settings.loading || Boolean(respondingId)}
                onClick={refresh}
              >
                <Icon
                  name="refresh"
                  className={
                    loading ? "h-5 w-5 motion-safe:animate-spin" : "h-5 w-5"
                  }
                />
              </button>
            ) : undefined
          }
          subtitle={
            upcoming.length
              ? formatUpcomingVisitCount(upcoming.length, locale)
              : copy.subtitle
          }
          title={copy.title}
        />

        <div className="patient-stack space-y-5 px-4">
          {unavailableAppointment && <p role="alert" className="rounded-2xl bg-danger-tint p-3 text-sm text-danger-ink">{locale === "es-MX" ? "Esta cita no está disponible. Actualiza tus citas." : "This visit is unavailable. Refresh your visits."}</p>}
          {!settings.loading && zone.fallback ? (
            <Card className="rounded-[22px] shadow-none">
              <p role="status">{copy.fallback}</p>
              <Button onClick={settings.refresh} variant="ghost">
                {copy.retry}
              </Button>
            </Card>
          ) : null}
          {settings.loading || (loading && visits.length === 0) ? (
            <div className="space-y-3">
              <p role="status" className="sr-only">
                {settings.loading ? copy.loadingSettings : copy.loading}
              </p>
              <div aria-hidden="true" className="ma-skeleton h-40 w-full rounded-[22px]" />
            </div>
          ) : error && visits.length === 0 ? (
            <ErrorState
              description={copy.loadErrorDetail}
              action={<Button onClick={refresh}>{copy.retry}</Button>}
              title={copy.loadError}
            />
          ) : visits.length === 0 ? (
            <div className="flex flex-col items-center gap-3 rounded-[22px] bg-surface px-6 py-9 text-center">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-tint text-brand">
                <Icon name="cal" />
              </span>
              <h2 className="text-[17px] font-semibold text-ink">
                {copy.emptyTitle}
              </h2>
              <p className="max-w-[32ch] text-[15px] leading-6 text-muted">
                {copy.emptyDetail}
              </p>
            </div>
          ) : (
            <>
              {loading ? (
                <p role="status" className="text-sm text-muted">
                  {copy.loading}
                </p>
              ) : error ? (
                <Card className="rounded-[22px] shadow-none">
                  <p role="alert">{copy.loadErrorDetail}</p>
                  <Button onClick={refresh} variant="ghost">
                    {copy.retry}
                  </Button>
                </Card>
              ) : null}
              {actionError ? (
                <div
                  className="rounded-[22px] bg-danger-tint px-4 py-3 text-sm font-medium text-danger-ink"
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
            <section className="flex flex-wrap items-center gap-3 rounded-[22px] bg-surface px-[14px] py-[14px]">
              <span aria-hidden="true" className="flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] bg-brand-tint text-brand"><Icon name="chat" className="h-5 w-5" /></span>
              <div className="min-w-0 flex-1 basis-40">
                <h2 className="text-[15px] font-semibold text-ink">
                  {copy.chatHelp.title}
                </h2>
                <p className="mt-0.5 text-[13px] leading-5 text-muted">
                  {copy.chatHelp.description}
                </p>
              </div>
              <Button
                size="sm"
                variant="secondary"
                onClick={() => router.push("/chat")}
                disabled={Boolean(respondingId)}
              >
                {copy.chatHelp.open}
              </Button>
            </section>
          ) : null}
        </div>
      </div>
    </PullToRefresh>
  );
}
