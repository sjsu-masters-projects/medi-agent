import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TodayPage from "@/app/(app)/today/page";
import { FeedTaskStatus, FeedTaskType, type CareTeamFilterOption, type FeedTask, type PlanOwner } from "@/types";

const destination = vi.hoisted(() => ({ params: new URLSearchParams() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => destination.params }));
vi.mock("@/components/features/approved-plan-details", () => ({ ApprovedPlanDetails: () => <p>Approved snapshot</p> }));

const { markComplete, useFeedData, usePatientProfile } = vi.hoisted(() => ({
    markComplete: vi.fn(), useFeedData: vi.fn(), usePatientProfile: vi.fn(),
}));
vi.mock("@/hooks/use-feed-data", () => ({ useFeedData }));
vi.mock("@/hooks/use-patient-profile", () => ({ usePatientProfile }));
vi.mock("@/hooks/use-pending-adr-follow-ups", () => ({ usePendingADRFollowUps: () => ({ count: 0, loaded: true }) }));
vi.mock("@/hooks/use-medication-questions", () => ({ useMedicationQuestions: () => ({ items: [], loaded: true, refresh: () => {} }) }));

function owner(overrides: Partial<PlanOwner> = {}): PlanOwner {
    return { care_plan_id: "plan-cardio", care_team_id: "team-cardio", ownership_state: "owned", specialty: "Cardiology", clinician_name: "Dr. Park", clinic_id: "c1", clinic_name: "Cedar Grove", unowned_notice: false, ...overrides };
}
const ortho = owner({ care_plan_id: "plan-ortho", care_team_id: "team-ortho", specialty: "Orthopaedics", clinician_name: "Dr. Lee", clinic_name: "Willow Terrace" });
const gone = owner({ care_plan_id: "plan-ent", care_team_id: null, ownership_state: "unowned", specialty: "ENT", clinician_name: "Dr. Moss", clinic_name: "Birch Lane", unowned_notice: true });

function task(id: string, name: string, planOwner: PlanOwner | null, extra: Partial<FeedTask> = {}): FeedTask {
    return { id, targetId: id, type: FeedTaskType.OBLIGATION, name, status: FeedTaskStatus.PENDING, frequency: "Daily", ...(planOwner ? { planOwner } : {}), ...extra } as FeedTask;
}
function filters(...options: Array<[PlanOwner, number]>): CareTeamFilterOption[] {
    return options.map(([o, count]) => ({ care_team_id: o.care_team_id, ownership_state: o.ownership_state, specialty: o.specialty, clinician_name: o.clinician_name, clinic_name: o.clinic_name, count }));
}
function mockFeed(tasks: FeedTask[], extra: Record<string, unknown> = {}) {
    useFeedData.mockReturnValue({
        adherenceStats: { currentStreakDays: 0, overallScore: 0 }, error: null, loading: false, markComplete,
        reportBarrier: vi.fn(), actionError: null, submitting: false, refreshFeed: vi.fn(),
        summary: { completed: 0, total: tasks.length }, tasks, ...extra,
    });
}

describe("Today with several care teams", () => {
    beforeEach(() => { destination.params = new URLSearchParams(); markComplete.mockReset(); markComplete.mockResolvedValue(false); usePatientProfile.mockReturnValue(null); });
    afterEach(cleanup);

    it("looks exactly as before for a single care team: no owner line, no filter, no clinic card", () => {
        mockFeed([task("a", "Walk 20 minutes", owner()), task("b", "Check glucose", owner())], { careTeamFilters: filters([owner(), 2]) });
        render(<TodayPage />);
        expect(screen.queryByTestId("task-owner")).not.toBeInTheDocument();
        expect(screen.queryByTestId("care-team-filter")).not.toBeInTheDocument();
        expect(screen.queryByText("Contact your clinic")).not.toBeInTheDocument();
    });

    it("names the owner under each title and offers a chip filter when there are two owners", () => {
        mockFeed([task("a", "Walk 20 minutes", owner()), task("b", "Knee exercises", ortho)], { careTeamFilters: filters([owner(), 1], [ortho, 1]) });
        render(<TodayPage />);
        expect(screen.getAllByText("Cardiology · Dr. Park · Cedar Grove").length).toBeGreaterThan(0);
        expect(screen.getAllByText("Orthopaedics · Dr. Lee · Willow Terrace").length).toBeGreaterThan(0);
        const group = screen.getByRole("group", { name: "Filter by care team" });
        expect(group.className).toContain("overflow-x-auto");
        expect(within(group).getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");
        expect(within(group).getAllByRole("button")).toHaveLength(3);
    });

    it("filters the list to one care team and back to All", () => {
        mockFeed([task("a", "Walk 20 minutes", owner(), { scheduledTime: "07:00" }), task("b", "Knee exercises", ortho, { scheduledTime: "09:00" }), task("c", "Foot care", ortho, { scheduledTime: "10:00" })], { careTeamFilters: filters([owner(), 1], [ortho, 2]) });
        render(<TodayPage />);
        const group = screen.getByRole("group", { name: "Filter by care team" });
        fireEvent.click(within(group).getByRole("button", { name: /Orthopaedics · Dr\. Lee/ }));
        expect(screen.queryByText("Walk 20 minutes")).not.toBeInTheDocument();
        expect(screen.getAllByText(/Knee exercises|Foot care/).length).toBeGreaterThan(0);
        expect(within(group).getByRole("button", { name: /Orthopaedics/ })).toHaveAttribute("aria-pressed", "true");
        fireEvent.click(within(group).getByRole("button", { name: "All" }));
        expect(screen.getAllByText("Walk 20 minutes").length).toBeGreaterThan(0);
    });

    it("shows a combined entry once, naming every owner, with one check-off", () => {
        const combined = task("med", "Ibuprofen 200 mg", owner(), { type: FeedTaskType.MEDICATION, planOwners: [owner(), ortho], combinedItemIds: ["med", "med-2"], description: "Take with food." });
        mockFeed([combined, task("x", "Knee exercises", ortho)], { careTeamFilters: filters([owner(), 1], [ortho, 2]) });
        render(<TodayPage />);
        expect(screen.getAllByText("Cardiology · Dr. Park · Cedar Grove and Orthopaedics · Dr. Lee · Willow Terrace").length).toBeGreaterThan(0);
        expect(screen.getAllByText("Ibuprofen 200 mg")).toHaveLength(1);
    });

    it("filtering to either owner keeps the combined entry", () => {
        const combined = task("med", "Ibuprofen 200 mg", owner(), { planOwners: [owner(), ortho] });
        mockFeed([combined, task("x", "Knee exercises", ortho)], { careTeamFilters: filters([owner(), 1], [ortho, 2]) });
        render(<TodayPage />);
        fireEvent.click(within(screen.getByRole("group", { name: "Filter by care team" })).getByRole("button", { name: /Cardiology/ }));
        expect(screen.getAllByText("Ibuprofen 200 mg").length).toBeGreaterThan(0);
        expect(screen.queryByText("Knee exercises")).not.toBeInTheDocument();
    });

    it("marks unowned activities with the care-team-ended caption and a dedicated chip", () => {
        mockFeed([task("a", "Walk 20 minutes", owner()), task("e", "Blood thinner", gone)], { careTeamFilters: filters([owner(), 1], [gone, 1]) });
        render(<TodayPage />);
        expect(screen.getAllByText("Prescribed by Dr. Moss, no longer on your care team. Ask your care team before changing it.").length).toBeGreaterThan(0);
        const chip = within(screen.getByRole("group", { name: "Filter by care team" })).getByRole("button", { name: /No longer on your care team/ });
        fireEvent.click(chip);
        expect(screen.queryByText("Walk 20 minutes")).not.toBeInTheDocument();
        expect(screen.getAllByText("Blood thinner").length).toBeGreaterThan(0);
    });

    it("still shows the caption for an unowned plan when it is the only plan (no filter chrome)", () => {
        mockFeed([task("e", "Blood thinner", gone)], { careTeamFilters: filters([gone, 1]) });
        render(<TodayPage />);
        expect(screen.getAllByText(/no longer on your care team\. Ask your care team before changing it\./).length).toBeGreaterThan(0);
        expect(screen.queryByTestId("care-team-filter")).not.toBeInTheDocument();
    });

    it("tells the patient to contact the clinic when no care team remains", () => {
        mockFeed([task("e", "Blood thinner", gone)], { careTeamFilters: filters([gone, 1]), contactClinic: true });
        render(<TodayPage />);
        const card = screen.getByRole("region", { name: "Contact your clinic" });
        expect(card).toHaveTextContent("Your reminders continue.");
    });

    it("explains an empty filter and can show everything again", () => {
        mockFeed([task("a", "Walk 20 minutes", owner())], { careTeamFilters: filters([owner(), 1], [ortho, 0]) });
        render(<TodayPage />);
        fireEvent.click(within(screen.getByRole("group", { name: "Filter by care team" })).getByRole("button", { name: /Orthopaedics/ }));
        expect(screen.getByText("Nothing for this care team today.")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Show all" }));
        expect(screen.getAllByText("Walk 20 minutes").length).toBeGreaterThan(0);
    });

    it("localizes everything in es-MX (draft wording)", () => {
        usePatientProfile.mockReturnValue({ preferredLanguage: "es-MX", timezone: "America/Los_Angeles" });
        mockFeed([task("a", "Caminar", owner()), task("e", "Anticoagulante", gone)], { careTeamFilters: filters([owner(), 1], [gone, 1]), contactClinic: true });
        render(<TodayPage />);
        expect(screen.getByRole("group", { name: "Filtrar por equipo de atención" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Ya no está en tu equipo de atención/ })).toBeInTheDocument();
        expect(screen.getAllByText(/Recetado por Dr\. Moss, que ya no está en tu equipo de atención/).length).toBeGreaterThan(0);
        expect(screen.getByRole("region", { name: "Comunícate con tu clínica" })).toBeInTheDocument();
    });
});
