"use client";

import { useLayoutEffect, useRef, type TextareaHTMLAttributes } from "react";
import { useSharedPatientProfile } from "@/contexts/patient-profile-context";

/** A usable saved time zone, else undefined (the browser's own zone). */
function usableZone(timeZone?: string | null) {
  if (!timeZone) return undefined;
  try {
    new Intl.DateTimeFormat("en-US", { timeZone });
    return timeZone;
  } catch {
    return undefined;
  }
}

/** The patient's saved time zone for message times (UX-007). */
export function useSavedTimezone() {
  return useSharedPatientProfile()?.profile?.timezone ?? undefined;
}

/**
 * "11:03", "Yesterday" or "Oct 3" for a message, judged in the patient's saved time zone so
 * a device set to another zone does not move a message to the wrong day.
 */
export function chatDisplayTime(timestamp: Date | string, locale: string, now = new Date(), timeZone?: string | null) {
  const date = timestamp instanceof Date ? timestamp : new Date(timestamp);
  if (Number.isNaN(date.getTime())) return "";
  const zone = usableZone(timeZone);
  const dayFormatter = new Intl.DateTimeFormat("en-CA", { timeZone: zone, year: "numeric", month: "2-digit", day: "2-digit" });
  const dayKey = (value: Date) => dayFormatter.format(value);
  const today = dayKey(now);
  const messageDay = dayKey(date);
  if (messageDay === today)
    return new Intl.DateTimeFormat(locale, { hour: "numeric", minute: "2-digit", timeZone: zone }).format(date);
  const yesterday = new Date(`${today}T12:00:00Z`);
  yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  if (messageDay === yesterday.toISOString().slice(0, 10))
    return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(-1, "day");
  const sameYear = messageDay.slice(0, 4) === today.slice(0, 4);
  return new Intl.DateTimeFormat(locale, { month: "short", day: "numeric", timeZone: zone, ...(sameYear ? {} : { year: "numeric" }) }).format(date);
}

export function ChatTextarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const field = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const element = field.current;
    if (!element) return;
    element.style.height = "0px";
    element.style.height = `${Math.max(44, Math.min(element.scrollHeight, 104))}px`;
  }, [props.value]);
  return <textarea {...props} ref={field} rows={1} className={`min-h-11 min-w-0 w-full resize-none bg-transparent px-4 py-3 text-base leading-[22px] text-ink placeholder:text-muted ${props.className ?? ""}`} />;
}

export const chatButton = "min-h-11 rounded-[14px] border border-line-strong bg-surface px-3 py-2 text-sm font-medium text-ink-2 transition-transform active:scale-[0.98] disabled:opacity-50";
