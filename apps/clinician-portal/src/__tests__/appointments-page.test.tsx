import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Appointment } from "@/types";
import type { MySchedule, ScheduleVisit } from "@/services/appointments";
import { clinicFilterState, resetClinicFilter } from "@/test/clinic-filter-mock";

const mocks = vi.hoisted(() => ({
  schedule: vi.fn(),
  patients: vi.fn(),
  profile: vi.fn(),
  busy: vi.fn(),
  propose: vi.fn(),
  patientRows: vi.fn(),
  allRows: vi.fn(),
  update: vi.fn(),
  cancel: vi.fn(),
  complete: vi.fn(),
  noShow: vi.fn(),
  replace: vi.fn(),
  state: { auth: { accessToken: "clinician-token" as string | null } },
  query: "",
}));
vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(mocks.query),
  usePathname: () => "/appointments",
  useRouter: () => ({ replace: mocks.replace, push: mocks.replace }),
}));
vi.mock("react-redux", () => ({
  useSelector: (selector: (state: typeof mocks.state) => unknown) => selector(mocks.state),
}));
vi.mock("@/services/appointments", () => ({
  fetchMySchedule: mocks.schedule,
  fetchSchedulingPatients: mocks.patients,
  fetchSchedulingProfile: mocks.profile,
  fetchBusyTimes: mocks.busy,
  proposeAppointmentOffer: mocks.propose,
  fetchPatientAppointments: mocks.patientRows,
  fetchSchedulingAppointments: mocks.allRows,
  updateVisitDetails: mocks.update,
  cancelVisit: mocks.cancel,
  completeVisit: mocks.complete,
  markVisitNoShow: mocks.noShow,
}));
import AppointmentsPage from "@/app/(dashboard)/appointments/page";

const roster = [
  { id: "p1", care_team_id: "team1", first_name: "Maya", last_name: "Patel", clinic_name: "Cedar Grove Community Health" },
  { id: "p2", care_team_id: "team2", first_name: "Hannah", last_name: "Brooks", clinic_name: "Willow Terrace" },
];
const TWO = [
  { clinic_id: "c1", clinic_code: "A", clinic_name: "Cedar Grove Community Health", role: "provider", status: "active" },
  { clinic_id: "c2", clinic_code: "B", clinic_name: "Willow Terrace", role: "provider", status: "active" },
] as never;

function visit(overrides: Partial<ScheduleVisit> = {}): ScheduleVisit {
  return {
    id: "v1",
    patientId: "p1",
    careTeamId: "team1",
    patientName: "Maya Patel",
    patientTimezone: "America/Los_Angeles",
    clinicName: "Cedar Grove Community Health",
    scheduledAt: "2026-10-17T16:30:00Z",
    durationMinutes: 30,
    appointmentType: "follow_up",
    status: "confirmed",
    createdAt: "2026-10-10T00:00:00Z",
    ...overrides,
  };
}
function schedule(overrides: Partial<MySchedule> = {}): MySchedule {
  return { visits: [], needsAction: [], nextVisit: null, ...overrides };
}
function offer(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: "o1",
    patientId: "p1",
    careTeamId: "team1",
    scheduledAt: "2026-10-20T16:00:00Z",
    durationMinutes: 30,
    appointmentType: "follow_up",
    status: "proposed",
    proposalGroupId: "g1",
    createdAt: "2026-10-15T00:00:00Z",
    ...overrides,
  };
}

describe("My schedule", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetClinicFilter();
    vi.spyOn(Date, "now").mockReturnValue(Date.parse("2026-10-17T15:00:00Z"));
    mocks.state.auth.accessToken = "clinician-token";
    mocks.query = "";
    mocks.schedule.mockResolvedValue(schedule());
    mocks.patients.mockResolvedValue(roster);
    mocks.profile.mockResolvedValue({ timezone: "America/Los_Angeles" });
    mocks.busy.mockResolvedValue([]);
    mocks.patientRows.mockResolvedValue([offer()]);
    mocks.allRows.mockResolvedValue([]);
    mocks.propose.mockResolvedValue([offer()]);
  });
  afterEach(() => vi.restoreAllMocks());

  it("does not load anything without a clinician session", () => {
    mocks.state.auth.accessToken = null;
    render(<AppointmentsPage />);
    expect(screen.getByRole("status")).toHaveTextContent("Sign in as a clinician");
    expect(mocks.schedule).not.toHaveBeenCalled();
  });

  it("shows both clinics' visits on one agenda, grouped by day, with clinic chips", async () => {
    clinicFilterState.clinics = TWO;
    mocks.schedule.mockResolvedValue(
      schedule({
        visits: [
          visit(),
          visit({ id: "v2", patientName: "Hannah Brooks", clinicName: "Willow Terrace", scheduledAt: "2026-10-17T20:00:00Z", status: "scheduled" }),
          visit({ id: "v3", patientName: "Maya Patel", scheduledAt: "2026-10-19T17:00:00Z" }),
        ],
      }),
    );
    render(<AppointmentsPage />);
    expect(await screen.findByRole("heading", { name: "Today · Sat Oct 17" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Mon Oct 19" })).toBeInTheDocument();
    expect(screen.getByText("9:30 AM")).toBeInTheDocument(); // the visit's own timezone
    const agenda = screen.getByLabelText("Agenda");
    expect(within(agenda).getAllByText("Cedar Grove Community Health")).toHaveLength(2);
    expect(within(agenda).getByText("Willow Terrace")).toBeInTheDocument();
    expect(within(agenda).getAllByText("Confirmed")).toHaveLength(2);
    expect(screen.getByText("Your visits and appointment offers · All clinics")).toBeInTheDocument();
    expect(screen.getByLabelText("Clinic")).toBeInTheDocument();
    const [from, to] = mocks.schedule.mock.calls[0]!.slice(1, 3) as string[];
    expect(Date.parse(to!) - Date.parse(from!)).toBeLessThanOrEqual(25 * 3_600_000); // Today
  });

  it("shows a week on request and passes the clinic filter to the server", async () => {
    clinicFilterState.clinics = TWO;
    clinicFilterState.clinicId = "c2";
    render(<AppointmentsPage />);
    await screen.findByText("Your visits and appointment offers · Willow Terrace");
    fireEvent.click(screen.getByRole("radio", { name: "This week" }));
    await waitFor(() => expect(mocks.schedule).toHaveBeenCalledTimes(2));
    const call = mocks.schedule.mock.calls[1]!;
    expect(call[3]).toBe("c2");
    expect(Date.parse(call[2] as string) - Date.parse(call[1] as string)).toBeGreaterThan(6 * 86_400_000);
  });

  it("shows no clinic chrome to a single-clinic clinician", async () => {
    mocks.schedule.mockResolvedValue(schedule({ visits: [visit()] }));
    render(<AppointmentsPage />);
    await screen.findByText("Maya Patel");
    expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
    expect(screen.queryByText("Cedar Grove Community Health")).not.toBeInTheDocument();
    expect(screen.getByText("Your visits and appointment offers")).toBeInTheDocument();
  });

  it("does not describe the previous day result as an empty week while loading", async () => {
    let finish!: (value: MySchedule) => void;
    mocks.schedule.mockResolvedValueOnce(schedule()).mockImplementationOnce(
      () => new Promise<MySchedule>((resolve) => { finish = resolve; }),
    );
    render(<AppointmentsPage />);
    await screen.findByText("No visits today");
    fireEvent.click(screen.getByRole("radio", { name: "This week" }));
    expect(screen.getByText("Loading your schedule…")).toBeInTheDocument();
    expect(screen.queryByText("No visits this week")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh schedule" })).toBeDisabled();
    finish(schedule({ visits: [visit()] }));
    expect(await screen.findByText("Maya Patel")).toBeInTheDocument();
  });

  it("does not reuse old-range visits on failure, but preserves a same-range refresh", async () => {
    mocks.schedule.mockResolvedValueOnce(schedule({ visits: [visit()] }));
    render(<AppointmentsPage />);
    await screen.findByText("Maya Patel");
    mocks.schedule.mockRejectedValueOnce(new Error("Unavailable"));
    fireEvent.click(screen.getByRole("button", { name: "Refresh schedule" }));
    await screen.findByText(/Showing what was loaded before/);
    expect(screen.getByText("Maya Patel")).toBeInTheDocument();
    mocks.schedule.mockRejectedValueOnce(new Error("Unavailable"));
    fireEvent.click(screen.getByRole("radio", { name: "This week" }));
    expect(screen.queryByText(/Showing what was loaded before/)).not.toBeInTheDocument();
    await screen.findByText("Your schedule is unavailable");
    expect(screen.queryByText("Maya Patel")).not.toBeInTheDocument();
    expect(screen.queryByText("No visits this week")).not.toBeInTheDocument();
  });

  it("opens a visit from its row", async () => {
    mocks.schedule.mockResolvedValue(schedule({ visits: [visit()] }));
    render(<AppointmentsPage />);
    fireEvent.click(await screen.findByRole("button", { name: /Maya Patel/ }));
    expect(mocks.replace).toHaveBeenCalledWith("/appointments?appointmentId=v1", { scroll: false });
  });

  it("summarises what needs action and opens the item", async () => {
    mocks.schedule.mockResolvedValue(
      schedule({
        needsAction: [
          { kind: "awaiting_reply", appointmentId: "o1", patientId: "p1", patientName: "Maya Patel", slotCount: 2, firstSlotAt: "2026-10-20T16:00:00Z", expiresAt: "2026-10-18T15:00:00Z", expiringSoon: true },
          { kind: "awaiting_reply", appointmentId: "o2", patientId: "p2", patientName: "Hannah Brooks", slotCount: 3, firstSlotAt: "2026-10-22T16:00:00Z", expiresAt: "2026-10-24T15:00:00Z", expiringSoon: false },
          { kind: "change_request", appointmentId: "o3", patientId: "p2", patientName: "Hannah Brooks", slotCount: 2, firstSlotAt: "2026-10-23T16:00:00Z", expiringSoon: false },
        ],
      }),
    );
    render(<AppointmentsPage />);
    const strip = await screen.findByRole("region", { name: "Needs action" });
    expect(within(strip).getByText("expiring soon")).toBeInTheDocument();
    expect(within(strip).getByText("change request")).toBeInTheDocument();
    fireEvent.click(within(strip).getByRole("button", { name: "2 awaiting reply" }));
    const list = within(strip).getByRole("list", { name: "Items that need action" });
    expect(within(list).getAllByRole("button")).toHaveLength(2);
    expect(list).toHaveTextContent("Expiring soon");
    fireEvent.click(within(list).getAllByRole("button")[0]!);
    expect(mocks.replace).toHaveBeenCalledWith("/appointments?appointmentId=o1", { scroll: false });
  });

  it("explains an empty day, names the next visit and offers a new offer", async () => {
    mocks.schedule.mockResolvedValue(schedule({ nextVisit: visit({ id: "v9", scheduledAt: "2026-10-19T17:00:00Z" }) }));
    render(<AppointmentsPage />);
    expect(await screen.findByText("No visits today")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Next visit: Mon Oct 19, 10:00 AM · Maya Patel/ })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "New offer" }).length).toBeGreaterThan(0);
  });

  it("reports a load failure with a retry and no raw server text", async () => {
    mocks.schedule.mockRejectedValueOnce(new Error("Raw authorization detail"));
    render(<AppointmentsPage />);
    await screen.findByText("Your schedule is unavailable");
    expect(screen.queryByText("Raw authorization detail")).not.toBeInTheDocument();
    fireEvent.click(screen.getAllByRole("button", { name: "Retry" })[0]!);
    expect(await screen.findByText("No visits today")).toBeInTheDocument();
  });

  describe("New offer panel", () => {
    async function openPanel() {
      render(<AppointmentsPage />);
      const button = await screen.findByRole("button", { name: "New offer" });
      await waitFor(() => expect(button).toBeEnabled());
      fireEvent.click(button);
      return screen.findByRole("dialog", { name: "New offer" });
    }
    async function choosePatient(panel: HTMLElement, value = "team1") {
      fireEvent.change(within(panel).getByRole("combobox", { name: "Patient" }), { target: { value } });
      await within(panel).findByLabelText("Option 1 (America/Los_Angeles)");
    }

    it("derives the clinic from the link, read-only and once", async () => {
      clinicFilterState.clinics = TWO;
      const panel = await openPanel();
      await choosePatient(panel);
      expect(within(panel).getByText("Clinic:", { exact: false })).toHaveTextContent("Clinic: Cedar Grove Community Health");
      expect(within(panel).getAllByText("Cedar Grove Community Health")).toHaveLength(1);
      expect(within(panel).queryByLabelText("Clinic")).not.toBeInTheDocument();
    });

    it("lists the clinician's busy times for the chosen date, with clinics and no patients", async () => {
      clinicFilterState.clinics = TWO;
      mocks.busy.mockResolvedValue([
        { startsAt: "2026-10-20T16:00:00Z", endsAt: "2026-10-20T16:30:00Z", clinicId: "c1", clinicName: "Cedar Grove Community Health" },
      ]);
      const panel = await openPanel();
      await choosePatient(panel);
      fireEvent.change(within(panel).getByLabelText("Option 1 (America/Los_Angeles)"), { target: { value: "2026-10-20T09:00" } });
      const busy = await within(panel).findByLabelText("Your booked times on 2026-10-20");
      expect(busy).toHaveTextContent("9:00–9:30 AM · Cedar Grove Community Health");
      expect(busy).not.toHaveTextContent("Maya");
      expect(mocks.busy).toHaveBeenCalledTimes(1);
    });

    it("names no clinic beside busy times for a single-clinic clinician", async () => {
      mocks.busy.mockResolvedValue([{ startsAt: "2026-10-20T16:00:00Z", endsAt: "2026-10-20T16:30:00Z", clinicName: "Only Clinic" }]);
      const panel = await openPanel();
      await choosePatient(panel);
      fireEvent.change(within(panel).getByLabelText("Option 1 (America/Los_Angeles)"), { target: { value: "2026-10-20T09:00" } });
      const busy = await within(panel).findByLabelText("Your booked times on 2026-10-20");
      expect(busy).toHaveTextContent("9:00–9:30 AM");
      expect(busy).not.toHaveTextContent("Only Clinic");
    });

    it("sends the offer from the sticky footer and refreshes the schedule", async () => {
      const panel = await openPanel();
      await choosePatient(panel);
      fireEvent.change(within(panel).getByLabelText("Option 1 (America/Los_Angeles)"), { target: { value: "2026-10-20T09:00" } });
      fireEvent.change(within(panel).getByLabelText("Option 2 (America/Los_Angeles)"), { target: { value: "2026-10-21T14:00" } });
      fireEvent.submit(within(panel).getByRole("form", { name: "Appointment offer" }));
      await screen.findByText(/Appointment offer sent/);
      expect(mocks.propose).toHaveBeenCalledWith(
        "clinician-token",
        expect.objectContaining({ care_team_id: "team1", slots: ["2026-10-20T16:00:00.000Z", "2026-10-21T21:00:00.000Z"] }),
      );
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
      expect(mocks.schedule).toHaveBeenCalledTimes(2);
    });

    it("keeps the server conflict callout and blocks sending until the time changes", async () => {
      mocks.propose.mockRejectedValue(
        Object.assign(new Error("conflict"), {
          details: { error: { code: "CLINICIAN_SCHEDULE_CONFLICT", details: { conflicts: [{ slot: "2026-10-20T16:00:00.000Z", clinic_name: "Willow Terrace", starts_at: "2026-10-20T15:45:00Z", ends_at: "2026-10-20T16:15:00Z" }] } } },
        }),
      );
      const panel = await openPanel();
      await choosePatient(panel);
      fireEvent.change(within(panel).getByLabelText("Option 1 (America/Los_Angeles)"), { target: { value: "2026-10-20T09:00" } });
      fireEvent.change(within(panel).getByLabelText("Option 2 (America/Los_Angeles)"), { target: { value: "2026-10-21T14:00" } });
      fireEvent.submit(within(panel).getByRole("form", { name: "Appointment offer" }));
      expect(await within(panel).findByRole("alert")).toHaveTextContent("You already have an appointment at Willow Terrace");
      expect(within(panel).getByText("Change the conflicting time to send.")).toBeInTheDocument();
      expect(within(panel).getByRole("button", { name: "Send offer" })).toBeDisabled();
    });

    it("disables the picker and refuses a second submit while sending", async () => {
      let resolve!: (rows: Appointment[]) => void;
      mocks.propose.mockReturnValue(new Promise<Appointment[]>((done) => { resolve = done; }));
      const panel = await openPanel();
      await choosePatient(panel);
      fireEvent.change(within(panel).getByLabelText("Option 1 (America/Los_Angeles)"), { target: { value: "2026-10-20T09:00" } });
      fireEvent.change(within(panel).getByLabelText("Option 2 (America/Los_Angeles)"), { target: { value: "2026-10-21T14:00" } });
      const form = within(panel).getByRole("form", { name: "Appointment offer" });
      fireEvent.submit(form);
      fireEvent.submit(form);
      expect(mocks.propose).toHaveBeenCalledTimes(1);
      expect(within(panel).getByRole("combobox", { name: "Patient" })).toBeDisabled();
      resolve([offer()]);
      await screen.findByText(/Appointment offer sent/);
    });

    it("retries a timezone failure without exposing server text", async () => {
      mocks.profile.mockRejectedValueOnce(new Error("private server detail"));
      const panel = await openPanel();
      fireEvent.change(within(panel).getByRole("combobox", { name: "Patient" }), { target: { value: "team1" } });
      await within(panel).findByText("Could not load the patient's timezone");
      expect(screen.queryByText("private server detail")).not.toBeInTheDocument();
      fireEvent.click(within(panel).getByRole("button", { name: "Try again" }));
      await within(panel).findByLabelText("Option 1 (America/Los_Angeles)");
    });
  });

  describe("visit detail", () => {
    it("opens the visit from the link with the patient, clinic, status and history", async () => {
      clinicFilterState.clinics = TWO;
      mocks.query = "appointmentId=v1";
      mocks.schedule.mockResolvedValue(schedule({ visits: [visit()] }));
      mocks.patientRows.mockResolvedValue([
        { ...offer({ id: "v1", status: "confirmed", clinicName: "Cedar Grove Community Health", patientNote: "Works for me" }) },
      ]);
      render(<AppointmentsPage />);
      const panel = await screen.findByRole("dialog", { name: "Visit" });
      expect(await within(panel).findByText(/Works for me/)).toBeInTheDocument();
      expect(within(panel).getByRole("link", { name: "Maya Patel" })).toHaveAttribute("href", "/patients/p1");
      expect(within(panel).getAllByText("Confirmed").length).toBeGreaterThan(0);
      expect(mocks.patientRows).toHaveBeenCalledWith("clinician-token", "p1");
    });

    it("looks up a linked appointment outside the loaded range, or says it is unavailable", async () => {
      mocks.query = "appointmentId=far";
      mocks.allRows.mockResolvedValue([offer({ id: "far" })]);
      mocks.patientRows.mockResolvedValue([offer({ id: "far" })]);
      const first = render(<AppointmentsPage />);
      await screen.findByRole("dialog", { name: "Visit" });
      first.unmount();
      mocks.query = "appointmentId=missing";
      render(<AppointmentsPage />);
      await screen.findByText("The linked appointment is unavailable.");
    });
  });

  describe("visit management", () => {
    async function openVisit(row: Partial<Appointment>) {
      mocks.query = "appointmentId=v1";
      mocks.schedule.mockResolvedValue(schedule({ visits: [visit()] }));
      mocks.patientRows.mockResolvedValue([offer({ id: "v1", status: "confirmed", scheduledAt: "2026-10-20T16:00:00Z", ...row })]);
      render(<AppointmentsPage />);
      const panel = await screen.findByRole("dialog", { name: "Visit" });
      await within(panel).findByRole("button", { name: "More actions" });
      return panel;
    }
    const openMenu = (panel: HTMLElement) => fireEvent.click(within(panel).getByRole("button", { name: "More actions" }));

    it("offers 'Offer new times' first for an upcoming visit and keeps the rest in the menu", async () => {
      const panel = await openVisit({});
      expect(within(panel).getByRole("button", { name: "Offer new times" })).toBeInTheDocument();
      expect(within(panel).queryByRole("button", { name: "Mark completed" })).not.toBeInTheDocument();
      openMenu(panel);
      const items = within(panel).getAllByRole("menuitem").map((item) => item.textContent);
      expect(items).toEqual(["Edit details", "Cancel visit"]); // no no-show before the visit ends
    });

    it("offers 'Mark completed' first once the visit has ended, and no-show in the menu", async () => {
      mocks.complete.mockResolvedValue(offer({ id: "v1", status: "completed", scheduledAt: "2026-10-16T16:00:00Z" }));
      const panel = await openVisit({ scheduledAt: "2026-10-16T16:00:00Z" });
      expect(within(panel).queryByRole("button", { name: "Offer new times" })).not.toBeInTheDocument();
      openMenu(panel);
      expect(within(panel).getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Edit details", "Mark no-show", "Cancel visit"]);
      fireEvent.click(within(panel).getByRole("button", { name: "Mark completed" }));
      await waitFor(() => expect(mocks.complete).toHaveBeenCalledWith("clinician-token", "v1"));
      await waitFor(() => expect(within(panel).queryByRole("button", { name: "More actions" })).not.toBeInTheDocument());
    });

    it("confirms a no-show before recording it", async () => {
      mocks.noShow.mockResolvedValue(offer({ id: "v1", status: "no_show", scheduledAt: "2026-10-16T16:00:00Z" }));
      const panel = await openVisit({ scheduledAt: "2026-10-16T16:00:00Z" });
      openMenu(panel);
      fireEvent.click(within(panel).getByRole("menuitem", { name: "Mark no-show" }));
      const dialog = await screen.findByRole("dialog", { name: "Mark as no-show?" });
      expect(mocks.noShow).not.toHaveBeenCalled();
      fireEvent.click(within(dialog).getByRole("button", { name: "Mark no-show" }));
      await waitFor(() => expect(mocks.noShow).toHaveBeenCalledWith("clinician-token", "v1"));
    });

    it("needs a reason before cancelling, then cancels and shows it", async () => {
      mocks.cancel.mockResolvedValue(offer({ id: "v1", status: "cancelled", cancelledBy: "clinician", cancelReasonCode: "other", cancelReason: "Water leak" }));
      const panel = await openVisit({});
      openMenu(panel);
      fireEvent.click(within(panel).getByRole("menuitem", { name: "Cancel visit" }));
      const dialog = await screen.findByRole("dialog", { name: "Cancel this visit?" });
      const confirm = within(dialog).getByRole("button", { name: "Cancel visit" });
      expect(confirm).toBeDisabled();
      fireEvent.change(within(dialog).getByRole("combobox"), { target: { value: "other" } });
      expect(confirm).toBeDisabled(); // "Other" needs text
      fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "Water leak" } });
      expect(confirm).toBeEnabled();
      fireEvent.click(confirm);
      await waitFor(() => expect(mocks.cancel).toHaveBeenCalledWith("clinician-token", "v1", { reason_code: "other", reason: "Water leak" }));
      expect(await within(panel).findByRole("note")).toHaveTextContent("Cancelled by your team. Other — Water leak");
      // The agenda reload runs after the cancel resolves; wait for it instead of racing it.
      await waitFor(() => expect(mocks.schedule.mock.calls.length).toBeGreaterThan(1));
    });

    it("keeps the dialog and says so when the cancel fails or the visit changed", async () => {
      mocks.cancel.mockRejectedValue(Object.assign(new Error("x"), { details: { error: { code: "APPOINTMENT_UNAVAILABLE" } } }));
      const panel = await openVisit({});
      openMenu(panel);
      fireEvent.click(within(panel).getByRole("menuitem", { name: "Cancel visit" }));
      const dialog = await screen.findByRole("dialog", { name: "Cancel this visit?" });
      fireEvent.change(within(dialog).getByRole("combobox"), { target: { value: "clinic_closed" } });
      fireEvent.click(within(dialog).getByRole("button", { name: "Cancel visit" }));
      expect(await within(dialog).findByRole("alert")).toHaveTextContent("This visit changed in the meantime");
    });

    it("closes only the dialog on Escape, not the panel behind it", async () => {
      const panel = await openVisit({});
      openMenu(panel);
      fireEvent.click(within(panel).getByRole("menuitem", { name: "Cancel visit" }));
      await screen.findByRole("dialog", { name: "Cancel this visit?" });
      fireEvent.keyDown(document, { key: "Escape" });
      await waitFor(() => expect(screen.queryByRole("dialog", { name: "Cancel this visit?" })).not.toBeInTheDocument());
      expect(screen.getByRole("dialog", { name: "Visit" })).toBeInTheDocument();
    });

    it("edits details without a time field and refreshes the schedule", async () => {
      mocks.update.mockResolvedValue(offer({ id: "v1", status: "confirmed", location: "Suite 3", appointmentType: "routine" }));
      const panel = await openVisit({});
      openMenu(panel);
      fireEvent.click(within(panel).getByRole("menuitem", { name: "Edit details" }));
      const dialog = await screen.findByRole("dialog", { name: "Edit details" });
      expect(within(dialog).getByText(/offer new times so the patient can agree/)).toBeInTheDocument();
      expect(within(dialog).queryByLabelText(/time|date/i)).not.toBeInTheDocument();
      fireEvent.change(within(dialog).getByLabelText("Location"), { target: { value: "Suite 3" } });
      fireEvent.change(within(dialog).getByLabelText("Appointment type"), { target: { value: "routine" } });
      fireEvent.submit(within(dialog).getByRole("form", { name: "Edit visit details" }));
      await waitFor(() => expect(mocks.update).toHaveBeenCalledWith("clinician-token", "v1", expect.objectContaining({ location: "Suite 3", appointment_type: "routine" })));
      await waitFor(() => expect(screen.queryByRole("dialog", { name: "Edit details" })).not.toBeInTheDocument());
    });

    it("lets an open offer be edited but not cancelled or completed", async () => {
      const panel = await openVisit({ status: "proposed" });
      expect(within(panel).queryByRole("button", { name: /Offer new times|Mark completed/ })).not.toBeInTheDocument();
      openMenu(panel);
      expect(within(panel).getAllByRole("menuitem").map((item) => item.textContent)).toEqual(["Edit details"]);
    });
  });

  describe("cancelled visits on the agenda", () => {
    it("hides them until asked, then shows them muted with a Cancelled chip", async () => {
      mocks.schedule.mockImplementation(async (_t, _f, _to, _c, includeCancelled) =>
        schedule({ visits: [visit(), ...(includeCancelled ? [visit({ id: "v2", patientName: "Hannah Brooks", status: "cancelled", scheduledAt: "2026-10-17T20:00:00Z" })] : [])] }),
      );
      render(<AppointmentsPage />);
      await screen.findByText("Maya Patel");
      expect(screen.queryByText("Hannah Brooks")).not.toBeInTheDocument();
      expect(mocks.schedule.mock.calls[0]![4]).toBe(false);
      fireEvent.click(screen.getByRole("checkbox", { name: "Show cancelled" }));
      const row = (await screen.findByText("Hannah Brooks")).closest("button")!;
      expect(row).toHaveClass("opacity-60");
      expect(within(row).getByText("Cancelled")).toBeInTheDocument();
      expect(mocks.schedule.mock.calls.at(-1)![4]).toBe(true);
    });
  });
});
