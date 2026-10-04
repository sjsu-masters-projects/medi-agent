export function resolveSchedulingTimezone(value?: string | null) {
  const timezone = value?.trim();
  if (timezone) {
    try {
      new Intl.DateTimeFormat("en-US", { timeZone: timezone }).format();
      return { timezone, fallback: false };
    } catch {
      /* Use an explicitly labelled UTC fallback. */
    }
  }
  return { timezone: "UTC", fallback: true };
}

function wallTimeParts(instant: number, timezone: string): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(instant);
  const get = (type: string) => parts.find((part) => part.type === type)?.value;
  return `${get("year")}-${get("month")}-${get("day")}T${get("hour")}:${get("minute")}`;
}

// datetime-local has no timezone. Resolve its wall-clock value explicitly rather
// than letting Date interpret it in the browser's timezone. Reject DST ambiguity.
export function appointmentTimeToUtc(value: string, timezone: string): string {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) {
    throw new Error("Enter a date and time for every option.");
  }
  const wall = Date.parse(`${value}:00Z`);
  if (!Number.isFinite(wall) || wallTimeParts(wall, "UTC") !== value) {
    throw new Error("Enter a valid appointment date and time.");
  }
  const offsets = new Set(
    [-36, -12, 0, 12, 36].map((hours) => {
      const sample = wall + hours * 3_600_000;
      return Date.parse(`${wallTimeParts(sample, timezone)}:00Z`) - sample;
    }),
  );
  const matches = [...offsets]
    .map((offset) => wall - offset)
    .filter((instant) => wallTimeParts(instant, timezone) === value);
  if (matches.length !== 1) {
    throw new Error(
      matches.length === 0
        ? `That time does not exist in ${timezone} because of a clock change. Choose another time.`
        : `That time occurs twice in ${timezone} because of a clock change. Choose another time.`,
    );
  }
  return new Date(matches[0]!).toISOString();
}

export function validateAppointmentTimes(
  values: string[],
  timezone: string,
  now = Date.now(),
) {
  if (values.length < 2 || values.length > 4) {
    throw new Error("Offer between 2 and 4 appointment times.");
  }
  const slots = values.map((value) => appointmentTimeToUtc(value, timezone));
  if (new Set(slots).size !== slots.length)
    throw new Error("Offer distinct appointment times.");
  if (slots.some((slot) => Date.parse(slot) <= now))
    throw new Error("Offer future appointment times.");
  return slots.sort();
}

export function formatSchedulingTime(value: string, timezone: string) {
  const date = new Date(value);
  if (!Number.isFinite(date.getTime())) return "Appointment time unavailable";
  return new Intl.DateTimeFormat("en-US", {
    timeZone: timezone,
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}
