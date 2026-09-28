import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CarePlanPanel } from "@/components/features/care-plan-panel";
import {
    fetchClinicianCarePlan,
    fetchClinicianCarePlanGeneration,
    retryClinicianCarePlanGeneration,
} from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({
    approveClinicianCarePlan: vi.fn(),
    fetchClinicianCarePlan: vi.fn(),
    fetchClinicianCarePlanGeneration: vi.fn(),
    retryClinicianCarePlanGeneration: vi.fn(),
    updateClinicianCarePlan: vi.fn(),
}));

describe("CarePlanPanel", () => {
    beforeEach(() => {
        vi.mocked(fetchClinicianCarePlan).mockReset();
        vi.mocked(fetchClinicianCarePlanGeneration).mockReset();
        vi.mocked(retryClinicianCarePlanGeneration).mockReset();
    });

    it("shows a failed automatic draft and retries the same evidence", async () => {
        vi.mocked(fetchClinicianCarePlan).mockResolvedValue(null);
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue({
            id: "generation-1",
            patient_id: "patient-1",
            status: "failed",
            attempts: 3,
            requested_at: "2026-09-28T10:00:00Z",
            failure_code: "provider_unavailable",
        });
        vi.mocked(retryClinicianCarePlanGeneration).mockResolvedValue({ status: "pending" });

        render(<CarePlanPanel patientId="patient-1" />);

        expect(await screen.findByText("Automatic evidence draft failed")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Retry generation" }));
        await waitFor(() =>
            expect(retryClinicianCarePlanGeneration).toHaveBeenCalledWith("patient-1"),
        );
    });
});
