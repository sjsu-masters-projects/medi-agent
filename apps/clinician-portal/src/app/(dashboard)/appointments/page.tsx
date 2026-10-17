"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useSelector } from "react-redux";
import { ClinicFilterEmpty, ClinicFilterField } from "@/components/features/clinic-chip";
import { AppointmentOfferForm } from "@/components/features/appointment-offer-form";
import { AppointmentOfferHistory } from "@/components/features/appointment-offer-history";
import { Button, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { useAppointmentScheduling } from "@/hooks/use-appointment-scheduling";
import { useClinicFilter, type ClinicFilter } from "@/hooks/use-clinic-filter";
import {
  fetchSchedulingProfile,
  type AssignedSchedulingPatient,
} from "@/services/appointments";
import type { RootState } from "@/store/store";
import type { Appointment } from "@/types";
import { resolveSchedulingTimezone } from "@/utils/appointment-times";

function PatientAppointments({
  token,
  patient,
  appointments,
  disabled,
  onCreated,
  onSendingChange,
  appointmentId,
}: {
  token: string;
  patient: AssignedSchedulingPatient;
  appointments: Appointment[];
  disabled: boolean;
  onCreated: (rows: Appointment[]) => void;
  onSendingChange: (sending: boolean) => void;
  appointmentId?: string | null;
}) {
  const [settings, setSettings] = useState<ReturnType<
    typeof resolveSchedulingTimezone
  > | null>(null);
  const [settingsFailed, setSettingsFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [previous, setPrevious] = useState<Appointment>();
  const [draftVersion, setDraftVersion] = useState(0);
  const [success, setSuccess] = useState(false);
  useEffect(() => {
    let active = true;
    void fetchSchedulingProfile(token, patient.id)
      .then((profile) => {
        if (active) setSettings(resolveSchedulingTimezone(profile.timezone));
      })
      .catch(() => {
        if (active) setSettingsFailed(true);
      });
    return () => {
      active = false;
    };
  }, [token, patient.id, attempt]);
  if (!settings)
    return settingsFailed ? (
      <ErrorState
        title="Could not load the patient's timezone"
        description="Retry before entering appointment times."
        onRetry={() => {
          setSettingsFailed(false);
          setAttempt((value) => value + 1);
        }}
      />
    ) : (
      <div className="space-y-3 rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
        <p role="status" className="text-sm text-muted">
          Loading the patient&apos;s timezone…
        </p>
        <Skeleton className="h-[42px] w-full" />
        <Skeleton className="h-[42px] w-2/3" />
      </div>
    );
  function created(rows: Appointment[]) {
    onCreated(rows);
    setPrevious(undefined);
    setDraftVersion((value) => value + 1);
    setSuccess(true);
  }
  return (
    <div className="ma-enter space-y-4">
      <p className="inline-flex flex-wrap items-center gap-2 rounded-[9px] border border-line bg-surface px-3 py-1.5 text-[13px] text-ink-2">
        <Icon name="globe" className="h-4 w-4 text-muted" />
        Appointment timezone:{" "}
        <strong className="font-mono text-xs font-medium text-ink">
          {settings.timezone}
        </strong>
      </p>
      {settings.fallback && (
        <p
          role="status"
          className="flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink"
        >
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            The patient has no valid saved timezone. Times are entered and
            displayed in UTC.
          </span>
        </p>
      )}
      {success && (
        <p
          role="status"
          className="ma-enter flex items-start gap-2.5 rounded-xl border border-ok-line bg-ok-soft px-4 py-3 text-sm text-ok-ink"
        >
          <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Appointment offer sent. The patient can choose a time in Visits.
          </span>
        </p>
      )}
      <div className="grid items-start gap-6 xl:grid-cols-[420px_minmax(0,1fr)]">
        <AppointmentOfferForm
          key={draftVersion}
          token={token}
          careTeamId={patient.care_team_id}
          timezone={settings.timezone}
          disabled={disabled}
          previous={previous}
          onCreated={created}
          onSendingChange={onSendingChange}
        />
        <section className="min-w-0 rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)]">
          <div className="flex items-center justify-between gap-3 border-b border-line px-5 py-4">
            <div>
              <h2 className="text-[15px] font-semibold text-ink">
                Appointments and patient responses
              </h2>
              <p className="mt-0.5 text-[13px] text-muted">
                {patient.first_name} {patient.last_name}
              </p>
            </div>
            <span className="font-mono text-[11px] uppercase tracking-[0.06em] text-muted">
              {settings.timezone}
            </span>
          </div>
          <AppointmentOfferHistory
            patientName={`${patient.first_name} ${patient.last_name}`}
            appointmentId={appointmentId}
            token={token}
            appointments={appointments}
            timezone={settings.timezone}
            disabled={disabled}
            onRepropose={(visit) => {
              setPrevious(visit);
              setSuccess(false);
              setDraftVersion((value) => value + 1);
            }}
          />
        </section>
      </div>
    </div>
  );
}

function SchedulingWorkspace({ token, appointmentId }: { token: string; appointmentId: string | null }) {
  const clinicFilter: ClinicFilter = useClinicFilter();
  const { patients, appointments, loading, error, refresh, addOffer } =
    useAppointmentScheduling(token, clinicFilter.clinicId, clinicFilter.ready);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previousTarget, setPreviousTarget] = useState(appointmentId);
  if (previousTarget !== appointmentId) {
    setPreviousTarget(appointmentId);
    setSelectedId(null);
  }
  const linkedAppointment = appointments.find((visit) => visit.id === appointmentId);
  const effectiveSelectedId = selectedId ?? linkedAppointment?.careTeamId ?? "";
  const [sending, setSending] = useState(false);
  const selected = patients.find(
    (patient) => patient.care_team_id === effectiveSelectedId,
  );
  return (
    <div className="ma-page space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-[-0.02em] text-ink">
            Appointments
          </h1>
          <p className="mt-1 text-sm text-muted">
            Offer times to assigned patients and review their responses.
          </p>
        </div>
        <Button
          variant="secondary"
          disabled={loading || sending}
          onClick={refresh}
        >
          <Icon name="refresh" className="h-4 w-4" />
          {loading ? "Refreshing…" : "Refresh appointments"}
        </Button>
      </div>
      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
        >
          <span className="flex min-w-0 flex-1 items-start gap-2.5">
            <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
            <span>
              Could not refresh scheduling data. Previously loaded appointments
              remain visible; retry before sending an offer.
            </span>
          </span>
          <Button variant="secondary" onClick={refresh} disabled={loading}>
            Retry
          </Button>
        </div>
      )}
      {appointmentId && !loading && !error && (!linkedAppointment || !patients.some((patient) => patient.id === linkedAppointment.patientId && patient.care_team_id === linkedAppointment.careTeamId)) && <p role="status" className="text-sm text-muted">The linked appointment is unavailable. Select an assigned patient to review other appointments.</p>}
      {loading && !patients.length ? (
        <div className="space-y-3 rounded-2xl border border-line bg-surface p-5 shadow-[var(--shadow-card)]">
          <p role="status" className="text-sm text-muted">
            Loading assigned patients and appointments…
          </p>
          <Skeleton className="h-[42px] w-full max-w-md" />
          <Skeleton className="h-24 w-full" />
        </div>
      ) : (
        <>
          {!patients.length && !error && clinicFilter.clinicId ? (
            <div className="space-y-3 rounded-2xl border border-line bg-surface px-5 py-6 text-sm text-ink-2 shadow-[var(--shadow-card)]">
              <div className="flex justify-end"><ClinicFilterField filter={clinicFilter} /></div>
              <p><ClinicFilterEmpty filter={clinicFilter} /></p>
            </div>
          ) : !patients.length && !error ? (
            <EmptyState
              icon={<Icon name="cal" />}
              title="No assigned patients"
              description="An active care-team assignment is required to offer appointments."
            />
          ) : (
            <div className="flex flex-wrap items-end gap-4 rounded-2xl border border-line bg-surface px-5 py-4 shadow-[var(--shadow-card)]">
              <div className="w-full max-w-md">
              <label className="block">
                <span className="mb-1.5 block text-[13px] font-medium text-ink-2">
                  Patient
                </span>
                <select
                  className="h-[42px] w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted"
                  value={effectiveSelectedId}
                  disabled={loading || error || sending}
                  onChange={(event) => setSelectedId(event.target.value)}
                >
                  <option value="">Select an assigned patient</option>
                  {patients.map((patient) => (
                    <option
                      key={patient.care_team_id}
                      value={patient.care_team_id}
                    >
                      {patient.first_name} {patient.last_name}
                      {clinicFilter.multi && patient.clinic_name ? ` · ${patient.clinic_name}` : ""}
                    </option>
                  ))}
                </select>
              </label>
              {selected?.clinic_name && (
                <p className="mt-1.5 text-[13px] text-muted">
                  Clinic: {selected.clinic_name}
                </p>
              )}
              </div>
              <p className="pb-2.5 text-[13px] text-muted">
                <span className="font-mono">{patients.length}</span> assigned
              </p>
              <div className="ml-auto pb-1">
                <ClinicFilterField filter={clinicFilter} />
              </div>
            </div>
          )}
          {selected && (
            <PatientAppointments
              appointmentId={appointmentId}
              key={selected.care_team_id}
              token={token}
              patient={selected}
              appointments={appointments.filter(
                (visit) =>
                  visit.patientId === selected.id &&
                  visit.careTeamId === selected.care_team_id,
              )}
              disabled={loading || error || sending}
              onCreated={addOffer}
              onSendingChange={setSending}
            />
          )}
        </>
      )}
    </div>
  );
}

function AppointmentsContent() {
  const appointmentId = useSearchParams().get("appointmentId");
  const token = useSelector((state: RootState) => state.auth.accessToken);
  return token ? (
    <SchedulingWorkspace key={token} token={token} appointmentId={appointmentId} />
  ) : (
    <p role="status" className="text-sm text-muted">
      Sign in as a clinician to manage appointments.
    </p>
  );
}

export default function AppointmentsPage() {
  return <Suspense fallback={<p role="status">Loading appointments…</p>}><AppointmentsContent /></Suspense>;
}
