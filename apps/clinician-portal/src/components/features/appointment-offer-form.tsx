"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button, Card, Input } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
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
    <Card padding="none" className="min-w-0">
      <form
        aria-label="Appointment offer"
        onSubmit={(event) => void submit(event)}
      >
        <div className="border-b border-line px-5 py-4">
          <h2 className="text-[15px] font-semibold text-ink">
            {previous ? "Offer new times" : "Offer appointment times"}
          </h2>
          <p className="mt-1 text-[13px] text-muted">
            Enter 2–4 options in{" "}
            <strong className="font-mono text-xs font-medium text-ink-2">
              {timezone}
            </strong>
            . The patient chooses one.
          </p>
          <p className="mt-1 text-[13px] text-muted">
            Offers expire after seven days. Each time is unavailable once it
            starts.
          </p>
          {previous && (
            <p className="mt-3 flex items-start gap-2.5 rounded-xl border border-primary-line bg-primary-tint px-3.5 py-2.5 text-[13px] text-ink-2">
              <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
              <span>
                This creates a new offer and keeps the previous response and
                note.
              </span>
            </p>
          )}
        </div>
        <fieldset
          disabled={disabled || sending}
          className="min-w-0 space-y-4 px-5 py-5"
        >
          <div className="space-y-3">
            {times.map((time, index) => (
              <div key={index} className="flex items-end gap-2">
                <div className="min-w-0 flex-1">
                  <Input
                    label={`Option ${index + 1} (${timezone})`}
                    type="datetime-local"
                    className="font-mono"
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
                    className="h-[42px]"
                    aria-label={`Remove option ${index + 1}`}
                    onClick={() =>
                      setTimes((current) =>
                        current.filter((_, i) => i !== index),
                      )
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
          <Button type="submit" size="lg" fullWidth>
            <Icon name="send" className="h-4 w-4" />
            {sending ? "Sending offer…" : "Send appointment offer"}
          </Button>
        </fieldset>
        {error && (
          <div className="px-5 pb-5">
            <p
              role="alert"
              className="flex items-start gap-2.5 rounded-xl border border-risk-line bg-risk-soft px-4 py-3 text-sm text-risk-ink"
            >
              <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{error}</span>
            </p>
          </div>
        )}
      </form>
    </Card>
  );
}
