import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VisitsPage from "@/app/(app)/visits/page";
import type { Appointment, Locale } from "@/types";

const mocks = vi.hoisted(() => ({
  fetchVisits: vi.fn(),
  respondToVisit: vi.fn(),
}));
let locale: Locale;
vi.mock("react-redux", () => ({
  useSelector: (selector: (state: unknown) => unknown) =>
    selector({ auth: { accessToken: "synthetic-session" } }),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: vi.fn() }),
}));
vi.mock("@/hooks/use-patient-profile", () => ({
  usePatientProfileState: () => ({
    profile: { preferredLanguage: locale, timezone: "America/Los_Angeles" },
    loading: false,
    error: false,
    timezoneMissing: false,
    refresh: vi.fn(),
  }),
}));
vi.mock("@/services/appointments", async (original) => ({
  ...(await original<typeof import("@/services/appointments")>()),
  ...mocks,
}));
const visit: Appointment = {
  id: "synthetic-slot",
  patientId: "synthetic-patient",
  careTeamId: "synthetic-team",
  proposalGroupId: "synthetic-offer",
  scheduledAt: "2099-10-01T16:00:00Z",
  durationMinutes: 30,
  appointmentType: "follow_up",
  status: "proposed",
  createdAt: "2026-10-01T00:00:00Z",
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  locale = "en-US";
  mocks.fetchVisits.mockReset();
  mocks.respondToVisit.mockReset();
  mocks.fetchVisits.mockResolvedValue([visit]);
});

describe("Visits recovery with the real data hook", () => {
  it("keeps an unsent offer note mounted during and after focus refresh", async () => {
    render(<VisitsPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Request different times" }),
    );
    const input = screen.getByRole("textbox");
    fireEvent.change(input, {
      target: { value: "Synthetic note: afternoons please" },
    });
    const pending = deferred<Appointment[]>();
    mocks.fetchVisits.mockReturnValueOnce(pending.promise);
    act(() => {
      window.dispatchEvent(new Event("focus"));
    });
    expect(input).toBeInTheDocument();
    expect(input).toHaveValue("Synthetic note: afternoons please");
    expect(screen.getByRole("button", { name: "Send request" })).toBeDisabled();
    await act(async () => {
      pending.resolve([visit]);
    });
    expect(screen.getByRole("textbox")).toBe(input);
    expect(input).toHaveValue("Synthetic note: afternoons please");
    expect(screen.getByRole("button", { name: "Send request" })).toBeEnabled();
  });

  it.each(["en-US", "es-MX"] as const)(
    "retains the note and blocks stale actions after a failed %s focus refresh",
    async (language) => {
      locale = language;
      const spanish = language === "es-MX";
      render(<VisitsPage />);
      fireEvent.click(
        await screen.findByRole("button", {
          name: spanish
            ? "Solicitar otros horarios"
            : "Request different times",
        }),
      );
      fireEvent.change(screen.getByRole("textbox"), {
        target: { value: "Synthetic draft" },
      });
      mocks.fetchVisits.mockRejectedValueOnce(
        new Error("private server detail"),
      );
      await act(async () => {
        window.dispatchEvent(new Event("focus"));
      });
      expect(screen.getByRole("alert")).toHaveTextContent(
        spanish
          ? "Intenta cargar tus citas de nuevo"
          : "Please try loading your visits again",
      );
      expect(
        screen.queryByText("private server detail"),
      ).not.toBeInTheDocument();
      expect(screen.getByRole("textbox")).toHaveValue("Synthetic draft");
      const sendLabel = spanish ? "Enviar solicitud" : "Send request";
      expect(screen.getByRole("button", { name: sendLabel })).toBeDisabled();
      fireEvent.click(
        screen.getByRole("button", {
          name: spanish ? "Intentar de nuevo" : "Try again",
        }),
      );
      await waitFor(() =>
        expect(screen.getByRole("button", { name: sendLabel })).toBeEnabled(),
      );
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.getByRole("textbox")).toHaveValue("Synthetic draft");
    },
  );

  it("retries a failed cancellation with the original note", async () => {
    const booked = { ...visit, status: "confirmed" as const };
    mocks.fetchVisits.mockResolvedValue([booked]);
    mocks.respondToVisit.mockRejectedValueOnce(new Error("network failure"));
    render(<VisitsPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Cancel visit" }),
    );
    const note = "Synthetic note: transport unavailable";
    fireEvent.change(screen.getByRole("textbox"), { target: { value: note } });
    expect(screen.getByRole("textbox")).toHaveAttribute("maxlength", "1000");
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm cancellation" }),
    );
    await screen.findByRole("alert");
    expect(screen.getByRole("textbox")).toHaveValue(note);
    const cancelled = {
      ...booked,
      status: "cancelled" as const,
      patientNote: note,
    };
    mocks.respondToVisit.mockResolvedValueOnce(cancelled);
    mocks.fetchVisits.mockResolvedValue([cancelled]);
    fireEvent.click(
      screen.getByRole("button", { name: "Confirm cancellation" }),
    );
    await screen.findByText("Cancelled");
    expect(mocks.respondToVisit).toHaveBeenNthCalledWith(
      2,
      visit.id,
      "cancel",
      "synthetic-session",
      note,
    );
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("retains a saved-response warning through a failed retry and clears it after recovery", async () => {
    mocks.fetchVisits
      .mockResolvedValueOnce([visit])
      .mockRejectedValueOnce(new Error("follow-up failed"))
      .mockRejectedValueOnce(new Error("retry failed"))
      .mockResolvedValue([{ ...visit, status: "confirmed" }]);
    mocks.respondToVisit.mockResolvedValue({ ...visit, status: "confirmed" });
    render(<VisitsPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: /^Choose this time:/ }),
    );
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Refresh visits" }));
    await screen.findByText("Please try loading your visits again.");
    expect(screen.getByText(/Your response was saved/)).toBeInTheDocument();
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(screen.queryAllByRole("alert")).toHaveLength(0));
    expect(mocks.fetchVisits).toHaveBeenCalledTimes(4);
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
  });
});
