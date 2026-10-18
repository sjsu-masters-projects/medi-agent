import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useState } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NOTIFICATION_MIN_GAP_MS, NOTIFICATION_POLL_MS, NotificationProvider, useNotifications } from "@/contexts/notifications-context";
import { NotificationBell, NotificationCentre } from "@/components/features/notification-centre";
import { notifications } from "@/services/notifications";
import type { NotificationPage, PatientNotification } from "@/types/notifications";
import { ApiClientError } from "@/services/api";

const session = vi.hoisted(() => ({ auth: { accessToken: "synthetic-token", user: { id: "patient-one" } }, profile: { preferredLanguage: "en-US", timezone: "America/Los_Angeles" } }));
vi.mock("react-redux", () => ({ useSelector: (select: (state: unknown) => unknown) => select({ auth: session.auth }) }));
vi.mock("@/contexts/patient-profile-context", () => ({ useSharedPatientProfile: () => ({ profile: session.profile }) }));
vi.mock("@/services/notifications", async () => ({ ...await vi.importActual("@/services/notifications"), notifications: { list: vi.fn(), summary: vi.fn(), read: vi.fn(), readThrough: vi.fn() } }));
const item = (id = "one"): PatientNotification => ({ id, event_type: "message", category: "messages", title: `Care team ${id}`, body: "Original question\nKeep this clinical text intact.", created_at: "2026-10-11T01:00:00Z", is_read: false, action_url: "/chat?view=care-team&conversation=exact", action_label: "Open conversation", actionable: true, can_acknowledge: false });
const page = (items = [item()], next_cursor: string | null = null, read_through: string | null = "snapshot-one"): NotificationPage => ({ items, next_cursor, read_through });
function Draft() { const [value, setValue] = useState(""); return <input aria-label="Uncertain draft" value={value} onChange={(event) => setValue(event.target.value)} />; }
function SnapshotProbe() {
  const { canMarkDisplayed, markAllRead } = useNotifications();
  return <><output aria-label="Snapshot authorization">{String(canMarkDisplayed)}</output><button type="button" onClick={() => void markAllRead()}>Probe snapshot write</button></>;
}
function App() { return <NotificationProvider><Draft /><NotificationBell /><NotificationCentre /></NotificationProvider>; }
beforeEach(() => {
  vi.resetAllMocks();
  session.auth = { accessToken: "synthetic-token", user: { id: "patient-one" } };
  session.profile = { preferredLanguage: "en-US", timezone: "America/Los_Angeles" };
  vi.mocked(notifications.list).mockResolvedValue(page());
  vi.mocked(notifications.summary).mockResolvedValue({ unread_count: 1, action_item_count: 0 });
  vi.mocked(notifications.read).mockResolvedValue(); vi.mocked(notifications.readThrough).mockResolvedValue({ skipped: 0 });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });

describe("patient notification centre", () => {
  it.each([401, 403])("forgets snapshots, bulk capability and loaded depth on denied refresh (%s)", async (status) => {
    vi.mocked(notifications.list).mockImplementation(async (_token, _locale, _unread, cursor) => cursor ? page([item("two")], null, "snapshot-two") : page([item()], "cursor-two"));
    render(<NotificationProvider><NotificationCentre /><SnapshotProbe /></NotificationProvider>);
    await screen.findByText("Care team one");
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("Care team two");
    expect(screen.getByLabelText("Snapshot authorization")).toHaveTextContent("true");
    vi.mocked(notifications.list).mockRejectedValueOnce(new ApiClientError("Denied", status, null));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Snapshot authorization")).toHaveTextContent("false");
    fireEvent.click(screen.getByRole("button", { name: "Probe snapshot write" }));
    expect(notifications.readThrough).not.toHaveBeenCalled();
    vi.mocked(notifications.list).mockClear();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByText("Care team one");
    expect(notifications.list).toHaveBeenCalledTimes(1);
    expect(screen.queryByText("Care team two")).not.toBeInTheDocument();
  });
  it.each([401, 403])("forgets snapshots and bulk capability on denied own read (%s)", async (status) => {
    render(<NotificationProvider><NotificationCentre /><SnapshotProbe /></NotificationProvider>);
    await screen.findByText("Care team one");
    vi.mocked(notifications.read).mockRejectedValueOnce(new ApiClientError("Denied", status, null));
    fireEvent.click(screen.getByRole("button", { name: "Mark as read: Care team one" }));
    await screen.findByRole("alert");
    expect(screen.getByLabelText("Snapshot authorization")).toHaveTextContent("false");
    fireEvent.click(screen.getByRole("button", { name: "Probe snapshot write" }));
    expect(notifications.readThrough).not.toHaveBeenCalled();
    expect(screen.queryByText("Care team one")).not.toBeInTheDocument();
  });
  it("uses saved date/locale, exact destinations and confirmed own read", async () => {
    render(<App />);
    await screen.findByText("Care team one");
    expect(screen.getByText(/Keep this clinical text intact/)).toHaveClass("whitespace-pre-wrap");
    expect(screen.getByRole("link", { name: "Open conversation" })).toHaveAttribute("href", item().action_url);
    // The row shows a short time; the full saved-timezone date is its accessible name.
    expect(screen.getByLabelText("Oct 10, 2026, 6:00 PM")).toHaveAttribute("dateTime", item().created_at);
    fireEvent.click(screen.getByRole("button", { name: "Mark as read: Care team one" }));
    await waitFor(() => expect(notifications.read).toHaveBeenCalledWith("synthetic-token", "one"));
  });
  it("marks an item read when its link is followed, and keeps links on history items", async () => {
    vi.mocked(notifications.list).mockResolvedValue(page([item(), { ...item("past"), actionable: false, action_label: "View" }]));
    render(<NotificationProvider><NotificationCentre /></NotificationProvider>);
    await screen.findByText("Care team one");
    expect(screen.getByRole("link", { name: "View" })).toHaveAttribute("href", item().action_url);
    fireEvent.click(screen.getByRole("link", { name: "Open conversation" }));
    await waitFor(() => expect(notifications.read).toHaveBeenCalledWith("synthetic-token", "one"));
  });

  it("tells the patient when mark-all skipped items that are no longer available", async () => {
    vi.mocked(notifications.readThrough).mockResolvedValue({ skipped: 2 });
    render(<NotificationProvider><NotificationCentre /></NotificationProvider>);
    await screen.findByText("Care team one");
    fireEvent.click(screen.getByRole("button", { name: "Mark displayed as read" }));
    expect(await screen.findByText("2 notifications are no longer available and were skipped.")).toBeInTheDocument();
  });

  it("preserves a draft across JWT refresh and saved-language change, while discarding stale notification responses", async () => {
    let resolveOld!: (value: NotificationPage) => void;
    vi.mocked(notifications.list).mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    const view = render(<App />);
    fireEvent.change(screen.getByRole("textbox", { name: "Uncertain draft" }), { target: { value: "Do not lose my retry body" } });
    session.auth.accessToken = "refreshed-token";
    view.rerender(<App />);
    await screen.findByText("Care team one");
    await act(async () => resolveOld(page([item("stale")])));
    expect(screen.queryByText("Care team stale")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("Do not lose my retry body");
    session.profile.preferredLanguage = "es-MX";
    view.rerender(<App />);
    await screen.findByRole("button", { name: "Marcar como leída: Care team one" });
    expect(screen.getByRole("textbox")).toHaveValue("Do not lose my retry body");
    expect(notifications.list).toHaveBeenLastCalledWith("refreshed-token", "es-MX", false, undefined, expect.any(AbortSignal));
  });
  it("keeps rows and the last count when a manual refresh fails, and says so", async () => {
    render(<App />); await screen.findByText("Care team one");
    vi.mocked(notifications.list).mockRejectedValueOnce(new TypeError());
    vi.mocked(notifications.summary).mockRejectedValueOnce(new TypeError());
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("alert");
    expect(screen.getByText("Care team one")).toBeInTheDocument();
    expect(screen.queryByText("0 unread")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications · 1 unread" })).toBeInTheDocument();
  });
  it("shows an unavailable count, not zero, when the first load never succeeded", async () => {
    vi.mocked(notifications.list).mockRejectedValue(new TypeError());
    vi.mocked(notifications.summary).mockRejectedValue(new TypeError());
    render(<App />);
    await screen.findByText("Count unavailable.");
    expect(screen.getByRole("button", { name: "Notifications · Count unavailable." })).toBeInTheDocument();
  });
  it("keeps what is shown, with no banner, when background polls hit a slow server, then backs off", async () => {
    vi.useFakeTimers();
    render(<App />);
    await act(async () => {});
    expect(notifications.list).toHaveBeenCalledTimes(1);
    vi.mocked(notifications.list).mockRejectedValue(new ApiClientError("Unavailable", 502, null));
    vi.mocked(notifications.summary).mockRejectedValue(new ApiClientError("Unavailable", 502, null));
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_POLL_MS));
    expect(notifications.list).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notifications · 1 unread" })).toBeInTheDocument();
    // The next attempt waits twice as long; a recovery returns to the normal pace.
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_POLL_MS));
    expect(notifications.list).toHaveBeenCalledTimes(2);
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_POLL_MS));
    expect(notifications.list).toHaveBeenCalledTimes(3);
    vi.mocked(notifications.list).mockResolvedValue(page());
    vi.mocked(notifications.summary).mockResolvedValue({ unread_count: 3, action_item_count: 0 });
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_POLL_MS * 4));
    expect(notifications.list).toHaveBeenCalledTimes(4);
    expect(screen.getByRole("button", { name: "Notifications · 3 unread" })).toBeInTheDocument();
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_POLL_MS));
    expect(notifications.list).toHaveBeenCalledTimes(5);
  });
  it("answers a burst of focus and visibility events with one refresh and never interrupts a running one", async () => {
    vi.useFakeTimers();
    render(<App />);
    await act(async () => {});
    expect(notifications.list).toHaveBeenCalledTimes(1);
    await act(async () => {
      window.dispatchEvent(new Event("focus"));
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(notifications.list).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_MIN_GAP_MS + 1));
    let release!: (value: NotificationPage) => void;
    vi.mocked(notifications.list).mockImplementationOnce(() => new Promise((resolve) => { release = resolve; }));
    await act(async () => { window.dispatchEvent(new Event("focus")); });
    expect(notifications.list).toHaveBeenCalledTimes(2);
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_MIN_GAP_MS + 1));
    await act(async () => { window.dispatchEvent(new Event("focus")); document.dispatchEvent(new Event("visibilitychange")); });
    expect(notifications.list).toHaveBeenCalledTimes(2);
    await act(async () => release(page()));
  });
  it("rejects an obsolete All response after changing to Unread", async () => {
    let resolveOld!: (value: NotificationPage) => void;
    vi.mocked(notifications.list).mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }));
    render(<App />);
    fireEvent.click(screen.getByRole("button", { name: "Unread" }));
    await screen.findByText("Care team one");
    await act(async () => resolveOld(page([item("obsolete")])));
    expect(screen.queryByText("Care team obsolete")).not.toBeInTheDocument();
    expect(notifications.list).toHaveBeenLastCalledWith("synthetic-token", "en-US", true, undefined, expect.any(AbortSignal));
  });
  it("does not mark a concurrently arriving notification from an older displayed snapshot", async () => {
    let finishWrite!: () => void;
    vi.mocked(notifications.readThrough).mockImplementationOnce(() => new Promise((resolve) => { finishWrite = () => resolve({ skipped: 0 }); }));
    render(<App />); await screen.findByText("Care team one");
    fireEvent.click(screen.getByRole("button", { name: "Mark displayed as read" }));
    vi.mocked(notifications.list).mockResolvedValue(page([{ ...item(), is_read: true }, item("new-arrival")], null, "new-snapshot"));
    await act(async () => finishWrite());
    await screen.findByRole("button", { name: "Mark as read: Care team new-arrival" });
    expect(notifications.readThrough).toHaveBeenCalledExactlyOnceWith("synthetic-token", "snapshot-one");
  });
  it("clears private cache and draft state across a different authenticated user", async () => {
    const view = render(<App />); await screen.findByText("Care team one");
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Private draft" } });
    session.auth = { user: { id: "patient-two" }, accessToken: "second-token" };
    vi.mocked(notifications.list).mockResolvedValue(page([item("second-user")]));
    view.rerender(<App />);
    await screen.findByText("Care team second-user");
    expect(screen.queryByText("Care team one")).not.toBeInTheDocument();
    expect(screen.getByRole("textbox")).toHaveValue("");
  });
  it("clears private details on revoked access", async () => {
    render(<App />); await screen.findByText("Care team one");
    vi.mocked(notifications.list).mockRejectedValueOnce(new ApiClientError("Denied", 403, null));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("alert");
    expect(screen.queryByText("Care team one")).not.toBeInTheDocument();
  });
  it("refreshes all loaded history pages and writes only each displayed signed snapshot", async () => {
    vi.mocked(notifications.list).mockImplementation(async (_token, _locale, _unread, cursor) => cursor ? page([item("two")], null, "snapshot-two") : page([item()], "cursor-two"));
    render(<App />); await screen.findByText("Care team one");
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await screen.findByText("Care team two");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(notifications.list).toHaveBeenCalledTimes(4));
    expect(screen.getByText("Care team two")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Mark displayed as read" }));
    await waitFor(() => expect(notifications.readThrough).toHaveBeenCalledTimes(2));
    expect(notifications.readThrough).toHaveBeenNthCalledWith(1, "synthetic-token", "snapshot-one");
    expect(notifications.readThrough).toHaveBeenNthCalledWith(2, "synthetic-token", "snapshot-two");
  });
  it("disables empty snapshots and preserves uncertainty on expired read snapshots", async () => {
    vi.mocked(notifications.list).mockResolvedValueOnce(page([], null, null));
    render(<App />);
    await screen.findByText("No notifications yet.");
    expect(screen.getByRole("button", { name: "Mark displayed as read" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByText("Care team one");
    vi.mocked(notifications.readThrough).mockRejectedValueOnce(new ApiClientError("Expired snapshot", 400, null));
    fireEvent.click(screen.getByRole("button", { name: "Mark displayed as read" }));
    await screen.findByText("Read could not be confirmed. Refresh before trying again.");
    expect(screen.getByText("Care team one")).toBeInTheDocument();
  });
  it("shares one visible/focus poll and stops on teardown", async () => {
    vi.useFakeTimers();
    const view = render(<App />);
    await act(async () => {});
    expect(notifications.list).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "Notifications · 1 unread" }));
    await act(async () => vi.advanceTimersByTime(15_000));
    expect(notifications.list).toHaveBeenCalledTimes(1);
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_POLL_MS - 15_000));
    expect(notifications.list).toHaveBeenCalledTimes(2);
    const visibility = vi.spyOn(document, "visibilityState", "get").mockReturnValue("hidden");
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_POLL_MS));
    expect(notifications.list).toHaveBeenCalledTimes(2);
    visibility.mockReturnValue("visible");
    await act(async () => window.dispatchEvent(new Event("focus")));
    expect(notifications.list).toHaveBeenCalledTimes(3);
    view.unmount();
    await act(async () => vi.advanceTimersByTime(NOTIFICATION_POLL_MS));
    expect(notifications.list).toHaveBeenCalledTimes(3);
    visibility.mockRestore();
  });
  it("traps keyboard focus in the sheet, closes on Escape and returns focus to the bell", async () => {
    render(<App />); await screen.findByText("Care team one");
    const bell = screen.getByRole("button", { name: "Notifications · 1 unread" });
    bell.focus(); fireEvent.click(bell);
    const dialog = screen.getByRole("dialog", { name: "Notifications" });
    expect(within(dialog).getByRole("button", { name: "Close notifications" })).toHaveFocus();
    within(dialog).getByRole("link", { name: "View all notifications" }).focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(within(dialog).getByRole("button", { name: "Close notifications" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument(); expect(bell).toHaveFocus();
  });
  it.each([["en-US", "Care team one"], ["es-MX", "Care team one"]])("shows the clinic as wrapping secondary text under the title in %s", async (locale) => {
    session.profile = { preferredLanguage: locale, timezone: "America/Los_Angeles" };
    vi.mocked(notifications.list).mockResolvedValue(page([{ ...item(), clinic_name: "Harbor Clinic de la Costa Norte" }, item("two")]));
    render(<NotificationProvider><NotificationCentre /></NotificationProvider>);
    const clinic = await screen.findByText("Harbor Clinic de la Costa Norte");
    expect(clinic.className).toContain("text-muted");
    expect(clinic.className).toContain("break-words");
    expect(clinic.previousElementSibling).toContainElement(screen.getByText("Care team one"));
    expect(screen.queryByText("Harbor Clinic")).not.toBeInTheDocument();
  });
});
