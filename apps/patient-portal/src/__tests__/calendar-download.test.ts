import { afterEach, expect, it, vi } from "vitest";
import { saveAppointmentCalendar } from "../../../../packages/shared/src/utils/appointment-calendar";

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

it("downloads a calendar Blob, removes the link, and releases its temporary URL", () => {
  vi.useFakeTimers();
  const createObjectURL = vi.fn<(blob: Blob) => string>(() => "blob:synthetic");
  const revokeObjectURL = vi.fn();
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  let clicked: { href: string; download: string } | undefined;
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicked = { href: this.href, download: this.download };
  });
  saveAppointmentCalendar({
    filename: "appointment-test.ics",
    content: "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
  });
  expect(createObjectURL.mock.calls[0]?.[0]).toBeInstanceOf(Blob);
  expect((createObjectURL.mock.calls[0]?.[0] as Blob).type).toBe(
    "text/calendar;charset=utf-8",
  );
  expect(clicked?.download).toBe("appointment-test.ics");
  expect(clicked?.href).toBe("blob:synthetic");
  expect(document.querySelector("a[download]")).toBeNull();
  expect(revokeObjectURL).not.toHaveBeenCalled();
  vi.runAllTimers();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:synthetic");
});
