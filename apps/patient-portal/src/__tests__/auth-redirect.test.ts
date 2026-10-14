import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { redirectToLogin } from "@/services/auth-redirect";
const requestId = "123e4567-e89b-42d3-a456-426614174000";
const followUpPath = `/chat?view=follow-up&request=${requestId}`;
const assign = vi.fn();
// jsdom's location.assign cannot be spied on, so stand in for it while keeping the URL parts.
function openAt(path: string) {
  const url = new URL(path, "https://patient.test");
  vi.stubGlobal("location", { pathname: url.pathname, search: url.search, assign });
}
function returnPathOf(loginUrl: string) {
  const [pathname, query] = loginUrl.split("?");
  expect(pathname).toBe("/login");
  return new URLSearchParams(query).get("return_path");
}
describe("redirectToLogin return path", () => {
  beforeEach(() => assign.mockReset());
  afterEach(() => vi.unstubAllGlobals());
  it("keeps the follow-up view and request ID so sign-in returns to the form", () => {
    openAt(followUpPath);
    redirectToLogin({ reason: "unauthorized" });
    expect(assign).toHaveBeenCalledOnce();
    const loginUrl = assign.mock.calls[0][0] as string;
    expect(loginUrl).toContain(`return_path=${encodeURIComponent(followUpPath)}`);
    expect(returnPathOf(loginUrl)).toBe(followUpPath);
    expect(new URLSearchParams(loginUrl.split("?")[1]).get("reason")).toBe("unauthorized");
  });
  it("keeps the assessment link used by notifications", () => {
    const path = `/chat?view=follow-up&assessment=${requestId}`;
    openAt(path);
    redirectToLogin();
    expect(returnPathOf(assign.mock.calls[0][0])).toBe(path);
  });
  it("prefers an explicit return path", () => {
    openAt("/today");
    redirectToLogin({ returnPath: followUpPath });
    expect(returnPathOf(assign.mock.calls[0][0])).toBe(followUpPath);
  });
  it("does not redirect when already on the login page", () => {
    openAt("/login?return_path=%2Fchat");
    redirectToLogin();
    expect(assign).not.toHaveBeenCalled();
  });
});
