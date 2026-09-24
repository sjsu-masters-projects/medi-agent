import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/services/api", () => ({
  api: { get: vi.fn(), post: vi.fn() },
}));

import { api } from "@/services/api";
import { fetchVisits, respondToVisit } from "@/services/appointments";

const apiRecord = {
  id: "a1",
  patient_id: "p1",
  care_team_id: "c1",
  clinician_name: "Elena Park",
  scheduled_at: "2026-05-08T17:00:00Z",
  duration_minutes: 30,
  appointment_type: "follow_up",
  location: "Telehealth",
  reason: "Check",
  notes: null,
  status: "proposed",
  source_document_id: null,
  created_at: "2026-05-07T10:00:00Z",
};

describe("appointments service", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("maps snake_case API records to camelCase appointments", async () => {
    vi.mocked(api.get).mockResolvedValue([apiRecord]);

    const visits = await fetchVisits("token");

    expect(api.get).toHaveBeenCalledWith("/api/v1/appointments/", {
      token: "token",
    });
    expect(visits[0]).toMatchObject({
      id: "a1",
      patientId: "p1",
      careTeamId: "c1",
      clinicianName: "Elena Park",
      scheduledAt: "2026-05-08T17:00:00Z",
      durationMinutes: 30,
      status: "proposed",
    });
  });

  it("posts the chosen action to the respond endpoint", async () => {
    vi.mocked(api.post).mockResolvedValue({
      ...apiRecord,
      status: "confirmed",
    });

    const updated = await respondToVisit("a1", "accept", "token");

    expect(api.post).toHaveBeenCalledWith(
      "/api/v1/appointments/a1/respond",
      { action: "accept" },
      { token: "token" },
    );
    expect(updated.status).toBe("confirmed");
  });
});
