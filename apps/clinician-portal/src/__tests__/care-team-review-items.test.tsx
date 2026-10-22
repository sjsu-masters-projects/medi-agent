import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CarePlanReviewsPage from "@/app/(dashboard)/care-plan-reviews/page";
import { ApiClientError } from "@/services/api";
import * as plans from "@/services/care-team-plans";
import { fetchDashboard } from "@/services/clinicians";
import { clinicFilterState, resetClinicFilter } from "@/test/clinic-filter-mock";
import type { PlanReviewItem } from "@/types";

const nav = vi.hoisted(() => ({ search: "" }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(nav.search) }));
vi.mock("@/services/clinicians", () => ({ fetchDashboard: vi.fn() }));
vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("@/services/care-team-plans", async (original) => ({
    ...(await original<typeof import("@/services/care-team-plans")>()),
    fetchReviewItems: vi.fn(), replyToReviewItem: vi.fn(), fetchUnownedActivities: vi.fn(), adoptCarePlan: vi.fn(), retireCarePlanItems: vi.fn(), takeRecord: vi.fn(),
}));

const item = (extra: Partial<PlanReviewItem>): PlanReviewItem => ({
    id: "r1", patient_id: "p1", patient_name: "Ana Lopez", clinic_id: "c1", clinic_name: "Cedar Grove", care_plan_id: "plan-1", kind: "cross_plan_conflict", target_care_team_id: "team-1", conflict_fingerprint: "fp",
    summary: { from: { specialty: "Orthopaedics", clinician_name: "Dr. Lee", clinic_name: "Willow Terrace" }, ours: { name: "Ibuprofen", dosage: "400 mg" }, theirs: { name: "Ibuprofen", dosage: "200 mg" } },
    request_note: "Can we agree on one dose?", reply_note: null, status: "open", created_at: "2026-10-20T12:00:00Z", resolved_at: null, ...extra,
});
const err = (code: string, status = 409) => new ApiClientError(code, status, { error: { code, message: code } });
function load(items: PlanReviewItem[], clinic_items: never[] = []) {
    vi.mocked(plans.fetchReviewItems).mockResolvedValue({ items, clinic_items });
}
const activities = { care_plan_id: "plan-1", ownership_state: "unowned" as const, previous_owner: { specialty: "ENT", clinician_name: "Dr. Moss", clinic_id: "c1", clinic_name: "Cedar Grove" }, unowned_since: null, approved_at: null,
    activities: [{ id: "a1", category: "medication", title: "Ear drops", instructions: "Twice daily", frequency: "twice daily", medication: {}, wording: {} }, { id: "a2", category: "movement", title: "Neck stretches", instructions: "", frequency: "daily", medication: {}, wording: {} }] };

describe("care plan review items", () => {
    beforeEach(() => { resetClinicFilter(); vi.resetAllMocks(); nav.search = ""; });

    it("shows a cross-plan ask with both instructions and requires a reply; a reply never claims to clear their block", async () => {
        load([item({})]);
        vi.mocked(plans.replyToReviewItem).mockResolvedValue({ id: "r1", status: "resolved", replayed: false });
        render(<CarePlanReviewsPage />);
        const row = await screen.findByRole("listitem", { name: "Another care team asks about a conflict" });
        expect(row).toHaveTextContent("Ana Lopez");
        // Name and clinic come on the item: the roster is never paged to find them.
        expect(fetchDashboard).not.toHaveBeenCalled();
        expect(within(row).getByRole("region", { name: "Their draft" })).toHaveTextContent("400 mg");
        expect(within(row).getByRole("region", { name: "Your plan" })).toHaveTextContent("200 mg");
        expect(row).toHaveTextContent("From Orthopaedics · Dr. Lee · Willow Terrace");
        const send = within(row).getByRole("button", { name: "Send reply" });
        expect(send).toBeDisabled();
        expect(row).toHaveTextContent("does not release their publication block");
        fireEvent.change(within(row).getByRole("textbox", { name: /Your reply/ }), { target: { value: "200 mg works" } });
        fireEvent.click(send);
        await waitFor(() => expect(plans.replyToReviewItem).toHaveBeenCalledWith("r1", "200 mg works"));
        expect(await screen.findByText(/Reply sent/)).toBeInTheDocument();
        expect(within(row).getByRole("link", { name: "Open care plan" })).toHaveAttribute("href", "/patients/p1?tab=care-plan");
    });

    it("focuses the item named by a notification link", async () => {
        nav.search = "item=r1";
        load([item({})]);
        render(<CarePlanReviewsPage />);
        const row = await screen.findByRole("listitem", { name: "Another care team asks about a conflict" });
        await waitFor(() => expect(row).toHaveFocus());
    });

    it("adopts an unowned plan after a confirmation that says it becomes yours", async () => {
        load([item({ kind: "unowned_plan", summary: {}, request_note: null })]);
        vi.mocked(plans.fetchUnownedActivities).mockResolvedValue(activities);
        vi.mocked(plans.adoptCarePlan).mockResolvedValue({});
        render(<CarePlanReviewsPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Adopt this plan" }));
        const dialog = await screen.findByRole("dialog", { name: "Adopt this care plan?" });
        expect(dialog).toHaveTextContent("it becomes yours");
        await within(dialog).findByText("Ear drops");
        const confirm = within(dialog).getByRole("button", { name: "Adopt this plan" });
        expect(confirm).toBeDisabled();
        fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "I now treat this patient" } });
        fireEvent.click(confirm);
        await waitFor(() => expect(plans.adoptCarePlan).toHaveBeenCalledWith("plan-1", { care_team_id: "team-1", note: "I now treat this patient" }));
        expect(await screen.findByText(/You adopted this plan/)).toBeInTheDocument();
    });

    it("tells the loser of an adoption race that another clinician adopted the plan", async () => {
        load([item({ kind: "unowned_plan", summary: {}, request_note: null })]);
        vi.mocked(plans.fetchUnownedActivities).mockResolvedValue(activities);
        vi.mocked(plans.adoptCarePlan).mockRejectedValue(err("PLAN_ALREADY_ADOPTED"));
        render(<CarePlanReviewsPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Adopt this plan" }));
        const dialog = await screen.findByRole("dialog");
        await within(dialog).findByText("Ear drops");
        fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "note" } });
        fireEvent.click(within(dialog).getByRole("button", { name: "Adopt this plan" }));
        expect(await within(dialog).findByRole("alert")).toHaveTextContent("Another clinician adopted this plan.");
        fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
        expect(await screen.findByText("Another clinician adopted this plan.")).toBeInTheDocument();
    });

    it("retires chosen items with a required reason", async () => {
        load([item({ kind: "unassigned_legacy_plan", summary: {}, request_note: null })]);
        vi.mocked(plans.fetchUnownedActivities).mockResolvedValue(activities);
        vi.mocked(plans.retireCarePlanItems).mockResolvedValue({});
        render(<CarePlanReviewsPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Retire items" }));
        const dialog = await screen.findByRole("dialog", { name: "Retire plan items" });
        await within(dialog).findByText("Neck stretches");
        const retire = within(dialog).getByRole("button", { name: /^Retire/ });
        expect(retire).toBeDisabled();
        fireEvent.click(within(dialog).getByRole("checkbox", { name: /Neck stretches/ }));
        expect(retire).toBeDisabled();
        fireEvent.change(within(dialog).getByRole("textbox"), { target: { value: "No longer needed" } });
        fireEvent.click(retire);
        await waitFor(() => expect(plans.retireCarePlanItems).toHaveBeenCalledWith("plan-1", { care_team_id: "team-1", item_ids: ["a2"], reason: "No longer needed" }));
    });

    it("takes an unowned clinical record and handles losing the race", async () => {
        load([item({ kind: "unowned_clinical_record", summary: { record: "adr_assessment", record_id: "adr-1" }, request_note: null, care_plan_id: null })]);
        vi.mocked(plans.takeRecord).mockRejectedValue(err("RECORD_ALREADY_TAKEN"));
        render(<CarePlanReviewsPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Take this ADR review" }));
        await waitFor(() => expect(plans.takeRecord).toHaveBeenCalledWith("adr_assessment", "adr-1", "team-1"));
        expect(await screen.findByText("Another care team took this record.")).toBeInTheDocument();
    });

    it("lists clinic-admin items without any patient detail", async () => {
        load([], [{ id: "k1", care_plan_id: "plan-9", kind: "unowned_plan", target_clinic_id: "c1", status: "open", created_at: "2026-10-20T12:00:00Z" }] as never);
        render(<CarePlanReviewsPage />);
        const section = await screen.findByRole("region", { name: "Clinic work" });
        expect(section).toHaveTextContent("needs an owner");
        expect(section).not.toHaveTextContent("Ana");
    });

    it("shows an empty state and an error with retry", async () => {
        load([]);
        render(<CarePlanReviewsPage />);
        expect(await screen.findByText("No open care plan review items")).toBeInTheDocument();
    });

    it("shows clinic chips and the clinic filter only for a multi-clinic clinician, and filters by clinic", async () => {
        clinicFilterState.clinics = [{ clinic_id: "c1", clinic_name: "Cedar Grove", role: "provider", status: "active", clinic_code: null }, { clinic_id: "c2", clinic_name: "Willow Terrace", role: "provider", status: "active", clinic_code: null }] as never;
        load([item({})]);
        render(<CarePlanReviewsPage />);
        const row = await screen.findByRole("listitem", { name: "Another care team asks about a conflict" });
        expect(within(row).getByTitle("Cedar Grove")).toBeInTheDocument();
        expect(screen.getByRole("combobox", { name: "Clinic" })).toBeInTheDocument();
    });

    it("shows no clinic chrome for a single-clinic clinician", async () => {
        load([item({})]);
        render(<CarePlanReviewsPage />);
        await screen.findByRole("listitem", { name: "Another care team asks about a conflict" });
        expect(screen.queryByRole("combobox", { name: "Clinic" })).not.toBeInTheDocument();
        expect(screen.queryByTitle("Cedar Grove")).not.toBeInTheDocument();
    });

    it("shows an error with retry when the items cannot load", async () => {
        vi.mocked(plans.fetchReviewItems).mockRejectedValueOnce(new Error("down"));
        render(<CarePlanReviewsPage />);
        expect(await screen.findByRole("alert")).toHaveTextContent("down");
        vi.mocked(plans.fetchReviewItems).mockResolvedValue({ items: [], clinic_items: [] });
        fireEvent.click(screen.getByRole("button", { name: "Retry" }));
        expect(await screen.findByText("No open care plan review items")).toBeInTheDocument();
    });
});
