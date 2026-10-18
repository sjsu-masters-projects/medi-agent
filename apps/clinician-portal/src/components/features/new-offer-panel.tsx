"use client";

import { useCallback, useEffect, useState } from "react";
import { ErrorState, Modal, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import {
  fetchBusyTimes,
  fetchSchedulingProfile,
  type AssignedSchedulingPatient,
} from "@/services/appointments";
import type { Appointment } from "@/types";
import { resolveSchedulingTimezone } from "@/utils/appointment-times";
import { AppointmentOfferForm } from "./appointment-offer-form";

interface Props {
  token: string;
  roster: AssignedSchedulingPatient[];
  /** Open for one patient (from a patient record); their links are the only choices. */
  patientId?: string;
  /** Offer new times after a decline, a change request or an expiry. */
  previous?: Appointment;
  /** Name the clinic of the link (multi-clinic clinicians only). */
  showClinic: boolean;
  onClose: () => void;
  onCreated: (rows: Appointment[]) => void;
}

const selectClass =
  "h-[42px] w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted";

function PanelBody({
  token,
  patient,
  previous,
  showClinic,
  onCreated,
  setSending,
}: {
  token: string;
  patient: AssignedSchedulingPatient;
  previous?: Appointment;
  showClinic: boolean;
  onCreated: (rows: Appointment[]) => void;
  setSending: (value: boolean) => void;
}) {
  const [settings, setSettings] = useState<ReturnType<typeof resolveSchedulingTimezone> | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    let live = true;
    void fetchSchedulingProfile(token, patient.id)
      .then((profile) => {
        if (live) setSettings(resolveSchedulingTimezone(profile.timezone));
      })
      .catch(() => {
        if (live) setFailed(true);
      });
    return () => {
      live = false;
    };
  }, [token, patient.id, attempt]);
  const loadBusy = useCallback((from: string, to: string) => fetchBusyTimes(token, from, to), [token]);

  if (!settings)
    return failed ? (
      <div className="px-5 py-5">
        <ErrorState
          title="Could not load the patient's timezone"
          description="Retry before entering appointment times."
          onRetry={() => {
            setFailed(false);
            setAttempt((value) => value + 1);
          }}
        />
      </div>
    ) : (
      <div className="space-y-3 px-5 py-5">
        <p role="status" className="text-sm text-muted">
          Loading the patient&apos;s timezone…
        </p>
        <Skeleton className="h-[42px] w-full" />
        <Skeleton className="h-[42px] w-2/3" />
      </div>
    );
  return (
    <>
      {settings.fallback && (
        <p
          role="status"
          className="mx-5 mt-4 flex items-start gap-2.5 rounded-xl border border-warn-line bg-warn-soft px-3.5 py-2.5 text-[13px] text-warn-ink"
        >
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>The patient has no valid saved timezone. Times are entered and displayed in UTC.</span>
        </p>
      )}
      <AppointmentOfferForm
        token={token}
        careTeamId={patient.care_team_id}
        timezone={settings.timezone}
        disabled={false}
        previous={previous}
        showClinic={showClinic}
        loadBusy={loadBusy}
        onCreated={onCreated}
        onSendingChange={setSending}
      />
    </>
  );
}

/** "New offer": a right-hand panel (full screen on a phone) with the patient picker and form. */
export function NewOfferPanel({
  token,
  roster,
  patientId,
  previous,
  showClinic,
  onClose,
  onCreated,
}: Props) {
  const candidates = previous
    ? roster.filter((patient) => patient.care_team_id === previous.careTeamId)
    : patientId
      ? roster.filter((patient) => patient.id === patientId)
      : roster;
  const locked = Boolean(previous) || (Boolean(patientId) && candidates.length === 1);
  const [chosen, setChosen] = useState("");
  const [sending, setSending] = useState(false);
  const careTeamId = locked ? (candidates[0]?.care_team_id ?? "") : chosen;
  const patient = candidates.find((row) => row.care_team_id === careTeamId);
  return (
    <Modal
      contentClassName="!p-0"
      onClose={() => {
        if (!sending) onClose();
      }}
      open
      placement="side"
      title={previous ? "Offer new times" : "New offer"}
    >
      <div className="flex min-h-0 flex-1 flex-col">
        <div className="space-y-1 border-b border-line px-5 py-4">
          {locked ? (
            <p className="text-sm font-medium text-ink">
              {patient ? `${patient.first_name} ${patient.last_name}` : "Patient unavailable"}
            </p>
          ) : (
            <label className="block">
              <span className="mb-1.5 block text-[13px] font-medium text-ink-2">Patient</span>
              <select
                className={selectClass}
                disabled={sending}
                onChange={(event) => setChosen(event.target.value)}
                value={chosen}
              >
                <option value="">Select a patient</option>
                {candidates.map((row) => (
                  <option key={row.care_team_id} value={row.care_team_id}>
                    {row.first_name} {row.last_name}
                    {showClinic && row.clinic_name ? ` · ${row.clinic_name}` : ""}
                  </option>
                ))}
              </select>
            </label>
          )}
          {showClinic && patient?.clinic_name && (
            <p className="text-[13px] text-muted">
              Clinic: <span className="font-medium text-ink-2">{patient.clinic_name}</span>
            </p>
          )}
        </div>
        {patient ? (
          <PanelBody
            key={patient.care_team_id}
            token={token}
            patient={patient}
            previous={previous}
            showClinic={showClinic}
            onCreated={onCreated}
            setSending={setSending}
          />
        ) : (
          <p className="px-5 py-6 text-sm text-muted">
            {locked
              ? "This patient is no longer on your care team, so you cannot offer times."
              : "Choose a patient to enter appointment times."}
          </p>
        )}
      </div>
    </Modal>
  );
}
