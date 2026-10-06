import { AppointmentStatus, type Appointment } from "@/types";

export function isUpcomingVisit(visit: Appointment, now: number): boolean {
  return (
    (visit.status === AppointmentStatus.CONFIRMED ||
      visit.status === AppointmentStatus.SCHEDULED) &&
    Date.parse(visit.scheduledAt) >= now
  );
}

/** Invalid timestamps remain visible after valid visits, never as upcoming. */
export function orderVisits(
  visits: Appointment[],
  direction: "ascending" | "descending",
): Appointment[] {
  return [...visits].sort((left, right) => {
    const leftTime = Date.parse(left.scheduledAt);
    const rightTime = Date.parse(right.scheduledAt);
    if (!Number.isFinite(leftTime)) return Number.isFinite(rightTime) ? 1 : 0;
    if (!Number.isFinite(rightTime)) return -1;
    return direction === "ascending"
      ? leftTime - rightTime
      : rightTime - leftTime;
  });
}
