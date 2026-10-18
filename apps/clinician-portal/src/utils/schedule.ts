import type { NeedsActionItem, ScheduleVisit } from "@/services/appointments";

export type AgendaMode = "day" | "week";

function localMidnight(moment: Date, plusDays = 0): Date {
  return new Date(moment.getFullYear(), moment.getMonth(), moment.getDate() + plusDays);
}

/** The agenda range in the browser's timezone: today, or today plus the next six days. */
export function agendaRange(mode: AgendaMode, now: Date): { from: Date; to: Date } {
  return { from: localMidnight(now), to: localMidnight(now, mode === "day" ? 1 : 7) };
}

export interface AgendaDay {
  key: string;
  label: string;
  isToday: boolean;
  visits: ScheduleVisit[];
}

function dayKey(moment: Date): string {
  return `${moment.getFullYear()}-${moment.getMonth() + 1}-${moment.getDate()}`;
}

/** "Today · Sat Oct 17", "Mon Oct 19". */
export function dayLabel(moment: Date, now: Date): string {
  const text = new Intl.DateTimeFormat("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
  })
    .format(moment)
    .replace(",", "");
  return dayKey(moment) === dayKey(now) ? `Today · ${text}` : text;
}

/** Visits grouped by calendar day (browser timezone), earliest first. */
export function groupByDay(visits: ScheduleVisit[], now: Date): AgendaDay[] {
  const days = new Map<string, AgendaDay>();
  const ordered = [...visits].sort((a, b) => Date.parse(a.scheduledAt) - Date.parse(b.scheduledAt));
  for (const visit of ordered) {
    const moment = new Date(visit.scheduledAt);
    const key = dayKey(moment);
    const day = days.get(key) ?? {
      key,
      label: dayLabel(moment, now),
      isToday: key === dayKey(now),
      visits: [],
    };
    day.visits.push(visit);
    days.set(key, day);
  }
  return [...days.values()];
}

function browserZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone;
}

/** The start time in the visit's own timezone. */
export function visitTimeLabel(visit: ScheduleVisit): string {
  const zone = visit.patientTimezone || browserZone();
  const date = new Date(visit.scheduledAt);
  if (!Number.isFinite(date.getTime())) return "—";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: zone,
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

/** The zone name when the visit's timezone is not the browser's, otherwise null. */
export function visitZoneNote(visit: ScheduleVisit): string | null {
  const zone = visit.patientTimezone;
  if (!zone || zone === browserZone()) return null;
  return (
    new Intl.DateTimeFormat("en-US", { timeZone: zone, timeZoneName: "short" })
      .formatToParts(new Date(visit.scheduledAt))
      .find((part) => part.type === "timeZoneName")?.value ?? zone
  );
}

/** "9:00–9:30 AM" (or "11:30 AM–12:00 PM" across noon) in the given timezone. */
export function formatBusyRange(startsAt: string, endsAt: string, timezone: string): string {
  const part = (value: string) => {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: timezone,
      hour: "numeric",
      minute: "2-digit",
    }).formatToParts(new Date(value));
    const get = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
    return { time: `${get("hour")}:${get("minute")}`, meridiem: get("dayPeriod") };
  };
  const start = part(startsAt);
  const end = part(endsAt);
  return start.meridiem === end.meridiem
    ? `${start.time}–${end.time} ${end.meridiem}`
    : `${start.time} ${start.meridiem}–${end.time} ${end.meridiem}`;
}

export interface NeedsActionCounts {
  awaiting: number;
  expiringSoon: number;
  changeRequests: number;
  expired: number;
}

export function needsActionCounts(items: NeedsActionItem[]): NeedsActionCounts {
  return {
    awaiting: items.filter((item) => item.kind === "awaiting_reply").length,
    expiringSoon: items.filter((item) => item.kind === "awaiting_reply" && item.expiringSoon).length,
    changeRequests: items.filter((item) => item.kind === "change_request").length,
    expired: items.filter((item) => item.kind === "expired").length,
  };
}
