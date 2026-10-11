"use client";

import { useState } from "react";
import { Button } from "@/components/ui";
import { formatVisitTime, type VisitsCopy } from "@/content/visits-copy";
import type { AppointmentResponseAction } from "@/services/appointments";
import type { Appointment, Locale } from "@/types";

interface OfferProps {
  slots: Appointment[];
  copy: VisitsCopy;
  locale: Locale;
  timezone: string;
  now: number;
  responding: boolean;
  onRespond: (
    id: string,
    action: AppointmentResponseAction,
    note?: string,
  ) => void;
}

export function VisitOfferCard({
  slots,
  copy,
  locale,
  timezone,
  now,
  responding,
  onRespond,
}: OfferProps) {
  const [composing, setComposing] = useState<
    "decline" | "request_alternative" | null
  >(null);
  const [note, setNote] = useState("");
  const first = slots[0];
  const composeCopy =
    composing === "decline"
      ? copy.offerDecline
      : copy.compose.request_alternative;
  const noteId = `offer-note-${first.id}`;
  return (
    <article className="border-b border-line px-[14px] py-[13px] last:border-b-0">
      <h3 className="text-[15px] font-semibold text-ink">{copy.offerTitle}</h3>
      <p className="mt-2 text-sm text-muted">
        {copy.types[first.appointmentType]} · {first.durationMinutes}{" "}
        {copy.minutes}
      </p>
      {first.clinicianName ? (
        <p className="mt-2 break-words text-sm text-ink-2">
          {copy.with} {first.clinicianName}
        </p>
      ) : null}
      {first.reason ? (
        <p className="break-words text-sm text-ink-2">{first.reason}</p>
      ) : null}
      {first.location ? (
        <p className="break-words text-sm text-ink-2">{first.location}</p>
      ) : null}
      <p className="mt-2 break-words text-[13px] text-muted">{timezone}</p>
      {first.notes &&
      slots.some((slot) => Date.parse(slot.scheduledAt) >= now) ? (
        <div className="mt-3 rounded-xl bg-surface-2 p-3 text-sm text-ink-2">
          <p className="font-semibold">{copy.preparationNotes}</p>
          <p className="mt-1 whitespace-pre-wrap break-words">{first.notes}</p>
        </div>
      ) : null}
      <ul className="mt-3 space-y-3">
        {slots.map((slot) => {
          const when = formatVisitTime(slot.scheduledAt, locale, timezone);
          return (
            <li key={slot.id}>
              <Button
                className="min-h-11 h-auto !justify-start whitespace-normal rounded-2xl border border-line-strong !bg-surface py-3 text-left hover:!border-brand/50 hover:!bg-brand-tint/40"
                fullWidth
                disabled={responding || !when}
                aria-label={`${copy.choose}: ${when ?? copy.invalidDate} (${timezone})`}
                onClick={() => onRespond(slot.id, "accept")}
                variant="secondary"
              >
                <span className="min-w-0 break-words">
                  <span className="font-mono text-[15px] leading-6">
                    {when ?? copy.invalidDate}
                  </span>
                  <span className="mt-1 block text-sm text-brand-ink">
                    {copy.choose}
                  </span>
                  {slot.proposalExpiresAt && (
                    <span className="mt-1 block text-xs leading-5 text-muted">
                      {copy.availableUntil}{" "}
                      {formatVisitTime(
                        slot.proposalExpiresAt,
                        locale,
                        timezone,
                      )}
                    </span>
                  )}
                </span>
              </Button>
            </li>
          );
        })}
      </ul>
      {composing ? (
        <div className="mt-4 space-y-3">
          <label
            className="block text-sm font-semibold text-ink-2"
            htmlFor={noteId}
          >
            {composeCopy.label}
          </label>
          <textarea
            className="min-h-24 w-full rounded-2xl border border-line-strong bg-surface px-4 py-3 text-base text-ink outline-none transition placeholder:text-muted focus:border-brand focus:ring-4 focus:ring-brand/15"
            id={noteId}
            maxLength={1000}
            disabled={responding}
            value={note}
            rows={3}
            placeholder={composeCopy.placeholder}
            onChange={(event) => setNote(event.target.value)}
          />
          <div className="flex flex-wrap gap-3 [&_button]:min-h-11">
            <Button
              disabled={responding}
              onClick={() => onRespond(first.id, composing, note)}
            >
              {composeCopy.confirm}
            </Button>
            <Button
              disabled={responding}
              variant="ghost"
              onClick={() => {
                setComposing(null);
                setNote("");
              }}
            >
              {copy.back}
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-4 flex flex-wrap gap-2 [&_button]:min-h-11">
          <Button
            disabled={responding}
            variant="secondary"
            onClick={() => {
              setComposing("decline");
              setNote("");
            }}
          >
            {copy.declineOffer}
          </Button>
          <Button
            disabled={responding}
            variant="ghost"
            onClick={() => {
              setComposing("request_alternative");
              setNote("");
            }}
          >
            {copy.differentTimes}
          </Button>
        </div>
      )}
    </article>
  );
}
