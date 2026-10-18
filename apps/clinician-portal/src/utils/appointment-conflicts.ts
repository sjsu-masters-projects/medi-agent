export interface ScheduleConflict {
  slot: string;
  clinicId?: string;
  clinicName: string;
  startsAt: string;
  endsAt: string;
}

/**
 * Reads the structured conflicts of a CLINICIAN_SCHEDULE_CONFLICT refusal. Server prose is never
 * returned; null means the error is something else.
 */
export function getScheduleConflicts(error: unknown): ScheduleConflict[] | null {
  const body = (error as { details?: { error?: unknown } } | null)?.details?.error;
  if (!body || typeof body !== "object") return null;
  const { code, details } = body as { code?: unknown; details?: { conflicts?: unknown } };
  if (code !== "CLINICIAN_SCHEDULE_CONFLICT" || !Array.isArray(details?.conflicts)) return null;
  const rows: ScheduleConflict[] = [];
  for (const item of details.conflicts as Record<string, unknown>[]) {
    if (
      typeof item?.slot === "string" &&
      typeof item.starts_at === "string" &&
      typeof item.ends_at === "string"
    ) {
      rows.push({
        slot: item.slot,
        clinicId: typeof item.clinic_id === "string" ? item.clinic_id : undefined,
        clinicName: typeof item.clinic_name === "string" && item.clinic_name ? item.clinic_name : "another clinic",
        startsAt: item.starts_at,
        endsAt: item.ends_at,
      });
    }
  }
  return rows.length ? rows : null;
}
