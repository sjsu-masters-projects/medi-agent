import { configureStore } from "@reduxjs/toolkit";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { feedSlice, fetchTodayFeed } from "@/store/slices/feed-slice";

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/services/api", () => ({ api: { get } }));

const ownerA = { care_plan_id: "p1", care_team_id: "t1", ownership_state: "owned", specialty: "Cardiology", clinician_name: "Dr. Park", clinic_id: "c1", clinic_name: "Cedar Grove", unowned_notice: false };
const ownerB = { ...ownerA, care_plan_id: "p2", care_team_id: "t2", specialty: "Orthopaedics", clinician_name: "Dr. Lee" };

describe("feed slice care-team ownership", () => {
    beforeEach(() => get.mockReset());

    it("maps owners, combined ids, filters and the contact-clinic flag", async () => {
        get.mockResolvedValue({
            date: "2026-10-22", timezone: "UTC", summary: { completed: 0, missed: 0, pending: 1, skipped: 0, total: 1 },
            tasks: [{ id: "m1", type: "medication", target_id: "m1", name: "Ibuprofen", frequency: "daily", status: "pending",
                plan_owner: ownerA, plan_owners: [ownerA, ownerB], combined_item_ids: ["m1", "m2"] }],
            care_team_filters: [{ care_team_id: "t1", ownership_state: "owned", specialty: "Cardiology", clinician_name: "Dr. Park", clinic_name: "Cedar Grove", count: 1 }],
            contact_clinic: true,
        });
        const store = configureStore({ reducer: feedSlice.reducer });
        await store.dispatch(fetchTodayFeed({ token: "t", locale: "en-US" }));
        const state = store.getState();
        expect(state.tasks[0]).toMatchObject({ planOwner: ownerA, planOwners: [ownerA, ownerB], combinedItemIds: ["m1", "m2"] });
        expect(state.careTeamFilters).toHaveLength(1);
        expect(state.contactClinic).toBe(true);
    });

    it("keeps an older single-owner response unchanged (no owner fields, no filters)", async () => {
        get.mockResolvedValue({ date: "2026-10-22", timezone: "UTC", summary: {}, tasks: [{ id: "o1", type: "obligation", target_id: "o1", name: "Walk", frequency: "daily", status: "pending" }] });
        const store = configureStore({ reducer: feedSlice.reducer });
        await store.dispatch(fetchTodayFeed({ token: "t", locale: "en-US" }));
        const task = store.getState().tasks[0];
        expect("planOwner" in task).toBe(false);
        expect("planOwners" in task).toBe(false);
        expect(store.getState().careTeamFilters).toEqual([]);
        expect(store.getState().contactClinic).toBe(false);
    });
});
