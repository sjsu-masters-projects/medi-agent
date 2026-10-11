import { describe, expect, it, vi } from "vitest";
import { api } from "@/services/api";
import { notificationDestination, notifications } from "@/services/notifications";
vi.mock("@/services/api", () => ({ api: { get: vi.fn(), put: vi.fn(), post: vi.fn() } }));

describe("patient notification contract", () => {
  it("sends only authenticated contract parameters and opaque snapshots", async () => {
    const controller = new AbortController();
    await notifications.list("synthetic-token", "es-MX", true, "opaque + cursor", controller.signal);
    await notifications.summary("synthetic-token", controller.signal);
    await notifications.read("synthetic-token", "own/id");
    await notifications.readThrough("synthetic-token", "signed-snapshot");
    expect(api.get).toHaveBeenCalledWith("/api/v1/notification-centre?locale=es-MX&unread=true&limit=50&cursor=opaque+%2B+cursor", { token: "synthetic-token", signal: controller.signal });
    expect(api.get).toHaveBeenCalledWith("/api/v1/notification-centre/summary", { token: "synthetic-token", signal: controller.signal });
    expect(api.put).toHaveBeenCalledWith("/api/v1/notification-centre/own%2Fid/read", undefined, { token: "synthetic-token" });
    expect(api.post).toHaveBeenCalledWith("/api/v1/notification-centre/read-through", { read_through: "signed-snapshot" }, { token: "synthetic-token" });
  });
  it.each([null, "https://example.com", "//example.com", "/\\example.com", "/login", "javascript:alert(1)", "/today\n"])("rejects unsafe/unrelated destination %s", (url) => {
    expect(notificationDestination(url)).toBeNull();
  });
  it.each(["/records?document=synthetic", "/today?activity=synthetic", "/today?view=care-plan", "/chat?view=care-team&conversation=synthetic", "/chat?view=care-team&recipient=synthetic", "/visits?appointmentId=synthetic"])("preserves exact authorized target %s", (url) => {
    expect(notificationDestination(url)).toBe(url);
  });
});
