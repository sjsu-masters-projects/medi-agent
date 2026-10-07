import { beforeEach, describe, expect, it, vi } from "vitest";
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { get, post } }));
import {
  fetchSchedulingAppointments,
  fetchSchedulingPatients,
  fetchSchedulingProfile,
  proposeAppointmentOffer,
} from "@/services/appointments";

const record = {
  id: "a",
  patient_id: "p",
  care_team_id: "team",
  scheduled_at: "2027-01-05T17:00:00Z",
  duration_minutes: 30,
  appointment_type: "follow_up",
  status: "proposed",
  created_at: "2026-09-28T00:00Z",
  proposal_group_id: "group",
  proposal_expires_at: "2026-10-05T00:00:00Z",
  patient_note: "As written",
  reason: "Follow-up",
};
describe("clinician appointment service", () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
  });
  it("uses authenticated roster/profile endpoints", async () => {
    get.mockResolvedValue([]);
    await fetchSchedulingPatients("token");
    await fetchSchedulingProfile("token", "patient");
    expect(get).toHaveBeenCalledWith("/api/v1/clinicians/me/patients", {
      token: "token",
    });
    expect(get).toHaveBeenCalledWith("/api/v1/clinicians/me/patients/patient", {
      token: "token",
    });
  });
  it("maps grouped appointments and preserves notes/statuses", async () => {
    get.mockResolvedValue([{ ...record, status: "withdrawn" }]);
    expect(await fetchSchedulingAppointments("token")).toEqual([
      expect.objectContaining({
        careTeamId: "team",
        patientId: "p",
        proposalGroupId: "group",
        proposalExpiresAt: "2026-10-05T00:00:00Z",
        patientNote: "As written",
        status: "withdrawn",
      }),
    ]);
  });
  it("passes only the selected care team and offer draft, with the login token", async () => {
    post.mockResolvedValue([record]);
    const draft = {
      care_team_id: "team",
      slots: ["2027-01-05T17:00Z", "2027-01-06T17:00Z"],
      duration_minutes: 30,
      appointment_type: "follow_up" as const,
    };
    const result = await proposeAppointmentOffer("token", draft);
    expect(post).toHaveBeenCalledWith("/api/v1/appointments/propose", draft, {
      token: "token",
    });
    expect(result[0]?.proposalGroupId).toBe("group");
    expect(draft).not.toHaveProperty("patient_id");
    expect(draft).not.toHaveProperty("clinician_id");
  });
});
