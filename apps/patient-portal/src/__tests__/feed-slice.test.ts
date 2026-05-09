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
            description: "Take with Food",
            provider: { clinicName: "Document extraction demo" },
            requiresScheduleConfiguration: true,
            targetId: "med-1",
        });
    });
});
