import { describe, expect, it } from "vitest";
import {
  appointmentTimeToUtc,
  formatSchedulingTime,
  resolveSchedulingTimezone,
  validateAppointmentTimes,
} from "@/utils/appointment-times";

describe("appointment times", () => {
  it.each([
    ["2027-01-05T09:00", "2027-01-05T17:00:00.000Z"],
    ["2027-07-05T09:00", "2027-07-05T16:00:00.000Z"],
    ["2027-07-05T23:30", "2027-07-06T06:30:00.000Z"],
  ])("converts %s in Los Angeles to %s", (value, expected) => {
    expect(appointmentTimeToUtc(value, "America/Los_Angeles")).toBe(expected);
  });
  it("rejects nonexistent and repeated DST wall times", () => {
    expect(() =>
      appointmentTimeToUtc("2027-03-14T02:30", "America/Los_Angeles"),
    ).toThrow("does not exist");
    expect(() =>
      appointmentTimeToUtc("2027-11-07T01:30", "America/Los_Angeles"),
    ).toThrow("occurs twice");
  });
  it("rejects invalid calendar dates and blank options", () => {
    expect(() => appointmentTimeToUtc("2027-02-30T09:00", "UTC")).toThrow(
      "valid appointment",
    );
    expect(() => appointmentTimeToUtc("", "UTC")).toThrow("every option");
  });
  it.each([undefined, null, "", "bad/timezone"])(
    "labels missing/invalid timezone %s as UTC",
    (zone) => {
      expect(resolveSchedulingTimezone(zone)).toEqual({
        timezone: "UTC",
        fallback: true,
      });
    },
  );
  it("preserves a valid saved timezone including UTC", () => {
    expect(resolveSchedulingTimezone("UTC")).toEqual({
      timezone: "UTC",
      fallback: false,
    });
  });
  it("requires 2–4 distinct future options and sorts their instants", () => {
    const now = Date.parse("2027-01-01T00:00Z");
    expect(
      validateAppointmentTimes(
        ["2027-01-06T09:00", "2027-01-05T09:00"],
        "UTC",
        now,
      ),
    ).toEqual(["2027-01-05T09:00:00.000Z", "2027-01-06T09:00:00.000Z"]);
    expect(() =>
      validateAppointmentTimes(["2027-01-05T09:00"], "UTC", now),
    ).toThrow("between 2 and 4");
    expect(() =>
      validateAppointmentTimes(Array(5).fill("2027-01-05T09:00"), "UTC", now),
    ).toThrow("between 2 and 4");
    expect(() =>
      validateAppointmentTimes(
        ["2027-01-05T09:00", "2027-01-05T09:00"],
        "UTC",
        now,
      ),
    ).toThrow("distinct");
    expect(() =>
      validateAppointmentTimes(
        ["2026-01-05T09:00", "2027-01-05T09:00"],
        "UTC",
        now,
      ),
    ).toThrow("future");
  });
  it("uses the explicit timezone for display as well as conversion", () => {
    expect(
      formatSchedulingTime("2027-07-06T06:30:00Z", "America/Los_Angeles"),
    ).toBe("Jul 5, 2027, 11:30 PM");
  });
});
