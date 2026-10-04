"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Card, Input } from "@/components/ui";
import { proposeAppointmentOffer } from "@/services/appointments";
import { validateAppointmentTimes } from "@/utils/appointment-times";
import type { Appointment } from "@/types";
import { getAppointmentErrorCode } from "../../../../../packages/shared/src/utils/appointment-errors";

interface Props {
  token: string;
  careTeamId: string;
  timezone: string;
  disabled: boolean;
  previous?: Appointment;
  onCreated: (appointments: Appointment[]) => void;
  onSendingChange: (sending: boolean) => void;
}

export function AppointmentOfferForm({
  token,
  careTeamId,
  timezone,
  disabled,
  previous,
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
  const [sending, setSending] = useState(false);
  const pending = useRef(false);
  const active = useRef(true);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (disabled || pending.current) return;
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
      if (active.current)
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
    <Card>
      <form
        aria-label="Appointment offer"
        onSubmit={(event) => void submit(event)}
        className="space-y-4"
      >
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            {previous ? "Offer new times" : "Offer appointment times"}
          </h2>
          <p className="text-sm text-gray-600">
            Enter 2–4 options in <strong>{timezone}</strong>. The patient
            chooses one.
          </p>
          <p className="mt-1 text-sm text-gray-600">
            Offers expire after seven days. Each time is unavailable once it
            starts.
          </p>
          {previous && (
            <p className="mt-1 text-sm text-gray-600">
              This creates a new offer and keeps the previous response and note.
            </p>
          )}
        </div>
        <fieldset disabled={disabled || sending} className="space-y-4">
          {times.map((time, index) => (
            <div key={index} className="flex items-end gap-3">
              <div className="flex-1">
                <Input
                  label={`Option ${index + 1} (${timezone})`}
                  type="datetime-local"
                  required
                  value={time}
                  onChange={(event) =>
                    setTimes((current) =>
                      current.map((value, i) =>
                        i === index ? event.target.value : value,
                      ),
                    )
                  }
                />
              </div>
              {times.length > 2 && (
                <Button
                  variant="ghost"
                  aria-label={`Remove option ${index + 1}`}
                  onClick={() =>
                    setTimes((current) => current.filter((_, i) => i !== index))
                  }
                >
                  Remove
                </Button>
              )}
            </div>
          ))}
          {times.length < 4 && (
            <Button
              variant="secondary"
              onClick={() => setTimes((current) => [...current, ""])}
            >
              Add another time
            </Button>
          )}
          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label="Duration (minutes)"
              type="number"
              min={5}
              max={480}
              step={1}
              required
              value={duration}
              onChange={(event) => setDuration(event.target.value)}
            />
            <label className="block text-sm font-medium text-gray-700">
              Appointment type
              <select
                className="mt-1 w-full rounded-lg border border-gray-300 px-3 py-2"
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
          <Button type="submit">
            {sending ? "Sending offer…" : "Send appointment offer"}
          </Button>
        </fieldset>
        {error && (
          <p role="alert" className="text-sm text-red-700">
            {error}
          </p>
        )}
      </form>
    </Card>
  );
}
