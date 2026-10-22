import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { NOTIFICATION_MIN_GAP_MS, NOTIFICATION_POLL_MS, NotificationProvider, useNotificationCentre } from "@/components/features/notification-provider";
import { NotificationBell, NotificationList } from "@/components/features/notification-centre";
import AlertsPage from "@/app/(dashboard)/alerts/page";
import { notificationCentre } from "@/services/notification-centre";
import { ApiClientError } from "@/services/api";
import type { CentreItem, CentrePage } from "@/types/notification-centre";

const auth = vi.hoisted(() => ({ user: { id: "synthetic-clinician" } as { id: string } | null, accessToken: "token-one" as string | null }));
const navigation = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: navigation.push }) }));
vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("react-redux", () => ({ useSelector: (select: (state: unknown) => unknown) => select({ auth }) }));
vi.mock("@/services/notification-centre", () => ({
  notificationCentre: { list: vi.fn(), summary: vi.fn(), read: vi.fn(), readThrough: vi.fn(), acknowledge: vi.fn() },
  notificationTarget: (url: string | null) => url?.startsWith("/") ? url : null,
}));

const item = (overrides: Partial<CentreItem> = {}): CentreItem => ({
  id: "receipt-1", event_type: "barrier.saved", category: "follow_up", title: "Patient reported a barrier", body: "Synthetic barrier details",
  created_at: "2026-10-11T12:00:00Z", is_read: false, action_url: "/patients/p1?tab=adherence&activity=med-1", action_label: "Review barrier", actionable: true, can_acknowledge: true, ...overrides,
});
const page = (items: CentreItem[] = [item()], overrides: Partial<CentrePage> = {}): CentrePage => ({ items, next_cursor: null, read_through: "signed-first-page", ...overrides });
function Probe() {
  const centre = useNotificationCentre();
  const [draft, setDraft] = useState("");
  return <><input aria-label="Retained draft" value={draft} onChange={(event) => setDraft(event.target.value)} /><p>{centre.history.data?.items[0]?.title}</p><button onClick={() => void centre.acknowledge(item({ can_acknowledge: true }))}>Attempt acknowledgement</button></>;
}
beforeEach(() => {
  vi.resetAllMocks(); auth.user = { id: "synthetic-clinician" }; auth.accessToken = "token-one";
  vi.mocked(notificationCentre.list).mockResolvedValue(page());
  vi.mocked(notificationCentre.summary).mockResolvedValue({ unread_count: 1, action_item_count: 1 });
  vi.mocked(notificationCentre.read).mockResolvedValue({});
  vi.mocked(notificationCentre.readThrough).mockResolvedValue({ skipped: 0 });
  vi.mocked(notificationCentre.acknowledge).mockResolvedValue({});
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("clinician notification centre", () => {
  it("confirms an unread receipt before following its destination", async () => {
    let confirmRead!: (value: unknown) => void;
    vi.mocked(notificationCentre.read).mockReturnValue(new Promise((resolve) => { confirmRead = resolve; }));
    vi.mocked(notificationCentre.list).mockResolvedValue(page([item({
      event_type: "message_received", category: "messages", title: "New message from Rajeev Chaurasia",
      action_url: "/messages?conversation=private-thread", action_label: "Open conversation",
    })]));
    render(<NotificationProvider><NotificationList /></NotificationProvider>);
    fireEvent.click(await screen.findByRole("link", { name: "Open conversation" }));
    expect(notificationCentre.read).toHaveBeenCalledWith("token-one", "receipt-1");
    expect(navigation.push).not.toHaveBeenCalled();
    await act(async () => { confirmRead({}); });
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/messages?conversation=private-thread"));
  });

  it("shows a clinic-level work item with no patient, no patient link and no placeholder text", async () => {
    vi.mocked(notificationCentre.list).mockResolvedValue(page([item({
      event_type: "care_plan_review", category: "care_plans", title: "A care plan at your clinic has no care team",
      body: "Open the clinic review page.", patient_name: null, clinic_name: "Cedar Grove", clinic_id: "c1",
      action_url: "/care-plan-reviews?clinic=c1&item=ci1", action_label: "Open clinic review", can_acknowledge: false,
    })]));
    const { container } = render(<NotificationProvider><NotificationList /></NotificationProvider>);
    const link = await screen.findByRole("link", { name: "Open clinic review" });
    expect(link).toHaveAttribute("href", "/care-plan-reviews?clinic=c1&item=ci1");
    expect(container.textContent).toContain("Cedar Grove");
    expect(container.textContent).not.toMatch(/undefined|null|\/patients\//);
    expect(container.querySelector('a[href*="/patients/"]')).toBeNull();
  });

  it("shares one cache between bell and Alerts, with no legacy archive on Alerts", async () => {
    render(<NotificationProvider><NotificationBell /><AlertsPage /></NotificationProvider>);
    await screen.findByText("Patient reported a barrier");
    expect(screen.getByText(/Your clinical action inbox/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Patient upload reviews" })).toHaveAttribute("href", "/review-queue");
    expect(notificationCentre.summary).toHaveBeenCalledTimes(1);
    expect(notificationCentre.list).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("link", { name: "Review barrier" })).toHaveAttribute("href", "/patients/p1?tab=adherence&activity=med-1");
    fireEvent.click(screen.getByRole("button", { name: "History" }));
    expect(screen.queryByText(/Earlier messages|Legacy sent-message archive/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Acknowledge" })).not.toBeInTheDocument();
    expect(notificationCentre.list).toHaveBeenCalledTimes(2);
  });

  it("opens an accessible panel, filters unread and returns focus on Escape", async () => {
    vi.mocked(notificationCentre.list).mockResolvedValue(page([item(), item({ id: "read", title: "Read notification", is_read: true, can_acknowledge: false })]));
    render(<NotificationProvider><NotificationBell /></NotificationProvider>);
    const bell = await screen.findByRole("button", { name: "Open notifications: 1 unread" });
    bell.focus(); fireEvent.click(bell);
    const dialog = screen.getByRole("dialog", { name: "Notifications" });
    expect(within(dialog).getByRole("link", { name: "Open Alerts" })).toHaveAttribute("href", "/alerts");
    fireEvent.click(within(dialog).getByRole("button", { name: "Unread" }));
    expect(screen.queryByText("Read notification")).not.toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(bell).toHaveFocus();
  });

  it("explains the authoritative source and distinguishes a state snapshot from clinical review", async () => {
    vi.mocked(notificationCentre.list).mockResolvedValue(page([item({
      source_label: "Confirmed patient symptom report", state_checked_at: "2026-10-21T10:00:00Z",
    })]));
    render(<NotificationProvider><NotificationList actions /></NotificationProvider>);
    fireEvent.click(await screen.findByText("Source and freshness"));
    expect(screen.getByText("Source: Confirmed patient symptom report")).toBeVisible();
    expect(screen.getByText(/not the last clinical review/)).toBeVisible();
    expect(document.querySelector('time[datetime="2026-10-21T10:00:00Z"]')).toBeInTheDocument();
  });

  it("records a note only after explicit acknowledgement and never treats read as acknowledgement", async () => {
    render(<NotificationProvider><NotificationList /><NotificationList actions /></NotificationProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "Mark read: Patient reported a barrier" }));
    await waitFor(() => expect(notificationCentre.read).toHaveBeenCalledWith("token-one", "receipt-1"));
    expect(notificationCentre.acknowledge).not.toHaveBeenCalled();
    await waitFor(() => expect(screen.getByRole("button", { name: "Acknowledge" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "Acknowledge" }));
    fireEvent.change(screen.getByLabelText("Optional note"), { target: { value: "Reviewing follow-up" } });
    expect(notificationCentre.acknowledge).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Record acknowledgement" }));
    await waitFor(() => expect(notificationCentre.acknowledge).toHaveBeenCalledWith("token-one", "receipt-1", "Reviewing follow-up"));
  });

  it("enforces server acknowledgement eligibility even if a caller supplies true", async () => {
    vi.mocked(notificationCentre.list).mockResolvedValue(page([item({ can_acknowledge: false })]));
    render(<NotificationProvider><Probe /><NotificationList actions /></NotificationProvider>);
    await screen.findByText("Synthetic barrier details");
    expect(screen.queryByRole("button", { name: "Acknowledge" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Attempt acknowledgement" }));
    expect(notificationCentre.acknowledge).not.toHaveBeenCalled();
  });

  it("requests the selected action category and retains it when following a cursor", async () => {
    vi.mocked(notificationCentre.list).mockImplementation(async (_token, actions, cursor, _signal, category) => actions && category === "documents"
      ? page([item({ category: "documents", title: cursor ? "Earlier document" : "Document review", can_acknowledge: false })], { next_cursor: cursor ? null : "document-cursor" }) : page());
    render(<NotificationProvider><NotificationList actions /></NotificationProvider>);
    await screen.findByText("Patient reported a barrier");
    fireEvent.change(screen.getByRole("combobox", { name: "Category" }), { target: { value: "documents" } });
    await screen.findByText("Document review");
    expect(screen.queryByText("Patient reported a barrier")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("Earlier document");
    expect(notificationCentre.list).toHaveBeenCalledWith("token-one", true, "document-cursor", undefined, "documents");
  });

  it("marks loaded pages through their signed snapshots, with no new-arrival ID or clock", async () => {
    vi.mocked(notificationCentre.list).mockImplementation(async (_token, actions, cursor) => actions ? page([]) : cursor ? page([item({ id: "older", title: "Older receipt" })], { read_through: "signed-second-page" }) : page([item()], { next_cursor: "opaque-cursor" }));
    render(<NotificationProvider><NotificationList /></NotificationProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
    await screen.findByText("Older receipt");
    expect(notificationCentre.list).toHaveBeenCalledWith("token-one", false, "opaque-cursor");
    fireEvent.click(screen.getByRole("button", { name: "Mark all loaded read" }));
    await waitFor(() => expect(notificationCentre.readThrough).toHaveBeenCalledTimes(2));
    expect(vi.mocked(notificationCentre.readThrough).mock.calls).toEqual([["token-one", "signed-first-page"], ["token-one", "signed-second-page"]]);
  });

  it("disables snapshot read when the server returns null", async () => {
    vi.mocked(notificationCentre.list).mockResolvedValue(page([], { read_through: null }));
    render(<NotificationProvider><NotificationList /></NotificationProvider>);
    await screen.findByText("No notifications in this view.");
    expect(screen.getByRole("button", { name: "Mark all loaded read" })).toBeDisabled();
  });

  it.each([401, 403])("clears receipts and signed snapshots when loading more returns %s", async (status) => {
    vi.mocked(notificationCentre.list).mockImplementation(async (_token, _actions, cursor) => {
      if (cursor) throw new ApiClientError("Denied", status, null);
      return page([item()], { next_cursor: "older-page" });
    });
    render(<NotificationProvider><NotificationList /></NotificationProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
    await screen.findByText("Access to alerts is unavailable.");
    expect(screen.queryByText("Patient reported a barrier")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Mark all loaded read" })).toBeDisabled();
    expect(notificationCentre.readThrough).not.toHaveBeenCalled();
  });

  it.each(["token refresh", "account change", "logout"])("stops a bulk read before the next snapshot after %s", async (change) => {
    let finishFirst!: (value: unknown) => void;
    vi.mocked(notificationCentre.readThrough).mockImplementationOnce(() => new Promise((resolve) => { finishFirst = () => resolve({ skipped: 0 }); }));
    vi.mocked(notificationCentre.list).mockImplementation(async (_token, actions, cursor) => actions ? page([]) : cursor ? page([item({ id: "older", title: "Older receipt" })], { read_through: "signed-second-page" }) : page([item()], { next_cursor: "opaque-cursor" }));
    const view = render(<NotificationProvider><NotificationList /></NotificationProvider>);
    fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
    await screen.findByText("Older receipt");
    fireEvent.click(screen.getByRole("button", { name: "Mark all loaded read" }));
    await waitFor(() => expect(notificationCentre.readThrough).toHaveBeenCalledTimes(1));
    if (change === "token refresh") auth.accessToken = "token-two";
    else if (change === "account change") auth.user = { id: "another-clinician" };
    else { auth.accessToken = null; auth.user = null; }
    view.rerender(<NotificationProvider><NotificationList /></NotificationProvider>);
    await act(async () => { finishFirst({}); });
    expect(notificationCentre.readThrough).toHaveBeenCalledTimes(1);
    expect(notificationCentre.readThrough).toHaveBeenCalledWith("token-one", "signed-first-page");
  });

  it("preserves loaded data on refresh failure and represents summary failure as unavailable", async () => {
    render(<NotificationProvider><NotificationBell /><NotificationList actions /></NotificationProvider>);
    await screen.findByText("Patient reported a barrier");
    vi.mocked(notificationCentre.list).mockRejectedValue(new Error("offline"));
    vi.mocked(notificationCentre.summary).mockRejectedValue(new Error("offline"));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("button", { name: "Open notifications: count unavailable" });
    expect(screen.getByText("Patient reported a barrier")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Previously loaded data remains visible");
    expect(screen.getByRole("button", { name: "Acknowledge" })).toBeDisabled();
  });

  it("clears denied data", async () => {
    render(<NotificationProvider><NotificationList /></NotificationProvider>);
    await screen.findByText("Patient reported a barrier");
    vi.mocked(notificationCentre.list).mockRejectedValue(new ApiClientError("Denied", 403, null));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByText("Access to alerts is unavailable.");
    expect(screen.queryByText("Patient reported a barrier")).not.toBeInTheDocument();
  });

  it("refreshes every minute only while visible, refreshes on focus, and stops on teardown", async () => {
    vi.useFakeTimers();
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    const view = render(<NotificationProvider><Probe /></NotificationProvider>);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(15000); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_MS - 15000); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(2);
    visibility.mockReturnValue("hidden");
    await act(async () => { await vi.advanceTimersByTimeAsync(2 * NOTIFICATION_POLL_MS); window.dispatchEvent(new Event("focus")); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(2);
    visibility.mockReturnValue("visible");
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(3);
    view.unmount();
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_MS); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(3);
    visibility.mockRestore();
  });

  it("keeps the last alerts without a banner when background polls fail, then backs off", async () => {
    vi.useFakeTimers();
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    render(<NotificationProvider><Probe /><NotificationList /></NotificationProvider>);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(1);
    vi.mocked(notificationCentre.list).mockRejectedValue(new ApiClientError("Unavailable", 502, null));
    vi.mocked(notificationCentre.summary).mockRejectedValue(new ApiClientError("Unavailable", 502, null));
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_MS); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(2);
    expect(screen.queryByText(/Could not refresh alerts/)).not.toBeInTheDocument();
    expect(screen.getAllByText("Patient reported a barrier").length).toBeGreaterThan(0);
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_MS); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(2);
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_POLL_MS); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(3);
    visibility.mockRestore();
  });

  it("answers a burst of focus and visibility events with one refresh", async () => {
    vi.useFakeTimers();
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("visible");
    render(<NotificationProvider><Probe /></NotificationProvider>);
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    await act(async () => { window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange")); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(1);
    await act(async () => { await vi.advanceTimersByTimeAsync(NOTIFICATION_MIN_GAP_MS + 1); });
    await act(async () => { window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange")); });
    expect(notificationCentre.summary).toHaveBeenCalledTimes(2);
    visibility.mockRestore();
  });

  it("retains child drafts on JWT refresh while rejecting the previous token's late response", async () => {
    let resolveOld!: (value: CentrePage) => void;
    vi.mocked(notificationCentre.list).mockImplementation((token) => token === "token-one" ? new Promise((resolve) => { resolveOld = resolve; }) : Promise.resolve(page([item({ title: "New session receipt" })])));
    const view = render(<NotificationProvider><Probe /></NotificationProvider>);
    await waitFor(() => expect(notificationCentre.list).toHaveBeenCalledTimes(2));
    fireEvent.change(screen.getByLabelText("Retained draft"), { target: { value: "Unconfirmed reply" } });
    auth.accessToken = "token-two";
    view.rerender(<NotificationProvider><Probe /></NotificationProvider>);
    await screen.findByText("New session receipt");
    expect(screen.getByLabelText("Retained draft")).toHaveValue("Unconfirmed reply");
    await act(async () => { resolveOld(page([item({ title: "Old unauthorized response" })])); });
    expect(screen.queryByText("Old unauthorized response")).not.toBeInTheDocument();
    auth.user = { id: "another-clinician" };
    view.rerender(<NotificationProvider><Probe /></NotificationProvider>);
    expect(screen.getByLabelText("Retained draft")).toHaveValue("");
  });
});
