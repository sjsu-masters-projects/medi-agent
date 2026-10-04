"use client";

import { useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { AppointmentOfferForm } from "@/components/features/appointment-offer-form";
import { AppointmentOfferHistory } from "@/components/features/appointment-offer-history";
import { Button, EmptyState, ErrorState } from "@/components/ui";
import { useAppointmentScheduling } from "@/hooks/use-appointment-scheduling";
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
}: {
  token: string;
  patient: AssignedSchedulingPatient;
  appointments: Appointment[];
  disabled: boolean;
  onCreated: (rows: Appointment[]) => void;
  onSendingChange: (sending: boolean) => void;
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
      <p role="status" className="text-sm text-gray-600">
        Loading the patient&apos;s timezone…
      </p>
    );
  function created(rows: Appointment[]) {
    onCreated(rows);
    setPrevious(undefined);
    setDraftVersion((value) => value + 1);
    setSuccess(true);
  }
  return (
    <div className="space-y-6">
      <p className="text-sm text-gray-600">
        Appointment timezone: <strong>{settings.timezone}</strong>
      </p>
      {settings.fallback && (
        <p
          role="status"
          className="rounded-lg bg-yellow-50 p-3 text-sm text-yellow-800"
        >
          The patient has no valid saved timezone. Times are entered and
          displayed in UTC.
        </p>
      )}
      {success && (
        <p
          role="status"
          className="rounded-lg bg-green-50 p-3 text-sm text-green-800"
        >
          Appointment offer sent. The patient can choose a time in Visits.
        </p>
      )}
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
      <section className="space-y-3">
        <h2 className="text-lg font-semibold text-gray-900">
          Appointments and patient responses
        </h2>
        <AppointmentOfferHistory
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
  );
}

function SchedulingWorkspace({ token }: { token: string }) {
  const { patients, appointments, loading, error, refresh, addOffer } =
    useAppointmentScheduling(token);
  const [selectedId, setSelectedId] = useState("");
  const [sending, setSending] = useState(false);
  const selected = patients.find(
    (patient) => patient.care_team_id === selectedId,
  );
  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Appointments</h1>
          <p className="text-sm text-gray-600">
            Offer times to assigned patients and review their responses.
          </p>
        </div>
        <Button
          variant="secondary"
          disabled={loading || sending}
          onClick={refresh}
        >
          {loading ? "Refreshing…" : "Refresh appointments"}
        </Button>
      </div>
      {error && (
        <div
          role="alert"
          className="flex items-center justify-between gap-3 rounded-lg bg-red-50 p-4 text-sm text-red-700"
        >
          <span>
            Could not refresh scheduling data. Previously loaded appointments
            remain visible; retry before sending an offer.
          </span>
          <Button variant="secondary" onClick={refresh} disabled={loading}>
            Retry
          </Button>
        </div>
      )}
      {loading && !patients.length ? (
        <p role="status">Loading assigned patients and appointments…</p>
      ) : (
        <>
          {!patients.length && !error ? (
            <EmptyState
              title="No assigned patients"
              description="An active care-team assignment is required to offer appointments."
            />
          ) : (
            <label className="block max-w-md text-sm font-medium text-gray-700">
              Patient
              <select
                className="mt-1 w-full rounded-lg border border-gray-300 bg-white px-3 py-2"
                value={selectedId}
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
                  </option>
                ))}
              </select>
            </label>
          )}
          {selected && (
            <PatientAppointments
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

export default function AppointmentsPage() {
  const token = useSelector((state: RootState) => state.auth.accessToken);
  return token ? (
    <SchedulingWorkspace key={token} token={token} />
  ) : (
    <p role="status">Sign in as a clinician to manage appointments.</p>
  );
}
