"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useSelector } from "react-redux";
import { ClinicFilterEmpty, ClinicFilterField } from "@/components/features/clinic-chip";
import { NewOfferPanel } from "@/components/features/new-offer-panel";
import { ScheduleAgenda } from "@/components/features/schedule-agenda";
import { ScheduleNeedsAction } from "@/components/features/schedule-needs-action";
import { VisitDetailPanel } from "@/components/features/visit-detail-panel";
import { Button, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { SegmentedControl } from "@/components/ui/toolbar";
import { clinicScopeLabel } from "@/hooks/clinic-scope";
import { useClinicFilter } from "@/hooks/use-clinic-filter";
import {
  fetchMySchedule,
  fetchSchedulingAppointments,
  fetchSchedulingPatients,
  type AssignedSchedulingPatient,
  type MySchedule,
  type ScheduleVisit,
} from "@/services/appointments";
import type { RootState } from "@/store/store";
import type { Appointment } from "@/types";
import { agendaRange, dayLabel, visitTimeLabel, type AgendaMode } from "@/utils/schedule";

interface Target {
  appointmentId: string;
  patientId: string;
  patientName?: string;
}

function ScheduleWorkspace({ token, appointmentId }: { token: string; appointmentId: string | null }) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const clinicFilter = useClinicFilter();
  const [mode, setMode] = useState<AgendaMode>("day");
  const [showCancelled, setShowCancelled] = useState(false);
  const [schedule, setSchedule] = useState<MySchedule | null>(null);
  const [roster, setRoster] = useState<AssignedSchedulingPatient[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [now, setNow] = useState(() => new Date(Date.now()));
  const [offerFor, setOfferFor] = useState<{ previous?: Appointment } | null>(null);
  const [sent, setSent] = useState(false);
  const [fallback, setFallback] = useState<Appointment[] | null>(null);

  const { clinicId, ready } = clinicFilter;
  useEffect(() => {
    if (!ready) return;
    let live = true;
    const current = new Date(Date.now());
    const { from, to } = agendaRange(mode, current);
    void Promise.all([
      fetchMySchedule(token, from.toISOString(), to.toISOString(), clinicId, showCancelled),
      fetchSchedulingPatients(token, clinicId).catch(() => null),
    ])
      .then(([result, people]) => {
        if (!live) return;
        setSchedule(result);
        if (people) setRoster(people);
        setNow(current);
        setError(false);
      })
      .catch(() => {
        if (live) setError(true);
      })
      .finally(() => {
        if (live) setLoading(false);
      });
    return () => {
      live = false;
    };
  }, [token, mode, clinicId, ready, attempt, showCancelled]);

  function refresh() {
    setLoading(true);
    setError(false);
    setAttempt((value) => value + 1);
  }

  const openVisit = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(searchParams?.toString() ?? "");
      if (id) next.set("appointmentId", id);
      else next.delete("appointmentId");
      const query = next.toString();
      router.replace(query ? `${pathname}?${query}` : (pathname ?? "/appointments"), { scroll: false });
    },
    [pathname, router, searchParams],
  );

  // A link to an appointment that is not in the loaded range (for example from an alert):
  // look it up in the caller's full list, which applies the same access rule.
  const known =
    schedule?.visits.find((visit) => visit.id === appointmentId) ??
    schedule?.needsAction.find((item) => item.appointmentId === appointmentId);
  useEffect(() => {
    if (!appointmentId || known || !schedule) return;
    let live = true;
    void fetchSchedulingAppointments(token, clinicId)
      .then((rows) => {
        if (live) setFallback(rows);
      })
      .catch(() => {
        if (live) setFallback([]);
      });
    return () => {
      live = false;
    };
  }, [appointmentId, known, schedule, token, clinicId]);

  let target: Target | null = null;
  if (appointmentId) {
    const fromFallback = fallback?.find((row) => row.id === appointmentId);
    const patientId =
      (known && "patientId" in known ? known.patientId : undefined) ??
      fromFallback?.patientId;
    if (patientId) {
      const person = roster.find((row) => row.id === patientId);
      target = {
        appointmentId,
        patientId,
        patientName:
          (known && "patientName" in known ? known.patientName : undefined) ??
          (person ? `${person.first_name} ${person.last_name}` : undefined),
      };
    }
  }
  const unavailable = Boolean(appointmentId && !target && fallback && !known);

  const scope = clinicScopeLabel(clinicFilter);
  const visits = schedule?.visits ?? [];
  const next: ScheduleVisit | null = schedule?.nextVisit ?? null;
  const period = mode === "day" ? "today" : "this week";

  return (
    <div className="ma-page space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">My schedule</h1>
          <p className="mt-1 text-sm text-muted">
            Your visits and appointment offers{scope ? ` · ${scope}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ClinicFilterField filter={clinicFilter} />
          <Button
            aria-label="Refresh schedule"
            disabled={loading}
            onClick={refresh}
            variant="secondary"
          >
            <Icon name="refresh" className={`h-4 w-4 ${loading ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">{loading ? "Refreshing…" : "Refresh"}</span>
          </Button>
          <Button
            disabled={!roster.length}
            onClick={() => {
              setSent(false);
              setOfferFor({});
            }}
          >
            <Icon name="plus" className="h-4 w-4" />
            New offer
          </Button>
        </div>
      </div>

      {sent && (
        <p
          role="status"
          className="ma-enter flex items-start gap-2.5 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink"
        >
          <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>Appointment offer sent. The patient can choose a time in Visits.</span>
        </p>
      )}
      {unavailable && (
        <p role="status" className="text-sm text-muted">
          The linked appointment is unavailable.
        </p>
      )}

      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
        >
          <span className="flex min-w-0 flex-1 items-start gap-2.5">
            <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
            <span>Could not load your schedule.{schedule ? " Showing what was loaded before." : ""}</span>
          </span>
          <Button variant="secondary" onClick={refresh} disabled={loading}>
            Retry
          </Button>
        </div>
      )}

      {loading && !schedule ? (
        <div aria-label="Loading schedule" className="space-y-3">
          <p role="status" className="text-sm text-muted">Loading your schedule…</p>
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : !schedule ? (
        error ? <ErrorState title="Your schedule is unavailable" description="Retry to load your visits." onRetry={refresh} /> : null
      ) : (
        <>
          <ScheduleNeedsAction
            items={schedule.needsAction}
            now={now.getTime()}
            onOpen={(item) => openVisit(item.appointmentId)}
            showClinic={clinicFilter.multi}
          />
          <div className="flex flex-wrap items-center justify-between gap-3">
            <SegmentedControl
              label="Schedule range"
              onChange={setMode}
              options={[
                { value: "day", label: "Today" },
                { value: "week", label: "This week" },
              ]}
              value={mode}
            />
            <label className="flex min-h-9 cursor-pointer items-center gap-2 text-[13px] text-ink-2">
              <input
                checked={showCancelled}
                className="h-4 w-4 accent-[var(--color-primary)]"
                onChange={(event) => setShowCancelled(event.target.checked)}
                type="checkbox"
              />
              Show cancelled
            </label>
          </div>
          {visits.length ? (
            <ScheduleAgenda
              now={now}
              onOpen={(visit) => openVisit(visit.id)}
              showClinic={clinicFilter.multi}
              visits={visits}
            />
          ) : clinicId && !next ? (
            <div className="rounded-2xl border border-line bg-surface px-5 py-6 text-sm text-ink-2 shadow-[var(--shadow-card)]">
              <ClinicFilterEmpty filter={clinicFilter} noun="visits" />
            </div>
          ) : (
            <EmptyState
              icon={<Icon name="cal" />}
              title={`No visits ${period}`}
              description={
                next
                  ? undefined
                  : "Nothing is booked. Offer times to a patient to fill your schedule."
              }
              action={
                <div className="flex flex-col items-center gap-3">
                  {next && (
                    <button
                      className="max-w-full break-words rounded-lg px-2 py-1 text-sm text-ink-2 underline-offset-2 hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary"
                      onClick={() => openVisit(next.id)}
                      type="button"
                    >
                      Next visit: {dayLabel(new Date(next.scheduledAt), now)}, {visitTimeLabel(next)}
                      {next.patientName ? ` · ${next.patientName}` : ""}
                    </button>
                  )}
                  <Button
                    disabled={!roster.length}
                    onClick={() => {
                      setSent(false);
                      setOfferFor({});
                    }}
                    variant="secondary"
                  >
                    <Icon name="plus" className="h-4 w-4" />
                    New offer
                  </Button>
                </div>
              }
            />
          )}
        </>
      )}

      {target && (
        <VisitDetailPanel
          appointmentId={target.appointmentId}
          key={target.appointmentId}
          onClose={() => openVisit(null)}
          onRepropose={(visit) => {
            openVisit(null);
            setSent(false);
            setOfferFor({ previous: visit });
          }}
          patientId={target.patientId}
          onChanged={refresh}
          patientName={target.patientName}
          showClinic={clinicFilter.multi}
          token={token}
        />
      )}
      {offerFor && (
        <NewOfferPanel
          onClose={() => setOfferFor(null)}
          onCreated={() => {
            setOfferFor(null);
            setSent(true);
            refresh();
          }}
          previous={offerFor.previous}
          roster={roster}
          showClinic={clinicFilter.multi}
          token={token}
        />
      )}
    </div>
  );
}

function ScheduleContent() {
  const appointmentId = useSearchParams()?.get("appointmentId") ?? null;
  const token = useSelector((state: RootState) => state.auth.accessToken);
  return token ? (
    <ScheduleWorkspace key={token} token={token} appointmentId={appointmentId} />
  ) : (
    <p role="status" className="text-sm text-muted">
      Sign in as a clinician to manage appointments.
    </p>
  );
}

export default function AppointmentsPage() {
  return (
    <Suspense fallback={<p role="status">Loading your schedule…</p>}>
      <ScheduleContent />
    </Suspense>
  );
}
