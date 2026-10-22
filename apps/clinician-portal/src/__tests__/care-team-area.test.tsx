import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CarePlanArea } from "@/components/features/care-plan-area";
import { CareTeamSelect, useCareTeamChoice } from "@/components/features/care-team-select";
import { OtherCareTeams, SharedAllergiesCard, SharedConditionsCard, sharedSummaryApplies } from "@/components/features/shared-clinical-summary";
import * as plans from "@/services/care-team-plans";
import { clinicFilterState, resetClinicFilter } from "@/test/clinic-filter-mock";
import type { ClinicianPlanListEntry, SharedClinicalSummary } from "@/types";

vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("@/components/features/care-plan-panel", () => ({
    CarePlanPanel: ({ scope }: { scope?: { carePlanId?: string } }) => <p data-testid="panel">Panel {scope?.carePlanId ?? "unscoped"}</p>,
}));
vi.mock("@/services/care-team-plans", async (original) => ({
    ...(await original<typeof import("@/services/care-team-plans")>()),
    fetchPatientPlans: vi.fn(), fetchReviewItems: vi.fn(), fetchSharedSummary: vi.fn(), fetchCareTeamOptions: vi.fn(),
}));

const plan = (extra: Partial<ClinicianPlanListEntry>): ClinicianPlanListEntry => ({
    care_plan_id: "plan-a", care_team_id: "team-a", ownership_state: "owned", origin: "native", is_mine: true, approved_at: "2026-10-12T17:00:00Z", unowned_since: null,
    owner: { specialty: "Cardiology", clinician_name: "Dr. Park", clinic_id: "c1", clinic_name: "Cedar Grove" }, latest_version_number: 3, active_version_id: "v3", draft_version_id: null, ...extra,
});
const other = plan({ care_plan_id: "plan-b", care_team_id: "team-b", is_mine: false, active_version_id: undefined, draft_version_id: undefined, owner: { specialty: "Orthopaedics", clinician_name: "Dr. Lee", clinic_id: "c2", clinic_name: "Willow Terrace" } });
const summary = (extra: Partial<SharedClinicalSummary> = {}): SharedClinicalSummary => ({
    medications: [{ id: "m1", name: "Ibuprofen", dosage: "200 mg", frequency: "twice daily", route: "oral", instructions: null, recorded_by: { specialty: "Cardiology", clinic_name: "Cedar Grove" }, recorded_by_care_team_id: "team-a" }],
    allergies: [{ id: "al1", allergen: "Penicillin", reaction: null, severity: "severe", recorded_by: { specialty: "Cardiology", clinic_name: "Cedar Grove" }, recorded_by_care_team_id: "team-a" }],
    conditions: [{ id: "c1", name: "Hypertension", icd10_code: null, status: "active", recorded_by: { specialty: "Cardiology", clinic_name: "Cedar Grove" }, recorded_by_care_team_id: "team-a" }],
    some_conditions_private: false,
    care_teams: [{ care_team_id: "team-a", specialty: "Cardiology", clinician_name: "Dr. Park", clinic_name: "Cedar Grove", is_mine: true, plan: null },
        { care_team_id: "team-b", specialty: "Orthopaedics", clinician_name: "Dr. Lee", clinic_name: "Willow Terrace", is_mine: false, plan: { care_plan_id: "plan-b", ownership_state: "owned", approved_at: "2026-10-12T17:00:00Z" } }],
    ...extra,
});

describe("CarePlanArea", () => {
    beforeEach(() => { cleanup(); resetClinicFilter(); vi.resetAllMocks(); vi.mocked(plans.fetchReviewItems).mockResolvedValue({ items: [], clinic_items: [] }); });

    it("adds nothing for a patient with one plan of one care team", async () => {
        vi.mocked(plans.fetchPatientPlans).mockResolvedValue({ plans: [plan({})] });
        render(<CarePlanArea patientId="p1" />);
        expect(await screen.findByTestId("panel")).toHaveTextContent("unscoped");
        expect(screen.queryByRole("heading", { name: "Care plans" })).not.toBeInTheDocument();
    });

    it("falls back to the plain draft review when the plan list cannot load", async () => {
        vi.mocked(plans.fetchPatientPlans).mockRejectedValue(new Error("down"));
        render(<CarePlanArea patientId="p1" />);
        expect(await screen.findByTestId("panel")).toHaveTextContent("unscoped");
    });

    it("shows my plan as a card and other teams as compact read-only rows with no item detail", async () => {
        vi.mocked(plans.fetchPatientPlans).mockResolvedValue({ plans: [plan({ draft_version_id: "d1" }), other] });
        vi.mocked(plans.fetchSharedSummary).mockResolvedValue(summary());
        render(<CarePlanArea patientId="p1" />);
        const mine = await screen.findByRole("list", { name: "Your care plans" });
        expect(mine).toHaveTextContent("Cardiology · Dr. Park");
        expect(mine).toHaveTextContent("Draft");
        expect(mine).toHaveTextContent("Approved plan live · Oct 12");
        const rows = screen.getByRole("list", { name: "Other care teams' plans" });
        expect(rows).toHaveTextContent("Orthopaedics · Dr. Lee · Willow Terrace · approved Oct 12 · Medications shared below");
        expect(within(rows).queryByRole("button")).not.toBeInTheDocument();
        expect(await screen.findByText("Shared medication list")).toBeInTheDocument();
        expect(screen.getByText("Recorded by Cardiology · Cedar Grove")).toBeInTheDocument();
        expect(screen.getByTestId("panel")).toHaveTextContent("unscoped");
    });

    it("shows the clinic chip on my cards only for a multi-clinic clinician", async () => {
        clinicFilterState.clinics = [{ clinic_id: "c1", clinic_name: "Cedar Grove", role: "provider", status: "active", clinic_code: null }, { clinic_id: "c2", clinic_name: "Willow Terrace", role: "provider", status: "active", clinic_code: null }] as never;
        vi.mocked(plans.fetchPatientPlans).mockResolvedValue({ plans: [plan({}), other] });
        vi.mocked(plans.fetchSharedSummary).mockResolvedValue(summary());
        render(<CarePlanArea patientId="p1" />);
        const mine = await screen.findByRole("list", { name: "Your care plans" });
        expect(within(mine).getByTitle("Cedar Grove")).toBeInTheDocument();
    });

    it("lets a clinician with two plans choose which draft to review, scoping the panel", async () => {
        const second = plan({ care_plan_id: "plan-c", care_team_id: "team-c", owner: { specialty: "Primary care", clinician_name: "Dr. Park", clinic_id: "c2", clinic_name: "Willow Terrace" }, draft_version_id: "d2" });
        vi.mocked(plans.fetchPatientPlans).mockResolvedValue({ plans: [plan({}), second] });
        render(<CarePlanArea patientId="p1" />);
        expect(await screen.findByTestId("panel")).toHaveTextContent("Panel plan-c");
        fireEvent.click(screen.getByRole("button", { name: "Open plan" }));
        await waitFor(() => expect(screen.getByTestId("panel")).toHaveTextContent("Panel plan-a"));
    });

    it("shows a review badge and the patient's review items; a missing deep-linked item is explained", async () => {
        vi.mocked(plans.fetchPatientPlans).mockResolvedValue({ plans: [plan({})] });
        vi.mocked(plans.fetchReviewItems).mockResolvedValue({ items: [{ id: "r1", patient_id: "p1", care_plan_id: "plan-b", kind: "conflict_acknowledged", target_care_team_id: "team-a", conflict_fingerprint: "f", summary: {}, request_note: "agreed", reply_note: null, status: "open", created_at: "2026-10-20T12:00:00Z", resolved_at: null }, { id: "elsewhere", patient_id: "other-patient", care_plan_id: null, kind: "unowned_plan", target_care_team_id: "t", conflict_fingerprint: null, summary: {}, request_note: null, reply_note: null, status: "open", created_at: "2026-10-20T12:00:00Z", resolved_at: null }], clinic_items: [] });
        render(<CarePlanArea patientId="p1" reviewId="gone" />);
        expect(await screen.findByRole("link", { name: /Care plan review item/ })).toHaveAttribute("href", "#review-items");
        expect(screen.getByText(/That review item is no longer open/)).toBeInTheDocument();
        expect(screen.getAllByRole("listitem", { name: "A care team kept both instructions, with a reason" })).toHaveLength(1);
    });

    it("offers adopt and retire for a plan nobody owns", async () => {
        vi.mocked(plans.fetchPatientPlans).mockResolvedValue({ plans: [plan({}), plan({ care_plan_id: "plan-u", care_team_id: null, ownership_state: "unowned", is_mine: false, adoptable_by_care_team_ids: ["team-a"], approved_at: null })] });
        render(<CarePlanArea patientId="p1" />);
        const adopt = await screen.findByRole("button", { name: "Adopt this plan" });
        const row = adopt.closest("li") as HTMLElement;
        expect(row).toHaveTextContent("Unowned");
        expect(within(row).getByRole("button", { name: "Retire items" })).toBeInTheDocument();
    });
});

describe("shared clinical summary", () => {
    it("applies only to several care teams or private conditions", () => {
        expect(sharedSummaryApplies(null)).toBe(false);
        expect(sharedSummaryApplies(summary({ care_teams: [] }))).toBe(false);
        expect(sharedSummaryApplies(summary({ care_teams: [], some_conditions_private: true }))).toBe(true);
        expect(sharedSummaryApplies(summary())).toBe(true);
    });

    it("captions conditions and allergies and shows a neutral private-conditions row with no count", () => {
        const value = summary({ some_conditions_private: true });
        render(<><SharedConditionsCard summary={value} /><SharedAllergiesCard summary={value} /><OtherCareTeams summary={value} /></>);
        expect(screen.getAllByText("Recorded by Cardiology · Cedar Grove")).toHaveLength(2);
        const note = screen.getByTestId("private-conditions-note");
        expect(note).toHaveTextContent("Some conditions are kept private by the patient");
        expect(note.textContent).not.toMatch(/\d/);
        expect(screen.getByRole("heading", { name: "Also cared for by" })).toBeInTheDocument();
        expect(screen.getByText(/Plan approved Oct 12, 2026/)).toBeInTheDocument();
    });

    it("omits the private row when nothing is private", () => {
        render(<SharedConditionsCard summary={summary()} />);
        expect(screen.queryByTestId("private-conditions-note")).not.toBeInTheDocument();
    });
});

function Harness({ patientId }: { patientId: string }) {
    const choice = useCareTeamChoice(patientId);
    return <><CareTeamSelect onChange={choice.setValue} options={choice.options} required={choice.required} value={choice.value} /><p data-testid="state">{choice.missing ? "missing" : "ok"}:{choice.careTeamId ?? "none"}</p></>;
}

describe("care-team select for creating records", () => {
    beforeEach(() => { cleanup(); vi.resetAllMocks(); });
    const option = (id: string, clinic: string) => ({ care_team_id: id, patient_id: "p", clinician_id: "c", clinic_id: id, clinic_name: clinic });

    it("shows nothing and requires nothing with a single link", async () => {
        vi.mocked(plans.fetchCareTeamOptions).mockResolvedValue([option("t1", "Cedar Grove")]);
        render(<Harness patientId="p" />);
        await waitFor(() => expect(plans.fetchCareTeamOptions).toHaveBeenCalled());
        expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
        expect(screen.getByTestId("state")).toHaveTextContent("ok:none");
    });

    it("requires a choice with several links and returns it", async () => {
        vi.mocked(plans.fetchCareTeamOptions).mockResolvedValue([option("t1", "Cedar Grove"), option("t2", "Willow Terrace")]);
        render(<Harness patientId="p" />);
        const select = await screen.findByRole("combobox", { name: /Care team/ });
        expect(select).toBeRequired();
        expect(screen.getByTestId("state")).toHaveTextContent("missing:none");
        fireEvent.change(select, { target: { value: "t2" } });
        expect(screen.getByTestId("state")).toHaveTextContent("ok:t2");
    });

    it("stays out of the way when the options cannot load", async () => {
        vi.mocked(plans.fetchCareTeamOptions).mockRejectedValue(new Error("down"));
        render(<Harness patientId="p" />);
        await waitFor(() => expect(plans.fetchCareTeamOptions).toHaveBeenCalled());
        expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
        expect(screen.getByTestId("state")).toHaveTextContent("ok:none");
    });
});
