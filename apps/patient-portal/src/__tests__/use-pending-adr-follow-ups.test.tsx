import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ADR_REQUESTS_POLL_MS, usePendingADRFollowUps } from "@/hooks/use-pending-adr-follow-ups";
import type { ADRInformationRequest } from "@/services/adr-follow-up";
const { fetchADRInformationRequests } = vi.hoisted(() => ({ fetchADRInformationRequests: vi.fn() }));
let token: string | null;
vi.mock("@/services/adr-follow-up", () => ({ fetchADRInformationRequests }));
vi.mock("react-redux", () => ({
  useSelector: (selector: (state: unknown) => unknown) => selector({ auth: { accessToken: token } }),
}));
const requests = (count: number) => Array.from({ length: count }, (_, index) => ({ id: `request-${index}` }) as ADRInformationRequest);
function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
const flush = () => act(async () => { await Promise.resolve(); });
const focus = () => act(async () => { window.dispatchEvent(new Event("focus")); await Promise.resolve(); });
const becomeVisible = () => act(async () => { document.dispatchEvent(new Event("visibilitychange")); await Promise.resolve(); });
let visibility: DocumentVisibilityState;
describe("usePendingADRFollowUps", () => {
  beforeEach(() => {
    token = "session-a";
    visibility = "visible";
    fetchADRInformationRequests.mockReset();
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-10-12T12:00:00Z"));
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibility);
  });
  afterEach(() => { vi.restoreAllMocks(); vi.useRealTimers(); });
  it("fetches once on mount with the session token", async () => {
    fetchADRInformationRequests.mockResolvedValue(requests(2));
    const { result } = renderHook(usePendingADRFollowUps);
    expect(result.current).toEqual({ count: 0, loaded: false });
    await flush();
    expect(result.current).toEqual({ count: 2, loaded: true });
    expect(fetchADRInformationRequests).toHaveBeenCalledOnce();
    expect(fetchADRInformationRequests).toHaveBeenCalledWith("session-a");
  });
  it("shares one request between every row in the tab", async () => {
    fetchADRInformationRequests.mockResolvedValue(requests(3));
    const first = renderHook(usePendingADRFollowUps);
    const second = renderHook(usePendingADRFollowUps);
    await flush();
    expect(fetchADRInformationRequests).toHaveBeenCalledOnce();
    expect(first.result.current).toEqual({ count: 3, loaded: true });
    expect(second.result.current).toEqual({ count: 3, loaded: true });
  });
  it("polls at most once a minute: focus and visibility inside the minute reuse the result", async () => {
    fetchADRInformationRequests.mockResolvedValueOnce(requests(1)).mockResolvedValue(requests(0));
    const { result } = renderHook(usePendingADRFollowUps);
    await flush();
    await focus();
    await becomeVisible();
    vi.setSystemTime(Date.now() + ADR_REQUESTS_POLL_MS - 1);
    await focus();
    expect(fetchADRInformationRequests).toHaveBeenCalledTimes(1);
    vi.setSystemTime(Date.now() + 1);
    await focus();
    await becomeVisible();
    expect(fetchADRInformationRequests).toHaveBeenCalledTimes(2);
    expect(result.current).toEqual({ count: 0, loaded: true });
  });
  it("refreshes on the minute while visible and never while hidden", async () => {
    vi.useFakeTimers({ toFake: ["Date", "setTimeout", "clearTimeout"] });
    vi.setSystemTime(new Date("2026-10-12T12:00:00Z"));
    fetchADRInformationRequests.mockResolvedValue(requests(1));
    renderHook(usePendingADRFollowUps);
    await flush();
    await act(async () => { await vi.advanceTimersByTimeAsync(ADR_REQUESTS_POLL_MS); });
    expect(fetchADRInformationRequests).toHaveBeenCalledTimes(2);
    visibility = "hidden";
    await act(async () => { await vi.advanceTimersByTimeAsync(ADR_REQUESTS_POLL_MS * 5); });
    expect(fetchADRInformationRequests).toHaveBeenCalledTimes(2);
    visibility = "visible";
    await becomeVisible();
    expect(fetchADRInformationRequests).toHaveBeenCalledTimes(3);
  });
  it("skips the refetch while the tab is hidden", async () => {
    fetchADRInformationRequests.mockResolvedValue(requests(1));
    renderHook(usePendingADRFollowUps);
    await flush();
    vi.setSystemTime(Date.now() + ADR_REQUESTS_POLL_MS);
    visibility = "hidden";
    await focus();
    await becomeVisible();
    expect(fetchADRInformationRequests).toHaveBeenCalledTimes(1);
    visibility = "visible";
    await becomeVisible();
    expect(fetchADRInformationRequests).toHaveBeenCalledTimes(2);
  });
  it("ignores a stale response that arrives after a newer request", async () => {
    const first = deferred<ADRInformationRequest[]>();
    const second = deferred<ADRInformationRequest[]>();
    fetchADRInformationRequests.mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise);
    const { result } = renderHook(usePendingADRFollowUps);
    vi.setSystemTime(Date.now() + ADR_REQUESTS_POLL_MS);
    await focus();
    expect(fetchADRInformationRequests).toHaveBeenCalledTimes(2);
    await act(async () => second.resolve(requests(2)));
    expect(result.current).toEqual({ count: 2, loaded: true });
    await act(async () => first.resolve(requests(1)));
    expect(result.current).toEqual({ count: 2, loaded: true });
  });
  it("reports no pending requests, but loaded, when the load fails", async () => {
    fetchADRInformationRequests.mockRejectedValue(new Error("network down"));
    const { result } = renderHook(usePendingADRFollowUps);
    await flush();
    expect(result.current).toEqual({ count: 0, loaded: true });
  });
  it("does not fetch or load without an access token", async () => {
    token = null;
    const { result } = renderHook(usePendingADRFollowUps);
    await focus();
    expect(fetchADRInformationRequests).not.toHaveBeenCalled();
    expect(result.current).toEqual({ count: 0, loaded: false });
  });
  it("clears at once on a token change and drops the previous session's late response", async () => {
    const late = deferred<ADRInformationRequest[]>();
    fetchADRInformationRequests.mockReturnValueOnce(late.promise).mockResolvedValueOnce(requests(1));
    const { result, rerender } = renderHook(usePendingADRFollowUps);
    token = "session-b";
    rerender();
    expect(result.current).toEqual({ count: 0, loaded: false });
    expect(fetchADRInformationRequests).toHaveBeenLastCalledWith("session-b");
    await flush();
    expect(result.current).toEqual({ count: 1, loaded: true });
    await act(async () => late.resolve(requests(2)));
    expect(result.current).toEqual({ count: 1, loaded: true });
  });
  it("hides the previous session's count as soon as the token changes", async () => {
    fetchADRInformationRequests.mockResolvedValueOnce(requests(2)).mockReturnValueOnce(new Promise(() => {}));
    const { result, rerender } = renderHook(usePendingADRFollowUps);
    await flush();
    expect(result.current).toEqual({ count: 2, loaded: true });
    token = "session-b";
    rerender();
    expect(result.current).toEqual({ count: 0, loaded: false });
  });
  it("clears on sign-out and stops listening after unmount", async () => {
    fetchADRInformationRequests.mockResolvedValue(requests(1));
    const { result, rerender, unmount } = renderHook(usePendingADRFollowUps);
    await flush();
    token = null;
    rerender();
    expect(result.current).toEqual({ count: 0, loaded: false });
    token = "session-a";
    rerender();
    await flush();
    const calls = fetchADRInformationRequests.mock.calls.length;
    unmount();
    vi.setSystemTime(Date.now() + 60_000);
    await focus();
    expect(fetchADRInformationRequests).toHaveBeenCalledTimes(calls);
  });
});
