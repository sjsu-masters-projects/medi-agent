import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CalendarExportButton } from "@/components/features/calendar-export-button";
import { api } from "@/services/api";
import { saveAppointmentCalendar } from "../../../../packages/shared/src/utils/appointment-calendar";

vi.mock("@/services/api", () => ({ api: { get: vi.fn() } }));
vi.mock(
  "../../../../packages/shared/src/utils/appointment-calendar",
  async (original) => ({
    ...(await original<
      typeof import("../../../../packages/shared/src/utils/appointment-calendar")
    >()),
    saveAppointmentCalendar: vi.fn(),
  }),
);
const file = {
  filename: "appointment-synthetic.ics",
  content: "BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n",
};
beforeEach(() => {
  vi.clearAllMocks();
});

describe("calendar export", () => {
  it.each([
    ["en-US", "Add to calendar", "Changes and cancellations do not sync"],
    [
      "es-MX",
      "Agregar al calendario",
      "Los cambios y las cancelaciones no se sincronizan",
    ],
  ] as const)(
    "downloads the authorized file with %s copy",
    async (locale, label, notice) => {
      vi.mocked(api.get).mockResolvedValue(file);
      render(
        <CalendarExportButton
          token="synthetic-token"
          appointmentId="visit-1"
          locale={locale}
        />,
      );
      expect(screen.getByText(new RegExp(notice))).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: label }));
      await waitFor(() =>
        expect(saveAppointmentCalendar).toHaveBeenCalledWith(file),
      );
      expect(api.get).toHaveBeenCalledWith(
        `/api/v1/appointments/visit-1/calendar?locale=${locale}`,
        { token: "synthetic-token", cache: "no-store" },
      );
    },
  );

  it("keeps localized failure inline, hides raw server text, and permits retry", async () => {
    vi.mocked(api.get)
      .mockRejectedValueOnce(new Error("Raw English server detail"))
      .mockResolvedValueOnce(file);
    render(
      <CalendarExportButton
        token="synthetic-token"
        appointmentId="visit-1"
        locale="es-MX"
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Agregar al calendario" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No se pudo descargar esta cita",
    );
    expect(screen.queryByText(/Raw English/)).not.toBeInTheDocument();
    expect(saveAppointmentCalendar).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Agregar al calendario" }),
    );
    await waitFor(() => expect(saveAppointmentCalendar).toHaveBeenCalledOnce());
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("blocks double downloads and discards a late file after switching sessions", async () => {
    let finish!: (value: typeof file) => void;
    vi.mocked(api.get).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const { rerender } = render(
      <CalendarExportButton
        token="session-one"
        appointmentId="visit-1"
        locale="en-US"
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByRole("button")).toBeDisabled();
    fireEvent.click(screen.getByRole("button"));
    expect(api.get).toHaveBeenCalledOnce();
    rerender(
      <CalendarExportButton
        token="session-two"
        appointmentId="visit-1"
        locale="en-US"
      />,
    );
    await act(async () => {
      finish(file);
    });
    expect(saveAppointmentCalendar).not.toHaveBeenCalled();
    expect(screen.getByRole("button")).not.toBeDisabled();
  });

  it("discards a pending download when its card unmounts", async () => {
    let finish!: (value: typeof file) => void;
    vi.mocked(api.get).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const { unmount } = render(
      <CalendarExportButton
        token="session"
        appointmentId="visit-1"
        locale="en-US"
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    unmount();
    await act(async () => {
      finish(file);
    });
    expect(saveAppointmentCalendar).not.toHaveBeenCalled();
  });

  it("honors disabled state and hides the control without a session", () => {
    const { rerender } = render(
      <CalendarExportButton
        token="session"
        appointmentId="visit-1"
        locale="en-US"
        disabled
      />,
    );
    fireEvent.click(screen.getByRole("button"));
    expect(api.get).not.toHaveBeenCalled();
    rerender(
      <CalendarExportButton
        token={null}
        appointmentId="visit-1"
        locale="en-US"
      />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
