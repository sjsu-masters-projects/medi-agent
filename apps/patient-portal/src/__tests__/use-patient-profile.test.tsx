import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  usePatientProfile,
  usePatientProfileState,
} from "@/hooks/use-patient-profile";
const { get } = vi.hoisted(() => ({ get: vi.fn() }));
let token: string | null;
let userId: string | undefined;
vi.mock("@/services/api", () => ({ api: { get } }));
vi.mock("react-redux", () => ({
  useSelector: (selector: (state: unknown) => unknown) =>
    selector({ auth: { accessToken: token, user: userId ? { id: userId } : null } }),
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
  userId = undefined;
  get.mockReset();
});
describe("patient profile state", () => {
  it("seeds the locale cookie from the saved profile preference", async () => {
    document.cookie = "patient-portal.locale=; Path=/; Max-Age=0";
    get.mockResolvedValueOnce(raw);
    const { result } = renderHook(usePatientProfileState);
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    expect(document.cookie).toContain("patient-portal.locale=es-MX");
    expect(document.documentElement.lang).toBe("es-MX");
  });

  it("keeps a saved preference when the refreshed GET arrives after the save", async () => {
    get.mockResolvedValueOnce(raw);
    const refresh = deferred<typeof raw>();
    get.mockReturnValueOnce(refresh.promise);
    const { result } = renderHook(usePatientProfileState);
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    const saveBeforeRefresh = result.current.updateProfile;
    act(() => result.current.refresh());
    act(() => saveBeforeRefresh((current) => ({ ...current, preferredLanguage: "en-US" })));
    expect(result.current.loading).toBe(false);
    await act(async () => refresh.resolve(raw));
    expect(result.current.profile?.preferredLanguage).toBe("en-US");
    expect(result.current.loading).toBe(false);
  });
  it("binds a retained save callback to the current retry and preserves newer profile fields", async () => {
    get.mockResolvedValueOnce(raw);
    const refresh = deferred<typeof raw>();
    get.mockReturnValueOnce(refresh.promise);
    const { result } = renderHook(usePatientProfileState);
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    const saveBeforeRefresh = result.current.updateProfile;
    act(() => result.current.refresh());
    await act(async () => refresh.resolve({ ...raw, first_name: "Updated" }));
    act(() => saveBeforeRefresh((current) => ({ ...current, preferredLanguage: "en-US" })));
    expect(result.current.loading).toBe(false);
    expect(result.current.profile?.firstName).toBe("Updated");
    expect(result.current.profile?.preferredLanguage).toBe("en-US");
  });
  it("ignores a retained profile save callback after the session changes", async () => {
    get.mockResolvedValue(raw);
    const { result, rerender } = renderHook(usePatientProfileState);
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    const oldSave = result.current.updateProfile;
    token = "session-b";
    get.mockResolvedValue({ ...raw, id: "other" });
    rerender();
    await waitFor(() => expect(result.current.profile?.id).toBe("other"));
    act(() => oldSave((current) => ({ ...current, preferredLanguage: "en-US" })));
    expect(result.current.profile?.preferredLanguage).toBe("es-MX");
  });
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

  it("keeps the profile on screen across a silent token refresh for the same patient", async () => {
    userId = "synthetic-1";
    get.mockResolvedValue(raw);
    const { result, rerender } = renderHook(usePatientProfileState);
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    token = "session-b";
    rerender();
    expect(result.current.loading).toBe(false);
    expect(result.current.profile?.id).toBe("synthetic-1");
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });

  it("clears the profile when a different patient signs in", async () => {
    userId = "synthetic-1";
    get.mockResolvedValue(raw);
    const { result, rerender } = renderHook(usePatientProfileState);
    await waitFor(() => expect(result.current.profile).not.toBeNull());
    token = "session-c";
    userId = "synthetic-2";
    get.mockReturnValue(new Promise(() => {}));
    rerender();
    expect(result.current.profile).toBeNull();
    expect(result.current.loading).toBe(true);
  });
});
