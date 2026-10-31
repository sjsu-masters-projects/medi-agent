"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Input } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { proposeAppointmentOffer, type BusyInterval } from "@/services/appointments";
import {
  appointmentTimeToUtc,
  formatSchedulingClock,
  timezoneName,
  validateAppointmentTimes,
} from "@/utils/appointment-times";
import { formatBusyRange } from "@/utils/schedule";
import { getScheduleConflicts, type ScheduleConflict } from "@/utils/appointment-conflicts";
import type { Appointment } from "@/types";
import { getAppointmentErrorCode } from "../../../../../packages/shared/src/utils/appointment-errors";

interface Props {
  token: string;
  careTeamId: string;
  timezone: string;
  disabled: boolean;
  previous?: Appointment;
  /** Name the clinic beside each busy time (multi-clinic clinicians only). */
  showClinic?: boolean;
  /** The clinician's own booked intervals in [from, to) across all clinics. */
  loadBusy: (from: string, to: string) => Promise<BusyInterval[]>;
  onCreated: (appointments: Appointment[]) => void;
  onSendingChange: (sending: boolean) => void;
}

export function AppointmentOfferForm({
  token,
  careTeamId,
  timezone,
  disabled,
  previous,
  showClinic = false,
  loadBusy,
  onCreated,
  onSendingChange,
}: Props) {
  const [times, setTimes] = useState(["", ""]);
  const [duration, setDuration] = useState(
    String(previous?.durationMinutes ?? 30),
  );
  const [reason, setReason] = useState(previous?.reason ?? "");
  const [location, setLocation] = useState(previous?.location ?? "");
  const [type, setType] = useState<Appointment["appointmentType"]>(
    previous?.appointmentType ?? "follow_up",
  );
  const [error, setError] = useState("");
  // One entry per slot input; a non-null entry is that slot's unresolved schedule conflict.
  const [conflicts, setConflicts] = useState<(ScheduleConflict | null)[]>([]);
  const blocked = conflicts.some(Boolean);
  const [sending, setSending] = useState(false);
  const pending = useRef(false);
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  // Busy times by chosen date (YYYY-MM-DD): the caller's own visits that day, all clinics.
  const [busy, setBusy] = useState<
    Record<string, { state: "loading" | "ready" | "error"; rows: BusyInterval[] }>
  >({});
  const requested = useRef(new Set<string>());
  const dates = [
    ...new Set(
      times
        .map((time) => time.slice(0, 10))
        .filter((date) => /^\d{4}-\d{2}-\d{2}$/.test(date)),
    ),
  ];
  const datesKey = dates.join(",");
  useEffect(() => {
    for (const date of datesKey ? datesKey.split(",") : []) {
      if (requested.current.has(date)) continue;
      requested.current.add(date);
      setBusy((current) => ({ ...current, [date]: { state: "loading", rows: [] } }));
      let from: number;
      try {
        from = Date.parse(appointmentTimeToUtc(`${date}T00:00`, timezone));
      } catch {
        from = Date.parse(`${date}T00:00:00Z`);
      }
      void loadBusy(new Date(from).toISOString(), new Date(from + 86_400_000).toISOString())
        .then((rows) => {
          if (active.current) setBusy((current) => ({ ...current, [date]: { state: "ready", rows } }));
        })
        .catch(() => {
          if (active.current) setBusy((current) => ({ ...current, [date]: { state: "error", rows: [] } }));
        });
    }
  }, [datesKey, timezone, loadBusy]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (disabled || pending.current || blocked) return;
    setError("");
    let slots: string[];
    try {
      slots = validateAppointmentTimes(times, timezone);
      if (
        !Number.isInteger(Number(duration)) ||
        Number(duration) < 5 ||
        Number(duration) > 480
      ) {
        throw new Error(
          "Duration must be a whole number between 5 and 480 minutes.",
        );
      }
    } catch (failure) {
      setError((failure as Error).message);
      return;
    }
    pending.current = true;
    setSending(true);
    onSendingChange(true);
    try {
      const rows = await proposeAppointmentOffer(token, {
        care_team_id: careTeamId,
        slots,
        duration_minutes: Number(duration),
        appointment_type: type,
        reason: reason.trim() || undefined,
        location: location.trim() || undefined,
      });
      if (active.current) onCreated(rows);
    } catch (failure) {
      const found = getScheduleConflicts(failure);
      const matched = found
        ? times.map((time) => {
            try {
              const utc = Date.parse(appointmentTimeToUtc(time, timezone));
              return found.find((c) => Date.parse(c.slot) === utc) ?? null;
            } catch {
              return null;
            }
          })
        : [];
      if (active.current && matched.some(Boolean)) {
        setConflicts(matched);
      } else if (active.current)
        setError(
          getAppointmentErrorCode(failure) === "APPOINTMENT_PAST"
            ? "One of these times has passed. Your draft is preserved; choose future times and send again."
            : "Could not send the offer. Your draft is preserved. Refresh appointments to check whether it was saved before trying again.",
        );
    } finally {
      pending.current = false;
      if (active.current) {
        setSending(false);
        onSendingChange(false);
      }
    }
  }

  return (
    <form
      aria-label="Appointment offer"
      className="flex min-h-0 flex-1 flex-col"
      onSubmit={(event) => void submit(event)}
    >
      <fieldset
        disabled={disabled || sending}
        className="m-0 flex min-h-0 min-w-0 flex-1 flex-col border-0 p-0"
      >
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-5 py-5">
          <p className="text-[13px] text-muted">
            Enter 2–4 options in{" "}
            <strong className="font-medium text-ink-2" title={timezone}>{timezoneName(timezone)}</strong>, the patient&apos;s time zone. The
            patient chooses one. Offers expire after seven days; each time is unavailable once it
            starts.
          </p>
          {previous && (
            <p className="flex items-start gap-2.5 rounded-xl border border-primary-line bg-primary-tint px-3.5 py-2.5 text-[13px] text-ink-2">
              <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <span>This creates a new offer and keeps the previous response and note.</span>
            </p>
          )}
          <div className="space-y-3">
            {times.map((time, index) => {
              const date = time.slice(0, 10);
              const day = busy[date];
              return (
                <div key={index} className="min-w-0">
                  <div className="flex items-end gap-2">
                    <div className="min-w-0 flex-1">
                      <Input
                        label={`Option ${index + 1} (${timezoneName(timezone)})`}
                        type="datetime-local"
                        className="font-mono"
                        required
                        value={time}
                        aria-describedby={
                          conflicts[index]
                            ? `slot-conflict-${index}`
                            : day
                              ? `slot-busy-${index}`
                              : undefined
                        }
                        onChange={(event) => {
                          setConflicts((current) =>
                            current.map((value, i) => (i === index ? null : value)),
                          );
                          setTimes((current) =>
                            current.map((value, i) =>
                              i === index ? event.target.value : value,
                            ),
                          );
                        }}
                      />
                    </div>
                    {times.length > 2 && (
                      <Button
                        variant="ghost"
                        className="h-[42px]"
                        aria-label={`Remove option ${index + 1}`}
                        onClick={() => {
                          setConflicts((current) => current.filter((_, i) => i !== index));
                          setTimes((current) => current.filter((_, i) => i !== index));
                        }}
                      >
                        Remove
                      </Button>
                    )}
                  </div>
                  {day && (
                    <div
                      id={`slot-busy-${index}`}
                      className="mt-1.5 text-xs text-muted"
                      aria-label={`Your booked times on ${date}`}
                    >
                      {day.state === "loading" && <p role="status">Checking your schedule…</p>}
                      {day.state === "error" && (
                        <p>Could not load your booked times. The server still checks for clashes.</p>
                      )}
                      {day.state === "ready" && day.rows.length === 0 && (
                        <p>Nothing else booked that day.</p>
                      )}
                      {day.state === "ready" && day.rows.length > 0 && (
                        <>
                          <p className="font-medium text-ink-2">Already booked that day</p>
                          <ul className="mt-0.5 space-y-0.5">
                            {day.rows.map((row) => (
                              <li className="break-words font-mono" key={`${row.startsAt}-${row.clinicId}`}>
                                {formatBusyRange(row.startsAt, row.endsAt, timezone)}
                                {showClinic && row.clinicName ? ` · ${row.clinicName}` : ""}
                              </li>
                            ))}
                          </ul>
                        </>
                      )}
                    </div>
                  )}
                  {conflicts[index] && (
                    <p
                      id={`slot-conflict-${index}`}
                      role="alert"
                      aria-live="assertive"
                      className="mt-2 flex items-start gap-2 rounded-xl border border-risk-line bg-risk-soft px-3 py-2 text-[13px] text-risk-ink"
                    >
                      <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
                      <span className="min-w-0 break-words">
                        {`You already have an appointment at ${conflicts[index].clinicName} from ${formatSchedulingClock(conflicts[index].startsAt, timezone)} to ${formatSchedulingClock(conflicts[index].endsAt, timezone)}.`}
                      </span>
                    </p>
                  )}
                </div>
              );
            })}
            {times.length < 4 && (
              <Button variant="secondary" onClick={() => setTimes((current) => [...current, ""])}>
                <Icon name="plus" className="h-4 w-4" />
                Add another time
              </Button>
            )}
          </div>
          <div className="grid gap-4 border-t border-line pt-4 sm:grid-cols-2">
            <Input
              label="Duration (minutes)"
              type="number"
              className="font-mono"
              min={5}
              max={480}
              step={1}
              required
              value={duration}
              onChange={(event) => setDuration(event.target.value)}
            />
            <label className="block">
              <span className="mb-1.5 block text-[13px] font-medium text-ink-2">
                Appointment type
              </span>
              <select
                className="h-[42px] w-full rounded-[10px] border border-line-strong bg-surface px-3.5 text-sm text-ink outline-none transition focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted"
                value={type}
                onChange={(event) =>
                  setType(event.target.value as Appointment["appointmentType"])
                }
              >
                <option value="follow_up">Follow-up</option>
                <option value="initial">Initial</option>
                <option value="routine">Routine</option>
                <option value="urgent">Urgent</option>
                <option value="pre_op">Pre-op</option>
              </select>
            </label>
            <Input
              label="Location (optional)"
              value={location}
              onChange={(event) => setLocation(event.target.value)}
            />
            <Input
              label="Reason (optional)"
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </div>
        </div>
        <div className="shrink-0 space-y-2 border-t border-line bg-surface px-5 py-3">
          {error && (
            <p
              role="alert"
              className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-3.5 py-2.5 text-[13px] text-risk-ink"
            >
              <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </p>
          )}
          {blocked ? (
            <p className="text-[13px] text-muted" id="offer-blocked-help">
              Change the conflicting time to send.
            </p>
          ) : null}
          <Button
            aria-describedby={blocked ? "offer-blocked-help" : undefined}
            type="submit"
            size="lg"
            fullWidth
            disabled={blocked}
          >
            <Icon name="send" className="h-4 w-4" />
            {sending ? "Sending offer…" : "Send offer"}
          </Button>
        </div>
      </fieldset>
    </form>
  );
}
