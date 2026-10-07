import { describe, expect, it } from "vitest";
import { applyAppointmentResponse } from "@/services/appointments";
import { AppointmentStatus, type Appointment } from "@/types";
const chosen: Appointment = {
  id: "a",
  proposalGroupId: "group-1",
  patientId: "synthetic-patient",
  careTeamId: "synthetic-team",
  scheduledAt: "2026-10-01T17:00:00Z",
  durationMinutes: 30,
  appointmentType: "follow_up",
  status: AppointmentStatus.PROPOSED,
  createdAt: "2026-09-26T00:00:00Z",
};
const visits = [
  chosen,
  { ...chosen, id: "b" },
  { ...chosen, id: "c", proposalGroupId: "group-2" },
  { ...chosen, id: "legacy", proposalGroupId: undefined },
];
describe("atomic offer response mapping", () => {
  it("confirms one slot and withdraws siblings without changing unrelated appointments", () => {
    const result = applyAppointmentResponse(
      visits,
      { ...chosen, status: AppointmentStatus.CONFIRMED },
      "accept",
    );
    expect(result.map((row) => row.status)).toEqual([
      "confirmed",
      "withdrawn",
      "proposed",
      "proposed",
    ]);
    expect(result[2]).toBe(visits[2]);
    expect(result[3]).toBe(visits[3]);
    expect(visits[1].status).toBe("proposed");
  });
  it.each(["decline", "request_alternative"] as const)(
    "updates the whole offer for %s",
    (action) => {
      const status =
        action === "decline"
          ? AppointmentStatus.DECLINED
          : AppointmentStatus.ALTERNATIVE_REQUESTED;
      const result = applyAppointmentResponse(
        visits,
        { ...chosen, status, patientNote: "Afternoons" },
        action,
      );
      expect(
        result.slice(0, 2).map((row) => [row.status, row.patientNote]),
      ).toEqual([
        [status, "Afternoons"],
        [status, "Afternoons"],
      ]);
      expect(result[2]).toBe(visits[2]);
    },
  );
  it("cancellation changes only the booked visit", () => {
    const result = applyAppointmentResponse(
      visits,
      { ...chosen, status: AppointmentStatus.CANCELLED },
      "cancel",
    );
    expect(result[1]).toBe(visits[1]);
  });
  it("a legacy response never changes grouped appointments", () => {
    const result = applyAppointmentResponse(
      visits,
      { ...visits[3], status: AppointmentStatus.CONFIRMED },
      "accept",
    );
    expect(result[0]).toBe(visits[0]);
    expect(result[1]).toBe(visits[1]);
  });
});
