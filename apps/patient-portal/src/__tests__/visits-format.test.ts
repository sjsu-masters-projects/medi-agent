import { describe, expect, it } from "vitest";
import { formatVisitTime, resolveVisitsTimezone } from "@/content/visits-copy";

describe("visit times", () => {
  it.each([
    ["2026-01-08T17:00:00Z", "en-US", "Thursday, January 8, 2026 at 9:00 AM"],
    ["2026-07-08T17:00:00Z", "en-US", "Wednesday, July 8, 2026 at 10:00 AM"],
    ["2026-07-08T01:00:00Z", "en-US", "Tuesday, July 7, 2026 at 6:00 PM"],
    ["2026-01-08T17:00:00Z", "es-MX", "jueves, 8 de enero de 2026, 9:00 a.m."],
    [
      "2026-07-08T17:00:00Z",
      "es-MX",
      "miércoles, 8 de julio de 2026, 10:00 a.m.",
    ],
    ["2026-07-08T01:00:00Z", "es-MX", "martes, 7 de julio de 2026, 6:00 p.m."],
  ] as const)(
    "formats %s in %s with daylight-saving and date rollover",
    (value, locale, expected) => {
      expect(formatVisitTime(value, locale, "America/Los_Angeles")).toBe(
        expected,
      );
    },
  );
  it("uses the explicit saved zone even when the process timezone differs", () => {
    const previous = process.env.TZ;
    try {
      process.env.TZ = "Asia/Tokyo";
      expect(
        formatVisitTime("2026-07-08T17:00:00Z", "en-US", "America/Los_Angeles"),
      ).toContain("10:00 AM");
      process.env.TZ = "America/New_York";
      expect(
        formatVisitTime("2026-07-08T17:00:00Z", "en-US", "America/Los_Angeles"),
      ).toContain("10:00 AM");
    } finally {
      if (previous === undefined) delete process.env.TZ;
      else process.env.TZ = previous;
    }
  });
  it("recognizes UTC as a valid saved zone", () => {
    expect(resolveVisitsTimezone("UTC")).toEqual({
      timezone: "UTC",
      fallback: false,
    });
  });
  it("handles malformed appointment timestamps without crashing", () => {
    expect(formatVisitTime("invalid", "en-US", "UTC")).toBeNull();
  });
});
