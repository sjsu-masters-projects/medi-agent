import { configureStore } from "@reduxjs/toolkit";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { feedSlice, fetchTodayFeed } from "@/store/slices/feed-slice";
import { FeedTaskStatus, FeedTaskType } from "@/types";

const { get } = vi.hoisted(() => ({
    get: vi.fn(),
}));

vi.mock("@/services/api", () => ({
    api: { get },
}));

describe("feedSlice", () => {
    it("keeps the latest locale when an older feed response finishes last", async () => {
        const response = (name: string) => ({
            date: "2026-10-19", timezone: "America/Los_Angeles",
            summary: { completed: 1, missed: 0, pending: 0, skipped: 0, total: 1 },
            tasks: [{ id: "same-task", target_id: "same-activity", type: FeedTaskType.OBLIGATION,
                name, frequency: "daily", status: FeedTaskStatus.COMPLETED,
                scheduled_time: "08:00", completed_at: "2026-10-19T15:00:00Z" }],
        });
        let finishEnglish!: (value: ReturnType<typeof response>) => void;
        get.mockReturnValueOnce(new Promise((resolve) => { finishEnglish = resolve; }));
        get.mockResolvedValueOnce(response("Revisa tu glucosa"));
        const store = configureStore({ reducer: feedSlice.reducer });
        const oldRequest = store.dispatch(fetchTodayFeed({ token: "token", locale: "en-US" }));
        await store.dispatch(fetchTodayFeed({ token: "token", locale: "es-MX" }));
        finishEnglish(response("Check your glucose"));
        await oldRequest;
        expect(store.getState()).toMatchObject({ locale: "es-MX", loading: false,
            summary: { completed: 1 }, tasks: [{ name: "Revisa tu glucosa", targetId: "same-activity",
                status: FeedTaskStatus.COMPLETED, scheduledTime: "08:00", completedAt: "2026-10-19T15:00:00Z" }] });
    });

    it("ignores an old failed request after the current locale succeeds", async () => {
        let failOld!: (reason: Error) => void;
        get.mockReturnValueOnce(new Promise((_, reject) => { failOld = reject; }));
        get.mockResolvedValueOnce({ date: "2026-10-19", timezone: "UTC", tasks: [], summary: {} });
        const store = configureStore({ reducer: feedSlice.reducer });
        const oldRequest = store.dispatch(fetchTodayFeed({ locale: "en-US" }));
        await store.dispatch(fetchTodayFeed({ locale: "es-MX" }));
        failOld(new Error("old request failed"));
        await oldRequest;
        expect(store.getState()).toMatchObject({ locale: "es-MX", error: null, loading: false });
    });

    it("stores a stable load key rather than backend prose", async () => {
        get.mockRejectedValue(new Error("Internal English server detail"));
        const store = configureStore({ reducer: feedSlice.reducer });
        await store.dispatch(fetchTodayFeed({ token: "synthetic-token", locale: "es-MX" }));
        expect(store.getState().error).toBe("load");
    });
    beforeEach(() => {
        get.mockReset();
    });

    it("maps real feed API snake_case fields into patient portal task fields", async () => {
        get.mockResolvedValue({
            date: "2026-05-08",
            summary: {
                completed: 0,
                missed: 0,
                pending: 1,
                skipped: 0,
                total: 1,
            },
            tasks: [
                {
                    care_plan: {
                        category: "monitoring",
                        effective_end_date: null,
                        effective_start_date: "2026-05-01",
                        version_number: 2,
                    },
                    completed_at: null,
                    description: "Take with Food",
                    frequency: "twice daily",
                    id: "medication:med-1:unscheduled",
                    name: "Theophylline 200mg",
                    provider: {
                        clinic_name: "Document extraction demo",
                        id: "provider-1",
                        name: "Dr Adam Careful",
                        specialty: "Discharge",
                    },
                    requires_schedule_configuration: true,
                    scheduled_at: null,
                    scheduled_time: null,
                    status: FeedTaskStatus.PENDING,
                    target_id: "med-1",
                    type: FeedTaskType.MEDICATION,
                },
            ],
            timezone: "America/Los_Angeles",
        });
        const store = configureStore({ reducer: feedSlice.reducer });

        await store.dispatch(fetchTodayFeed({ token: "token" }));

        expect(get).toHaveBeenCalledWith("/api/v1/feed/today", { token: "token" });
        expect(store.getState().tasks[0]).toMatchObject({
            carePlan: {
                category: "monitoring",
                effectiveStartDate: "2026-05-01",
                versionNumber: 2,
            },
            description: "Take with Food",
            provider: { clinicName: "Document extraction demo" },
            requiresScheduleConfiguration: true,
            targetId: "med-1",
        });
    });
});
