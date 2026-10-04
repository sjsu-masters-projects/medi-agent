"use client";

import { useState } from "react";
import { Button, Card } from "@/components/ui";
import { formatVisitTime, type VisitsCopy } from "@/content/visits-copy";
import type { AppointmentResponseAction } from "@/services/appointments";
import type { Appointment, Locale } from "@/types";

interface OfferProps {
  slots: Appointment[];
  copy: VisitsCopy;
  locale: Locale;
  timezone: string;
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
    <Card>
      <h3 className="text-base font-bold text-slate-900">{copy.offerTitle}</h3>
      {first.clinicianName ? (
        <p className="mt-2 text-sm text-slate-600">
          {copy.with} {first.clinicianName}
        </p>
      ) : null}
      {first.reason ? (
        <p className="text-sm text-slate-600">{first.reason}</p>
      ) : null}
      {first.location ? (
        <p className="text-sm text-slate-600">{first.location}</p>
      ) : null}
      <p className="mt-2 text-sm text-slate-600">{timezone}</p>
      <ul className="mt-3 space-y-3">
        {slots.map((slot) => {
          const when = formatVisitTime(slot.scheduledAt, locale, timezone);
          return (
            <li key={slot.id}>
              <Button
                fullWidth
                disabled={responding || !when}
                aria-label={`${copy.choose}: ${when ?? copy.invalidDate} (${timezone})`}
                onClick={() => onRespond(slot.id, "accept")}
                variant="secondary"
              >
                <span>
                  {when ?? copy.invalidDate}
                  <span className="block text-sm">{copy.choose}</span>
                  {slot.proposalExpiresAt && (
                    <span className="block text-xs">
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
            className="block text-sm font-semibold text-slate-700"
            htmlFor={noteId}
          >
            {composeCopy.label}
          </label>
          <textarea
            className="w-full rounded-xl border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:ring-2 focus:ring-blue-500"
            id={noteId}
            maxLength={1000}
            disabled={responding}
            value={note}
            rows={3}
            placeholder={composeCopy.placeholder}
            onChange={(event) => setNote(event.target.value)}
          />
          <div className="flex gap-3">
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
        <div className="mt-4 flex flex-wrap gap-3">
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
    </Card>
  );
}
