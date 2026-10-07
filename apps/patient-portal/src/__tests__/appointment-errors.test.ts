import { describe, expect, it } from "vitest";
import { getAppointmentErrorCode } from "../../../../packages/shared/src/utils/appointment-errors";

describe("appointment error codes", () => {
  it.each([
    "APPOINTMENT_CONFLICT",
    "APPOINTMENT_EXPIRED",
    "APPOINTMENT_UNAVAILABLE",
    "APPOINTMENT_PAST",
  ])("reads %s without depending on server messages", (code) => {
    expect(
      getAppointmentErrorCode({
        message: "private server detail",
        details: { error: { code } },
      }),
    ).toBe(code);
  });
  it.each([
    null,
    "APPOINTMENT_CONFLICT",
    new Error("APPOINTMENT_EXPIRED"),
    {},
    { details: null },
    { details: {} },
    { details: { error: null } },
    { details: { error: { code: "UNKNOWN" } } },
  ])("ignores undocumented or malformed errors: %j", (error) => {
    expect(getAppointmentErrorCode(error)).toBeNull();
  });
});
