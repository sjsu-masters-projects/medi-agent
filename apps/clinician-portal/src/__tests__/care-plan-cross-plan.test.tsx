import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CarePlanPanel } from "@/components/features/care-plan-panel";
import { ApiClientError } from "@/services/api";
import { fetchCrossPlanReview, resolveConflict } from "@/services/care-team-plans";
import {
    approveClinicianCarePlan,
    fetchClinicianCarePlanGeneration,
    fetchClinicianCarePlanReviewContext,
    retryClinicianCarePlanGeneration,
} from "@/services/clinicians";
import type { CrossPlanConflict, CrossPlanReview } from "@/types";

vi.mock("@/services/clinicians", () => ({
    approveClinicianCarePlan: vi.fn(),
    fetchBackTranslation: vi.fn(),
    fetchClinicianCarePlanReviewContext: vi.fn(),
    fetchClinicianCarePlanGeneration: vi.fn(),
    fetchClinicianDocumentSource: vi.fn(),
    retryClinicianCarePlanGeneration: vi.fn(),
    translateClinicianCarePlanItem: vi.fn(),
    updateClinicianCarePlan: vi.fn(),
}));
vi.mock("@/services/care-team-plans", async (importOriginal) => ({
    ...(await importOriginal<typeof import("@/services/care-team-plans")>()),
    fetchCrossPlanReview: vi.fn(),
    resolveConflict: vi.fn(),
}));

const verified = (title: string, instructions: string, frequency: string) => ({
    title, instructions, frequency, source_locale: "en-US" as const,
    wording: { "en-US": { title, instructions, frequency }, "es-MX": { title: `${title} (es)`, instructions: `${instructions} (es)`, frequency: `${frequency} (es)` } },
    wording_origin: { "en-US": "source" as const, "es-MX": "ai_draft" as const },
    wording_verified: true,
});
const plan = (extra: object = {}) => ({
    id: "v2", patient_id: "p", version_number: 2, status: "draft" as const, items: [{
        id: "item-ibu", source_fact_id: "fact-1", category: "movement", schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false,
        ...verified("Ibuprofen 200 mg", "Take one tablet with food", "twice daily"), ...extra,
    }],
});
const conflict = (extra: Partial<CrossPlanConflict> = {}): CrossPlanConflict => ({
    fingerprint: "fp-1", kind: "duplicate_medication", severity: "blocker", identity_basis: "recorded_ingredient", draft_item_id: "item-ibu",
    ours: { name: "Ibuprofen", dosage: "200 mg", frequency: "twice daily", route: "oral", instructions: "Take one tablet with food" },
    theirs: { name: "Ibuprofen", dosage: "400 mg", frequency: "three times daily", route: "oral", instructions: "Take with meals" },
    other_plan: { care_plan_id: "plan-ortho", ownership_state: "owned", specialty: "Orthopaedics", clinician_name: "Dr. Lee", clinic_name: "Willow Terrace", approved_at: "2026-10-12T17:00:00Z" },
    shared_list_entry_id: "med-1", acknowledged: false, acknowledged_reason: null, asked_other_team: false, ...extra,
});
const review = (...conflicts: CrossPlanConflict[]): CrossPlanReview => ({ interaction_coverage: "not_checked", conflicts });

function setup(initial: CrossPlanReview, planExtra: object = {}) {
    vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: plan(planExtra), active: null, patient_locale: "en-US", active_medications: [] });
    vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue(null);
    vi.mocked(fetchCrossPlanReview).mockResolvedValue(initial);
}
async function renderPanel(scope?: { careTeamId?: string; carePlanId?: string }) {
    render(<CarePlanPanel patientId="p" scope={scope} />);
    const approve = await screen.findByRole("button", { name: "Approve and publish plan" });
    fireEvent.change(screen.getByPlaceholderText("Record the basis for your approval."), { target: { value: "Reviewed against sources" } });
    return approve;
}

describe("cross-plan conflicts in the care-plan draft review", () => {
    beforeEach(() => { vi.resetAllMocks(); });

    it("shows no conflict chrome when there is nothing to resolve, but never implies interactions were checked", async () => {
        setup(review());
        const approve = await renderPanel();
        await screen.findAllByText(/Interaction severity is not checked/);
        expect(approve).toBeEnabled();
        expect(screen.queryByText(/Conflicts with another care team/)).not.toBeInTheDocument();
        expect(screen.queryByTestId("conflict-summary")).not.toBeInTheDocument();
    });

    it("blocks approval with a red conflict card, a summary and a publish-without alternative", async () => {
        setup(review(conflict()));
        const approve = await renderPanel();
        const card = await screen.findByRole("region", { name: "Conflict with another care team's plan" });
        expect(card).toHaveClass("border-risk");
        expect(card).toHaveTextContent("Conflicts with another care team's plan");
        expect(card).toHaveTextContent("Duplicate medicine");
        expect(approve).toBeDisabled();
        expect(screen.getByTestId("conflict-summary")).toHaveTextContent("1 conflict to resolve");
        expect(screen.getByRole("button", { name: "Publish without these items" })).toBeEnabled();
    });

    it("compares this draft with the other care team's instruction, naming plan, clinician, clinic and date", async () => {
        setup(review(conflict()));
        await renderPanel();
        const card = await screen.findByRole("region", { name: "Conflict with another care team's plan" });
        const thisDraft = within(card).getByRole("region", { name: "This draft" });
        expect(thisDraft).toHaveTextContent("200 mg · twice daily · oral");
        const theirs = within(card).getByRole("region", { name: /Orthopaedics · Dr\. Lee · Willow Terrace · approved Oct 12/ });
        expect(theirs).toHaveTextContent("400 mg · three times daily · oral");
        expect(card).toHaveTextContent("the shared medication list");
        expect(screen.getAllByTestId("interaction-coverage")[0]).toHaveTextContent("Interaction severity is not checked");
    });

    it("explains each kind in words", async () => {
        setup(review(conflict({ kind: "stop_continue" })));
        await renderPanel();
        expect((await screen.findAllByText(/Stop vs continue/)).length).toBeGreaterThan(0);
    });

    it("lets the card collapse and expand", async () => {
        setup(review(conflict()));
        await renderPanel();
        const toggle = await screen.findByRole("button", { name: /Conflicts with another care team/ });
        expect(toggle).toHaveAttribute("aria-expanded", "true");
        fireEvent.click(toggle);
        expect(toggle).toHaveAttribute("aria-expanded", "false");
        expect(screen.queryByRole("region", { name: "This draft" })).not.toBeInTheDocument();
    });

    it("requires a reason of at least 10 characters to keep both, with a counter, then records it and unblocks", async () => {
        setup(review(conflict()));
        vi.mocked(resolveConflict).mockResolvedValue({ fingerprint: "fp-1", resolution: "keep_both", replayed: false });
        const approve = await renderPanel();
        fireEvent.click(await screen.findByRole("radio", { name: /Keep both, with a reason/ }));
        const submit = screen.getByRole("button", { name: "Keep both" });
        expect(submit).toBeDisabled();
        const reason = screen.getByRole("textbox", { name: /Reason for keeping both/ });
        fireEvent.change(reason, { target: { value: "too short" } });
        expect(screen.getByText(/9\/2000 · at least 10 characters/)).toBeInTheDocument();
        expect(submit).toBeDisabled();
        fireEvent.change(reason, { target: { value: "Both prescribers agreed on this combination." } });
        expect(submit).toBeEnabled();
        vi.mocked(fetchCrossPlanReview).mockResolvedValue(review(conflict({ acknowledged: true, acknowledged_reason: "Both prescribers agreed on this combination." })));
        fireEvent.click(submit);
        await waitFor(() => expect(resolveConflict).toHaveBeenCalledWith("p", "v2", "fp-1", { resolution: "keep_both", reason: "Both prescribers agreed on this combination." }));
        await waitFor(() => expect(approve).toBeEnabled());
        expect(screen.getByText(/Kept both\. Your reason is recorded\./)).toBeInTheDocument();
        expect(screen.queryByTestId("conflict-summary")).not.toBeInTheDocument();
    });

    it("asks the other care team and shows a waiting state that still blocks publication", async () => {
        setup(review(conflict()));
        vi.mocked(resolveConflict).mockResolvedValue({ fingerprint: "fp-1", resolution: "ask_other_team", replayed: false });
        const approve = await renderPanel();
        fireEvent.click(await screen.findByRole("radio", { name: /Ask the other care team/ }));
        const message = screen.getByRole("textbox", { name: /Message to the other care team/ });
        fireEvent.change(message, { target: { value: "Can we agree on 200 mg?" } });
        vi.mocked(fetchCrossPlanReview).mockResolvedValue(review(conflict({ asked_other_team: true })));
        fireEvent.click(screen.getByRole("button", { name: "Send to the other care team" }));
        await waitFor(() => expect(resolveConflict).toHaveBeenCalledWith("p", "v2", "fp-1", { resolution: "ask_other_team", reason: "Can we agree on 200 mg?" }));
        expect(await screen.findByTestId("waiting-state")).toHaveTextContent("Waiting for Dr. Lee");
        expect(approve).toBeDisabled();
    });

    it("tells the clinician when the conflict changed under them and refreshes the comparison", async () => {
        setup(review(conflict()));
        vi.mocked(resolveConflict).mockRejectedValue(new ApiClientError("changed", 409, { error: { code: "CONFLICT_CHANGED", message: "changed" } }));
        await renderPanel();
        fireEvent.click(await screen.findByRole("radio", { name: /Keep both, with a reason/ }));
        fireEvent.change(screen.getByRole("textbox", { name: /Reason for keeping both/ }), { target: { value: "Both prescribers agreed on this." } });
        fireEvent.click(screen.getByRole("button", { name: "Keep both" }));
        expect(await screen.findByText(/This conflict changed since you opened it/)).toBeInTheDocument();
        expect(fetchCrossPlanReview).toHaveBeenCalledTimes(2);
    });

    it("flags a reason that no longer applies when the instructions changed after an acknowledgement", async () => {
        setup(review(conflict()));
        vi.mocked(resolveConflict).mockResolvedValue({ fingerprint: "fp-1", resolution: "keep_both", replayed: false });
        await renderPanel();
        fireEvent.click(await screen.findByRole("radio", { name: /Keep both, with a reason/ }));
        fireEvent.change(screen.getByRole("textbox", { name: /Reason for keeping both/ }), { target: { value: "Both prescribers agreed on this." } });
        // After recording, the instructions change: a new fingerprint arrives, not acknowledged.
        vi.mocked(fetchCrossPlanReview).mockResolvedValue(review(conflict({ fingerprint: "fp-2" })));
        fireEvent.click(screen.getByRole("button", { name: "Keep both" }));
        expect(await screen.findByText(/that reason no longer applies/)).toBeInTheDocument();
    });

    it("treats a non-medication overlap as an amber, collapsible warning that never blocks", async () => {
        setup(review(conflict({ fingerprint: "fp-w", kind: "schedule_overlap", severity: "warning", ours: { category: "movement" }, theirs: { category: "movement" } })));
        const approve = await renderPanel();
        const summary = await screen.findByText(/Overlaps with other care teams' activities \(1\)/);
        expect(summary.closest("details")).toHaveClass("border-warn-line");
        expect(summary.closest("details")).not.toHaveAttribute("open");
        expect(approve).toBeEnabled();
        expect(screen.queryByText(/Conflicts with another care team's plan/)).not.toBeInTheDocument();
    });

    it("publishes without the conflicting items after confirming exactly which are excluded", async () => {
        setup(review(conflict()));
        vi.mocked(approveClinicianCarePlan).mockResolvedValue({ status: "approved", excluded_item_ids: ["item-ibu"], warnings: [], replayed: false });
        await renderPanel();
        fireEvent.click(await screen.findByRole("button", { name: "Publish without these items" }));
        const dialog = await screen.findByRole("dialog", { name: "Publish without these items?" });
        expect(within(dialog).getByRole("list", { name: "Items that will not be published" })).toHaveTextContent("Ibuprofen 200 mg");
        expect(within(dialog).getByRole("list")).toHaveTextContent("Conflicts with Orthopaedics · Dr. Lee · Willow Terrace");
        expect(approveClinicianCarePlan).not.toHaveBeenCalled();
        fireEvent.click(within(dialog).getByRole("button", { name: "Publish without these items" }));
        await waitFor(() => expect(approveClinicianCarePlan).toHaveBeenCalledWith("p", "v2", "Reviewed against sources", { idempotencyKey: expect.any(String), excludedItemIds: ["item-ibu"] }));
        expect(await screen.findByText(/Published without 1 item\. It stays in your next draft as pending\./)).toBeInTheDocument();
    });

    it("refreshes the blockers and says nothing was published on 409 CROSS_PLAN_CONFLICT", async () => {
        setup(review());
        vi.mocked(approveClinicianCarePlan).mockRejectedValue(new ApiClientError("conflict", 409, { error: { code: "CROSS_PLAN_CONFLICT", message: "c", details: { conflicts: [conflict()], interaction_coverage: "not_checked" } } }));
        const approve = await renderPanel();
        await waitFor(() => expect(approve).toBeEnabled());
        vi.mocked(fetchCrossPlanReview).mockResolvedValue(review(conflict()));
        fireEvent.click(approve);
        expect(await screen.findByText(/Nothing was published\. A conflict with another care team's plan needs your attention/)).toBeInTheDocument();
        await waitFor(() => expect(screen.getByTestId("conflict-summary")).toHaveTextContent("1 conflict to resolve"));
        expect(approve).toBeDisabled();
    });

    it("reports a reused idempotency key without claiming anything was published", async () => {
        setup(review());
        vi.mocked(approveClinicianCarePlan).mockRejectedValue(new ApiClientError("reused", 409, { error: { code: "IDEMPOTENCY_KEY_REUSED", message: "reused" } }));
        const approve = await renderPanel();
        await waitFor(() => expect(approve).toBeEnabled());
        fireEvent.click(approve);
        expect(await screen.findByText(/This publish attempt was already used for different content/)).toBeInTheDocument();
    });

    it("uses one idempotency key for an attempt and reuses it on retry after an unknown outcome", async () => {
        setup(review());
        vi.mocked(approveClinicianCarePlan).mockRejectedValueOnce(new Error("Network lost")).mockResolvedValue({ status: "approved", replayed: true });
        const approve = await renderPanel();
        await waitFor(() => expect(approve).toBeEnabled());
        fireEvent.click(approve);
        await screen.findByText("Network lost");
        fireEvent.click(approve);
        await waitFor(() => expect(approveClinicianCarePlan).toHaveBeenCalledTimes(2));
        const first = vi.mocked(approveClinicianCarePlan).mock.calls[0][3]?.idempotencyKey;
        const second = vi.mocked(approveClinicianCarePlan).mock.calls[1][3]?.idempotencyKey;
        expect(first).toBeTruthy();
        expect(second).toBe(first);
        expect(await screen.findByText(/nothing was published twice/)).toBeInTheDocument();
    });

    it("starts a new idempotency key after the server definitively refuses an attempt", async () => {
        setup(review());
        vi.mocked(approveClinicianCarePlan).mockRejectedValueOnce(new ApiClientError("bad", 422, { error: { code: "VALIDATION_ERROR", message: "bad" } })).mockResolvedValue({ status: "approved" });
        const approve = await renderPanel();
        await waitFor(() => expect(approve).toBeEnabled());
        fireEvent.click(approve);
        await screen.findByText("bad");
        fireEvent.click(approve);
        await waitFor(() => expect(approveClinicianCarePlan).toHaveBeenCalledTimes(2));
        expect(vi.mocked(approveClinicianCarePlan).mock.calls[1][3]?.idempotencyKey).not.toBe(vi.mocked(approveClinicianCarePlan).mock.calls[0][3]?.idempotencyKey);
    });

    it("says the cross-plan check could not load, offers a retry, and leaves the final check to the server", async () => {
        setup(review());
        vi.mocked(fetchCrossPlanReview).mockRejectedValueOnce(new Error("offline"));
        const approve = await renderPanel();
        expect(await screen.findByText(/The cross-plan check could not be loaded/)).toBeInTheDocument();
        expect(approve).toBeEnabled();
        vi.mocked(fetchCrossPlanReview).mockResolvedValue(review());
        fireEvent.click(screen.getByRole("button", { name: "Retry cross-plan check" }));
        await waitFor(() => expect(screen.queryByText(/The cross-plan check could not be loaded/)).not.toBeInTheDocument());
    });

    it("reviews the plan of the chosen care team", async () => {
        setup(review());
        await renderPanel({ careTeamId: "team-1", carePlanId: "plan-1" });
        expect(fetchClinicianCarePlanReviewContext).toHaveBeenCalledWith("p", { careTeamId: "team-1", carePlanId: "plan-1" });
        expect(fetchClinicianCarePlanGeneration).toHaveBeenCalledWith("p", { careTeamId: "team-1", carePlanId: "plan-1" });
        expect(retryClinicianCarePlanGeneration).not.toHaveBeenCalled();
    });
});
