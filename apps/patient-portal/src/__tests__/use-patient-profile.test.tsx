import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  usePatientProfile,
  usePatientProfileState,
} from "@/hooks/use-patient-profile";
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
let token: string | null;
vi.mock("@/services/api", () => ({ api: { get } }));
vi.mock("react-redux", () => ({
  useSelector: (selector: (state: unknown) => unknown) =>
    selector({ auth: { accessToken: token } }),
}));
const raw = {
  id: "synthetic-1",
  first_name: "Demo",
  last_name: "Patient",
  email: "demo@example.com",
  date_of_birth: "1980-01-01",
  preferred_language: "es",
  timezone: "America/Los_Angeles",
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
  get.mockReset();
});
describe("patient profile state", () => {
  it("loads and normalizes the profile while preserving the old hook interface", async () => {
    get.mockResolvedValue(raw);
    const { result } = renderHook(() => usePatientProfile());
    expect(result.current).toBeNull();
    await waitFor(() =>
      expect(result.current?.preferredLanguage).toBe("es-MX"),
    );
    expect(result.current?.timezone).toBe("America/Los_Angeles");
    expect(get).toHaveBeenCalledWith("/api/v1/patients/me", {
      token: "session-a",
    });
  });
  it("exposes failure and supports retry", async () => {
    get.mockRejectedValueOnce(new Error("failure")).mockResolvedValueOnce(raw);
    const { result } = renderHook(usePatientProfileState);
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.error).toBe(true));
    expect(result.current.loading).toBe(false);
    act(() => result.current.refresh());
    expect(result.current.loading).toBe(true);
    await waitFor(() => expect(result.current.profile?.id).toBe(raw.id));
    expect(result.current.error).toBe(false);
  });
  it("marks missing timezone separately from a saved UTC timezone", async () => {
    get
      .mockResolvedValueOnce({ ...raw, timezone: undefined })
      .mockResolvedValueOnce({ ...raw, timezone: "UTC" });
    const { result } = renderHook(usePatientProfileState);
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    expect(result.current.timezoneMissing).toBe(true);
    act(() => result.current.refresh());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.timezoneMissing).toBe(false);
  });
  it("clears settings on logout and never resurrects them when the token is reused", async () => {
    get.mockResolvedValueOnce(raw);
    const pending = deferred<typeof raw>();
    get.mockReturnValueOnce(pending.promise);
    const { result, rerender } = renderHook(usePatientProfileState);
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    token = null;
    rerender();
    expect(result.current.profile).toBeNull();
    expect(result.current.loading).toBe(false);
    token = "session-a";
    rerender();
    expect(result.current.profile).toBeNull();
    expect(result.current.loading).toBe(true);
    await act(async () => pending.resolve(raw));
    expect(result.current.profile?.id).toBe(raw.id);
  });
  it("ignores late responses from the previous session", async () => {
    const old = deferred<typeof raw>();
    const current = deferred<typeof raw>();
    get.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise);
    const { result, rerender } = renderHook(usePatientProfileState);
    token = "session-b";
    rerender();
    await act(async () => old.resolve(raw));
    expect(result.current.profile).toBeNull();
    expect(result.current.loading).toBe(true);
    await act(async () =>
      current.resolve({
        ...raw,
        id: "synthetic-2",
        preferred_language: "en-US",
      }),
    );
    expect(result.current.profile?.id).toBe("synthetic-2");
    expect(result.current.profile?.preferredLanguage).toBe("en-US");
  });
});
