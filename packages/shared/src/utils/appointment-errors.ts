export type AppointmentErrorCode =
  | "APPOINTMENT_CONFLICT"
  | "APPOINTMENT_EXPIRED"
  | "APPOINTMENT_UNAVAILABLE"
  | "APPOINTMENT_PAST";

/** Read only documented codes; never show database or server prose as page copy. */
export function getAppointmentErrorCode(error: unknown): AppointmentErrorCode | null {
  if (!error || typeof error !== "object" || !("details" in error)) return null;
  const details = error.details;
  if (!details || typeof details !== "object" || !("error" in details)) return null;
  const apiError = details.error;
  if (!apiError || typeof apiError !== "object" || !("code" in apiError)) return null;
  switch (apiError.code) {
    case "APPOINTMENT_CONFLICT":
    case "APPOINTMENT_EXPIRED":
    case "APPOINTMENT_UNAVAILABLE":
    case "APPOINTMENT_PAST":
      return apiError.code;
    default:
      return null;
  }
}
