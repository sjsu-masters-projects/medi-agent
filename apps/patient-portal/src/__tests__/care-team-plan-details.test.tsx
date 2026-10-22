import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovedPlanDetails } from "@/components/features/approved-plan-details";
import { api } from "@/services/api";

vi.mock("react-redux", () => ({ useSelector: (select: (state: unknown) => unknown) => select({ auth: { user: { id: "p" }, accessToken: "t" } }) }));
vi.mock("@/services/api", () => ({ api: { get: vi.fn() } }));

const base = { specialty: "Cardiology", clinician_name: "Dr. Park", clinic_id: "c1", clinic_name: "Cedar Grove", ownership_state: "owned", unowned_notice: false };
const cardio = { ...base, care_plan_id: "plan-1", care_team_id: "t1" };
const gone = { ...base, care_plan_id: "plan-2", care_team_id: null, specialty: "ENT", clinician_name: "Dr. Moss", ownership_state: "unowned", unowned_notice: true };
const item = (id: string, title: string, plan_owner?: unknown) => ({ id, title, instructions: `${title} instructions`, frequency: "Daily", is_removed: false, ...(plan_owner ? { plan_owner } : {}) });

describe("approved plan details grouped by care team", () => {
    beforeEach(() => vi.resetAllMocks());
    afterEach(cleanup);

    it("keeps the single-plan layout when there is one owning plan", async () => {
        vi.mocked(api.get).mockResolvedValue({ id: "v", status: "approved", version_number: 3, approved_at: "2026-10-10T12:00:00Z", items: [item("a", "Walk", cardio), item("b", "Hydrate", cardio)], plans: [] });
        render(<ApprovedPlanDetails locale="en-US" />);
        await screen.findByText("Walk");
        expect(screen.getByText("Approved care plan, version 3")).toBeInTheDocument();
        expect(screen.queryByRole("region")).not.toBeInTheDocument();
    });

    it("groups items by care team with the owner header and unowned caption", async () => {
        vi.mocked(api.get).mockResolvedValue({ id: "v", status: "approved", version_number: 3, approved_at: "2026-10-10T12:00:00Z",
            items: [item("a", "Walk", cardio), item("b", "Ear drops", gone)],
            plans: [{ ...cardio, plan_version_id: "v1", version_number: 3, approved_at: "2026-10-10T12:00:00Z" }, { ...gone, plan_version_id: "v2", version_number: 1, approved_at: "2026-09-01T12:00:00Z" }] });
        render(<ApprovedPlanDetails locale="en-US" />);
        const cardioGroup = await screen.findByRole("region", { name: "Cardiology · Dr. Park · Cedar Grove" });
        expect(within(cardioGroup).getByText("Walk")).toBeInTheDocument();
        expect(within(cardioGroup).getByText(/Version 3 · approved/)).toBeInTheDocument();
        const entGroup = screen.getByRole("region", { name: "ENT · Dr. Moss · Cedar Grove" });
        expect(within(entGroup).getByText("Ear drops")).toBeInTheDocument();
        expect(within(entGroup).getByText(/no longer on your care team/)).toBeInTheDocument();
    });

    it("never drops an item that lacks an owner: it falls back to the single list", async () => {
        vi.mocked(api.get).mockResolvedValue({ id: "v", status: "approved", version_number: 2, approved_at: "2026-10-10T12:00:00Z", items: [item("a", "Walk", cardio), item("b", "Hydrate", gone), item("c", "Legacy")] });
        render(<ApprovedPlanDetails locale="en-US" />);
        expect(await screen.findByText("Legacy")).toBeInTheDocument();
        expect(screen.getByText("Walk")).toBeInTheDocument();
    });

    it("localizes the group chrome in es-MX", async () => {
        vi.mocked(api.get).mockResolvedValue({ id: "v", status: "approved", version_number: 3, approved_at: "2026-10-10T12:00:00Z", items: [item("a", "Caminar", cardio), item("b", "Gotas", gone)],
            plans: [{ ...cardio, plan_version_id: "v1", version_number: 3, approved_at: "2026-10-10T12:00:00Z" }] });
        render(<ApprovedPlanDetails locale="es-MX" />);
        await screen.findByText("Caminar");
        expect(screen.getByText(/Versión 3 · aprobado el/)).toBeInTheDocument();
        expect(screen.getByText(/que ya no está en tu equipo de atención/)).toBeInTheDocument();
    });
});
