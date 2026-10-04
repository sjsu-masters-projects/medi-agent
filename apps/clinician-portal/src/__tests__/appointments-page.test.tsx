import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Appointment } from "@/types";
const mocks = vi.hoisted(() => ({
  patients: vi.fn(),
  appointments: vi.fn(),
  profile: vi.fn(),
  propose: vi.fn(),
  state: { auth: { accessToken: "clinician-token" as string | null } },
}));
vi.mock("react-redux", () => ({
  useSelector: (selector: (state: typeof mocks.state) => unknown) =>
    selector(mocks.state),
}));
vi.mock("@/services/appointments", () => ({
  fetchSchedulingPatients: mocks.patients,
  fetchSchedulingAppointments: mocks.appointments,
  fetchSchedulingProfile: mocks.profile,
  proposeAppointmentOffer: mocks.propose,
}));
import AppointmentsPage from "@/app/(dashboard)/appointments/page";

const roster = [
  { id: "p1", care_team_id: "team1", first_name: "Maya", last_name: "Patel" },
  {
    id: "p2",
    care_team_id: "team2",
    first_name: "Hannah",
    last_name: "Brooks",
  },
];
function appointment(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: "a1",
    patientId: "p1",
    careTeamId: "team1",
    proposalGroupId: "g1",
    scheduledAt: "2027-07-05T16:00Z",
    durationMinutes: 30,
    appointmentType: "follow_up",
    status: "proposed",
    createdAt: "2026-09-28T00:00Z",
    ...overrides,
  };
}
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
async function selectPatient(value = "team1") {
  await screen.findByRole("combobox", { name: "Patient" });
  fireEvent.change(screen.getByRole("combobox", { name: "Patient" }), {
    target: { value },
  });
}
async function fillTimes() {
  fireEvent.change(
    await screen.findByLabelText("Option 1 (America/Los_Angeles)"),
    { target: { value: "2027-07-05T09:00" } },
  );
  fireEvent.change(screen.getByLabelText("Option 2 (America/Los_Angeles)"), {
    target: { value: "2027-07-06T14:00" },
  });
}
function submit() {
  fireEvent.submit(screen.getByRole("form", { name: "Appointment offer" }));
}

describe("clinician appointments page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-09-28T00:00:00Z"));
    mocks.state.auth.accessToken = "clinician-token";
    mocks.patients.mockResolvedValue(roster);
    mocks.appointments.mockResolvedValue([]);
    mocks.profile.mockResolvedValue({ timezone: "America/Los_Angeles" });
    mocks.propose.mockResolvedValue([
      appointment(),
      appointment({ id: "a2", scheduledAt: "2027-07-06T21:00Z" }),
    ]);
  });
  afterEach(() => vi.restoreAllMocks());

  it("does not load scheduling data without a clinician session", () => {
    mocks.state.auth.accessToken = null;
    render(<AppointmentsPage />);
    expect(screen.getByRole("status")).toHaveTextContent(
      "Sign in as a clinician",
    );
    expect(mocks.patients).not.toHaveBeenCalled();
  });

  it("retries an initial load failure without showing raw server messages", async () => {
    mocks.patients.mockRejectedValueOnce(new Error("Raw authorization detail"));
    render(<AppointmentsPage />);
    await screen.findByRole("alert");
    expect(
      screen.queryByText("Raw authorization detail"),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(screen.getByRole("combobox", { name: "Patient" })).toBeEnabled(),
    );
    expect(
      screen.getByRole("option", { name: "Maya Patel" }),
    ).toBeInTheDocument();
  });
  it("supplies the selected care-team ID and timezone-correct slots automatically", async () => {
    render(<AppointmentsPage />);
    await selectPatient();
    await fillTimes();
    submit();
    await screen.findByText(/Appointment offer sent/);
    expect(mocks.propose).toHaveBeenCalledWith(
      "clinician-token",
      expect.objectContaining({
        care_team_id: "team1",
        slots: ["2027-07-05T16:00:00.000Z", "2027-07-06T21:00:00.000Z"],
        duration_minutes: 30,
      }),
    );
    expect(screen.getByLabelText("Appointment history")).toHaveTextContent(
      "Jul 5, 2027, 9:00 AM",
    );
    expect(screen.getByLabelText("Option 1 (America/Los_Angeles)")).toHaveValue(
      "",
    );
  });
  it("waits for settings and retries profile failure without exposing server text", async () => {
    const pending = deferred<{ timezone: string }>();
    mocks.profile.mockReturnValueOnce(pending.promise);
    render(<AppointmentsPage />);
    await selectPatient();
    expect(
      screen.getByText(/Loading the patient's timezone/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    await act(async () => pending.resolve({ timezone: "UTC" }));
    expect(await screen.findByLabelText("Option 1 (UTC)")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Patient" }), {
      target: { value: "team2" },
    });
    mocks.profile.mockRejectedValueOnce(new Error("private server detail"));
    fireEvent.change(screen.getByRole("combobox", { name: "Patient" }), {
      target: { value: "team1" },
    });
    await screen.findByText("Could not load the patient's timezone");
    expect(screen.queryByText("private server detail")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByLabelText("Option 1 (America/Los_Angeles)");
  });
  it.each([undefined, "Invalid/Zone"])(
    "labels fallback %s as UTC",
    async (timezone) => {
      mocks.profile.mockResolvedValue({ timezone });
      render(<AppointmentsPage />);
      await selectPatient();
      await screen.findByLabelText("Option 1 (UTC)");
      expect(screen.getByText(/no valid saved timezone/)).toBeInTheDocument();
    },
  );
  it("preserves a failed offer draft and visible history", async () => {
    mocks.appointments.mockResolvedValue([
      appointment({ status: "confirmed", reason: "Existing visit" }),
    ]);
    mocks.propose.mockRejectedValue(new Error("Raw English failure"));
    render(<AppointmentsPage />);
    await selectPatient();
    await fillTimes();
    submit();
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Your draft is preserved",
    );
    expect(screen.getByText("Existing visit")).toBeInTheDocument();
    expect(screen.getByLabelText("Option 1 (America/Los_Angeles)")).toHaveValue(
      "2027-07-05T09:00",
    );
    expect(screen.queryByText("Raw English failure")).not.toBeInTheDocument();
  });
  it("disables patient changes, refresh, and duplicate submissions while sending", async () => {
    const pending = deferred<Appointment[]>();
    mocks.propose.mockReturnValue(pending.promise);
    render(<AppointmentsPage />);
    await selectPatient();
    await fillTimes();
    submit();
    submit();
    expect(mocks.propose).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("combobox", { name: "Patient" })).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Refresh appointments" }),
    ).toBeDisabled();
    await act(async () => pending.resolve([appointment()]));
    await screen.findByText(/Appointment offer sent/);
  });
  it("refreshes persisted responses and excludes another patient's/clinician's records", async () => {
    mocks.appointments.mockResolvedValueOnce([
      appointment(),
      appointment({ id: "a2" }),
      appointment({ id: "foreign", patientId: "p2", reason: "Other patient" }),
      appointment({
        id: "other-team",
        careTeamId: "other",
        reason: "Other clinician",
      }),
    ]);
    render(<AppointmentsPage />);
    await selectPatient();
    await screen.findByRole("form");
    expect(screen.queryByText("Other patient")).not.toBeInTheDocument();
    expect(screen.queryByText("Other clinician")).not.toBeInTheDocument();
    mocks.appointments.mockResolvedValue([
      appointment({
        status: "confirmed",
        patientNote: "Gracias, works for me",
      }),
      appointment({ id: "a2", status: "withdrawn" }),
    ]);
    fireEvent.click(
      screen.getByRole("button", { name: "Refresh appointments" }),
    );
    await screen.findByText(/Gracias, works for me/);
    const history = screen.getByLabelText("Appointment history");
    expect(history).toHaveTextContent("Confirmed");
    expect(history).toHaveTextContent("Withdrawn");
  });
  it.each(["declined", "alternative_requested"] as const)(
    "re-proposes after %s while preserving history and note",
    async (status) => {
      mocks.appointments.mockResolvedValue([
        appointment({
          status,
          patientNote: "Please offer afternoons",
          reason: "Original reason",
          location: "Telehealth",
        }),
      ]);
      render(<AppointmentsPage />);
      await selectPatient();
      await screen.findByRole("form");
      fireEvent.click(screen.getByRole("button", { name: "Offer new times" }));
      expect(screen.getByLabelText("Reason (optional)")).toHaveValue(
        "Original reason",
      );
      expect(screen.getByLabelText("Location (optional)")).toHaveValue(
        "Telehealth",
      );
      await fillTimes();
      mocks.propose.mockResolvedValue([
        appointment({ id: "new", proposalGroupId: "g2" }),
      ]);
      submit();
      await screen.findByText(/Appointment offer sent/);
      const history = screen.getByLabelText("Appointment history");
      expect(history).toHaveTextContent("Please offer afternoons");
      expect(
        within(history).getAllByText("Awaiting patient response").length,
      ).toBeGreaterThan(0);
      expect(mocks.propose.mock.calls[0]?.[1]).not.toHaveProperty(
        "proposal_group_id",
      );
    },
  );
  it("preserves loaded appointments when refresh fails, and retries", async () => {
    mocks.appointments
      .mockResolvedValueOnce([appointment({ reason: "Keep visible" })])
      .mockRejectedValueOnce(new Error("private details"));
    render(<AppointmentsPage />);
    await selectPatient();
    await screen.findByText("Keep visible");
    fireEvent.click(
      screen.getByRole("button", { name: "Refresh appointments" }),
    );
    await screen.findByRole("alert");
    expect(screen.getByText("Keep visible")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Send appointment offer" }),
    ).toBeDisabled();
    mocks.appointments.mockResolvedValue([
      appointment({ reason: "Keep visible" }),
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(screen.queryByRole("alert")).not.toBeInTheDocument(),
    );
  });
  it("supports 2–4 options and blocks duplicates and past dates before POST", async () => {
    render(<AppointmentsPage />);
    await selectPatient();
    await fillTimes();
    fireEvent.click(screen.getByRole("button", { name: "Add another time" }));
    fireEvent.click(screen.getByRole("button", { name: "Add another time" }));
    expect(
      screen.queryByRole("button", { name: "Add another time" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove option 4" }));
    fireEvent.click(screen.getByRole("button", { name: "Remove option 3" }));
    fireEvent.change(screen.getByLabelText("Option 2 (America/Los_Angeles)"), {
      target: { value: "2027-07-05T09:00" },
    });
    submit();
    expect(screen.getByRole("alert")).toHaveTextContent("distinct");
    expect(mocks.propose).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Option 2 (America/Los_Angeles)"), {
      target: { value: "2020-07-05T09:00" },
    });
    submit();
    expect(screen.getByRole("alert")).toHaveTextContent("future");
  });
  it("clears selections/drafts/history between sessions and ignores old responses", async () => {
    const oldProfile = deferred<{ timezone: string }>();
    mocks.profile.mockReturnValueOnce(oldProfile.promise);
    const view = render(<AppointmentsPage />);
    await selectPatient();
    mocks.state.auth.accessToken = "new-token";
    mocks.patients.mockResolvedValue([]);
    mocks.appointments.mockResolvedValue([]);
    view.rerender(<AppointmentsPage />);
    await screen.findByText("No assigned patients");
    await act(async () =>
      oldProfile.resolve({ timezone: "America/Los_Angeles" }),
    );
    expect(screen.queryByRole("form")).not.toBeInTheDocument();
    expect(screen.queryByText("Maya Patel")).not.toBeInTheDocument();
    expect(mocks.patients).toHaveBeenLastCalledWith("new-token");
  });
  it("ignores a late profile response after switching patients", async () => {
    const pending = deferred<{ timezone: string }>();
    mocks.profile
      .mockReturnValueOnce(pending.promise)
      .mockResolvedValueOnce({ timezone: "UTC" });
    render(<AppointmentsPage />);
    await selectPatient();
    await selectPatient("team2");
    await screen.findByLabelText("Option 1 (UTC)");
    await act(async () => pending.resolve({ timezone: "America/Los_Angeles" }));
    expect(
      screen.queryByLabelText("Option 1 (America/Los_Angeles)"),
    ).not.toBeInTheDocument();
  });
});
