import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useVisitsData } from "@/hooks/use-visits-data";
import type { Appointment } from "@/types";

const { fetchVisits, respondToVisit } = vi.hoisted(() => ({
  fetchVisits: vi.fn(),
  respondToVisit: vi.fn(),
}));
let token: string | null;
vi.mock("react-redux", () => ({
  useSelector: (selector: (state: unknown) => unknown) =>
    selector({ auth: { accessToken: token } }),
}));
vi.mock("@/services/appointments", async (original) => ({
  ...(await original<typeof import("@/services/appointments")>()),
  fetchVisits,
  respondToVisit,
}));
const visit: Appointment = {
  id: "synthetic-slot",
  patientId: "synthetic-patient",
  careTeamId: "synthetic-team",
  proposalGroupId: "synthetic-group",
  scheduledAt: "2099-10-01T10:00:00Z",
  durationMinutes: 30,
  appointmentType: "follow_up",
  status: "proposed",
  createdAt: "2026-09-28T00:00:00Z",
};
function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}
beforeEach(() => {
  token = "session-a";
  fetchVisits.mockReset();
  respondToVisit.mockReset();
});
afterEach(() => vi.useRealTimers());

describe("visit loading, expiry, and response recovery", () => {
  it("distinguishes a saved response from a failed follow-up refresh", async () => {
    fetchVisits
      .mockResolvedValueOnce([visit])
      .mockRejectedValueOnce(new Error("network"));
    respondToVisit.mockResolvedValue({ ...visit, status: "confirmed" });
    const { result } = renderHook(useVisitsData);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.respond(visit.id, "accept"));
    expect(result.current.visits[0].status).toBe("confirmed");
    expect(result.current.actionError).toBe("RESPONSE_SAVED_REFRESH_FAILED");
  });
  it("keeps visits visible and uses only stable codes on a conflict", async () => {
    fetchVisits.mockResolvedValue([visit]);
    respondToVisit.mockRejectedValue({
      message: "Raw English detail",
      details: { error: { code: "APPOINTMENT_CONFLICT" } },
    });
    const { result } = renderHook(useVisitsData);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.respond(visit.id, "accept"));
    expect(result.current.visits).toEqual([visit]);
    expect(result.current.actionError).toBe("APPOINTMENT_CONFLICT");
    expect(result.current.respondingId).toBeNull();
  });
  it("refreshes the persisted expired state after a late response", async () => {
    fetchVisits
      .mockResolvedValueOnce([visit])
      .mockResolvedValueOnce([{ ...visit, status: "expired" }]);
    respondToVisit.mockRejectedValue({
      details: { error: { code: "APPOINTMENT_EXPIRED" } },
    });
    const { result } = renderHook(useVisitsData);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.respond(visit.id, "accept"));
    expect(result.current.visits[0].status).toBe("expired");
    expect(result.current.actionError).toBe("APPOINTMENT_EXPIRED");
  });
  it("keeps the list and expiry notice if the follow-up read fails", async () => {
    fetchVisits
      .mockResolvedValueOnce([visit])
      .mockRejectedValueOnce(new Error("network"));
    respondToVisit.mockRejectedValue({
      details: { error: { code: "APPOINTMENT_EXPIRED" } },
    });
    const { result } = renderHook(useVisitsData);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.respond(visit.id, "accept"));
    expect(result.current.visits).toEqual([visit]);
    expect(result.current.error).toBeNull();
    expect(result.current.actionError).toBe("APPOINTMENT_EXPIRED");
  });
  it("reads authoritative sibling states after acceptance", async () => {
    const expired = {
      ...visit,
      id: "elapsed-slot",
      status: "expired" as const,
    };
    const confirmed = { ...visit, status: "confirmed" as const };
    fetchVisits
      .mockResolvedValueOnce([visit, { ...expired, status: "proposed" }])
      .mockResolvedValueOnce([confirmed, expired]);
    respondToVisit.mockResolvedValue(confirmed);
    const { result } = renderHook(useVisitsData);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => result.current.respond(visit.id, "accept"));
    expect(result.current.visits).toEqual([confirmed, expired]);
  });
  it("refreshes at the deadline and on browser focus", async () => {
    vi.useFakeTimers();
    const pending = {
      ...visit,
      proposalExpiresAt: new Date(Date.now() + 1000).toISOString(),
    };
    fetchVisits
      .mockResolvedValueOnce([pending])
      .mockResolvedValue([{ ...pending, status: "expired" }]);
    const { result } = renderHook(useVisitsData);
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current.visits[0].status).toBe("proposed");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.visits[0].status).toBe("expired");
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
    });
    expect(fetchVisits).toHaveBeenCalledTimes(3);
  });
  it("does not repeatedly retry an elapsed deadline after a failed refresh", async () => {
    vi.useFakeTimers();
    fetchVisits
      .mockResolvedValueOnce([
        {
          ...visit,
          proposalExpiresAt: new Date(Date.now() + 1000).toISOString(),
        },
      ])
      .mockRejectedValue(new Error("network"));
    const { result } = renderHook(useVisitsData);
    await act(async () => {
      await Promise.resolve();
    });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(121000);
    });
    expect(fetchVisits).toHaveBeenCalledTimes(2);
    expect(result.current.error).toBe("LOAD_FAILED");
  });
  it("clears visits between sessions and ignores an old action result", async () => {
    fetchVisits.mockResolvedValueOnce([visit]).mockResolvedValueOnce([]);
    const old = deferred<Appointment>();
    respondToVisit.mockReturnValue(old.promise);
    const { result, rerender } = renderHook(useVisitsData);
    await waitFor(() => expect(result.current.loading).toBe(false));
    let response!: Promise<void>;
    act(() => {
      response = result.current.respond(visit.id, "accept");
    });
    token = "session-b";
    rerender();
    expect(result.current.visits).toEqual([]);
    await waitFor(() => expect(result.current.loading).toBe(false));
    await act(async () => {
      old.resolve({ ...visit, status: "confirmed" });
      await response;
    });
    expect(result.current.visits).toEqual([]);
    expect(result.current.respondingId).toBeNull();
    expect(fetchVisits.mock.calls.map(([session]) => session)).toEqual([
      "session-a",
      "session-b",
    ]);
  });
  it("ignores late loads after logout and stays empty without a session", async () => {
    const old = deferred<Appointment[]>();
    fetchVisits.mockReturnValueOnce(old.promise);
    const { result, rerender } = renderHook(useVisitsData);
    token = null;
    rerender();
    await act(async () => old.resolve([visit]));
    expect(result.current.visits).toEqual([]);
    expect(result.current.loading).toBe(false);
  });
  it("prevents duplicate responses and focus reads while submitting", async () => {
    fetchVisits.mockResolvedValue([visit]);
    const pending = deferred<Appointment>();
    respondToVisit.mockReturnValue(pending.promise);
    const { result } = renderHook(useVisitsData);
    await waitFor(() => expect(result.current.loading).toBe(false));
    let response!: Promise<void>;
    act(() => {
      response = result.current.respond(visit.id, "accept");
    });
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
      await result.current.respond(visit.id, "accept");
    });
    expect(respondToVisit).toHaveBeenCalledTimes(1);
    expect(fetchVisits).toHaveBeenCalledTimes(1);
    await act(async () => {
      pending.resolve({ ...visit, status: "confirmed" });
      await response;
    });
  });
});
