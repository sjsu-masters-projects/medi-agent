import { beforeEach, describe, expect, it, vi } from "vitest";
import { api } from "@/services/api";
import { notificationCentre, notificationTarget } from "@/services/notification-centre";

vi.mock("@/services/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));
beforeEach(() => vi.clearAllMocks());

describe("notification centre contract", () => {
  it("forwards opaque cursors, English locale, auth and abort signal for both feeds", () => {
    const signal = new AbortController().signal;
    notificationCentre.list("session", false, "opaque +/", signal);
    notificationCentre.list("session", true, "next", signal);
    expect(api.get).toHaveBeenCalledWith("/api/v1/notification-centre?locale=en-US&limit=50&unread=false&cursor=opaque+%2B%2F", { token: "session", signal });
    expect(api.get).toHaveBeenCalledWith("/api/v1/notification-centre/action-items?locale=en-US&limit=50&cursor=next", { token: "session", signal });
  });
  it("uses the server snapshot verbatim and separates read from audited acknowledgement", () => {
    notificationCentre.read("session", "receipt");
    notificationCentre.readThrough("session", "opaque.signed.snapshot");
    notificationCentre.acknowledge("session", "work", "Reviewing");
    expect(api.put).toHaveBeenCalledWith("/api/v1/notification-centre/receipt/read", undefined, { token: "session" });
    expect(api.post).toHaveBeenCalledWith("/api/v1/notification-centre/read-through", { read_through: "opaque.signed.snapshot" }, { token: "session" });
    expect(api.post).toHaveBeenCalledWith("/api/v1/notification-centre/action-items/work/acknowledge", { note: "Reviewing" }, { token: "session" });
  });
  it.each([null, "https://example.com", "//example.com", "/\\example.com", "javascript:alert(1)", "/\nexample.com"])("rejects nonlocal target %s", (target) => {
    expect(notificationTarget(target)).toBeNull();
  });
  it.each(["/messages?conversation=thread", "/patients/p?tab=documents#document-d", "/patients/p?tab=care-plan", "/patients/p?tab=adherence&activity=med", "/patients/p?tab=chat", "/medwatch?assessment=adr", "/appointments?appointmentId=visit"])("preserves exact authorized target %s", (target) => {
    expect(notificationTarget(target)).toBe(target);
  });
});
