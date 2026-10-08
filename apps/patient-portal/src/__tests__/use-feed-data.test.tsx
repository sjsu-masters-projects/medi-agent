import { configureStore } from "@reduxjs/toolkit";
import { act, renderHook, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useFeedData } from "@/hooks/use-feed-data";
import { authSlice, hydrateSession } from "@/store/slices/auth-slice";
import { feedSlice } from "@/store/slices/feed-slice";
import { FeedTaskStatus, FeedTaskType, type FeedTask } from "@/types";
import { ApiTransportError } from "../../../../packages/shared/src/utils/api-transport";

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { get, post } }));
const task: FeedTask = { id: "task-1", targetId: "target-1", type: FeedTaskType.OBLIGATION, name: "Hydrate", frequency: "daily", status: FeedTaskStatus.PENDING, requiresScheduleConfiguration: false };
const summary = { completed: 0, missed: 0, skipped: 0, pending: 1, total: 1 };
function setup(authenticated = true, locale: "en-US" | "es-MX" = "en-US") {
    const store = configureStore({ reducer: { auth: authSlice.reducer, feed: feedSlice.reducer } });
    if (authenticated) store.dispatch(hydrateSession({ accessToken: "synthetic-token", refreshToken: "synthetic-refresh", expiresAt: 9999999999, user: { id: "patient-1", email: "test@example.test", role: "patient" } }));
    const wrapper = ({ children }: { children: ReactNode }) => <Provider store={store}>{children}</Provider>;
    return { store, ...renderHook(() => useFeedData(locale), { wrapper }) };
}
describe("saved adherence acknowledgement", () => {
    it("localizes an uncertain Spanish save without replaying or acknowledging it", async () => {
        post.mockRejectedValue(new ApiTransportError(true, 0));
        const { result } = setup(true, "es-MX");
        await waitFor(() => expect(result.current.tasks).toHaveLength(1));
        await act(async () => { expect(await result.current.markComplete(task)).toBe(false); });
        expect(result.current.actionError).toContain("Actualiza");
        expect(result.current.tasks[0].status).toBe(FeedTaskStatus.PENDING);
        expect(post).toHaveBeenCalledTimes(1);
    });
    beforeEach(() => {
        vi.resetAllMocks();
        get.mockImplementation((path: string) => Promise.resolve(path.includes("feed") ? { tasks: [task], summary, date: "2026-10-01", timezone: "UTC" } : { overall_score: 0 }));
    });
    it("does not mark complete before the API confirms, and blocks duplicate clicks", async () => {
        let resolve!: () => void;
        post.mockReturnValue(new Promise<void>((done) => { resolve = done; }));
        const { result, store } = setup();
        await waitFor(() => expect(result.current.tasks).toHaveLength(1));
        let pending!: Promise<boolean>;
        act(() => { pending = result.current.markComplete(task); });
        expect(store.getState().feed.tasks[0].status).toBe(FeedTaskStatus.PENDING);
        await act(async () => { expect(await result.current.markComplete(task)).toBe(false); });
        expect(post).toHaveBeenCalledTimes(1);
        get.mockImplementation((path: string) => Promise.resolve(path.includes("feed") ? { tasks: [{ ...task, status: "completed" }], summary: { ...summary, completed: 1 }, date: "2026-10-01", timezone: "UTC" } : { overall_score: 1 }));
        await act(async () => { resolve(); expect(await pending).toBe(true); });
        await waitFor(() => expect(result.current.tasks[0].status).toBe("completed"));
        expect(post).toHaveBeenCalledWith("/api/v1/adherence/", expect.objectContaining({ status: "completed", target_id: task.targetId }), { token: "synthetic-token" });
    });
    it("keeps a failed barrier pending and shows an actionable error", async () => {
        post.mockRejectedValue(new Error("offline"));
        const { result } = setup();
        await waitFor(() => expect(result.current.tasks).toHaveLength(1));
        await act(async () => { expect(await result.current.reportBarrier(task, "other", "test barrier")).toBe(false); });
        expect(result.current.tasks[0].status).toBe(FeedTaskStatus.PENDING);
        expect(result.current.actionError).toMatch(/couldn’t confirm/);
        expect(result.current.submitting).toBe(false);
    });
    it.each(["side_effects", "cost", "access", "schedule", "confusion", "other"] as const)("sends the %s barrier without dropping its note", async (code) => {
        post.mockResolvedValue({});
        const { result } = setup();
        await act(async () => { expect(await result.current.reportBarrier(task, code, " synthetic QA ")).toBe(true); });
        expect(post).toHaveBeenCalledWith("/api/v1/adherence/", expect.objectContaining({ status: "skipped", barrier_code: code, notes: "synthetic QA" }), { token: "synthetic-token" });
    });
    it("never acknowledges a response without a session", async () => {
        const { result } = setup(false);
        await act(async () => { expect(await result.current.markComplete(task)).toBe(false); });
        expect(post).not.toHaveBeenCalled();
        expect(result.current.actionError).toMatch(/sign in again/);
    });
});
