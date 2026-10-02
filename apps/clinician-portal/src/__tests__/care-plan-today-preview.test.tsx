import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CarePlanTodayPreviewPanel } from "@/components/features/care-plan-today-preview";
import { CarePlanPanel } from "@/components/features/care-plan-panel";
import {
    fetchCarePlanTodayPreview,
    fetchClinicianCarePlanReviewContext,
    fetchClinicianCarePlanGeneration,
    approveClinicianCarePlan,
    type CarePlanTodayPreview,
} from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({
    fetchCarePlanTodayPreview: vi.fn(),
    fetchClinicianCarePlanReviewContext: vi.fn(),
    fetchClinicianCarePlanGeneration: vi.fn(),
    fetchClinicianDocumentSource: vi.fn(),
    approveClinicianCarePlan: vi.fn(),
    retryClinicianCarePlanGeneration: vi.fn(),
    updateClinicianCarePlan: vi.fn(),
}));

const preview: CarePlanTodayPreview = {
    plan_id: "plan", version_number: 3, generated_at: "2026-10-02T18:00:00Z",
    feed: { date: "2026-10-02", timezone: "America/Los_Angeles", tasks: [
        { id: "one", name: "Walk", description: "Walk 20 minutes", frequency: "daily", status: "completed", scheduled_at: "2026-10-02T15:00:00Z", requires_schedule_configuration: false, care_plan: { version_number: 3, category: "movement" } },
        { id: "two", name: "Legacy medication", description: "Existing instruction", frequency: "daily", status: "pending", scheduled_at: null, requires_schedule_configuration: true, care_plan: null },
    ] },
};

describe("proposed Today preview", () => {
    beforeEach(() => vi.clearAllMocks());

    it("shows existing and proposed activities, patient-local time, and current completion without publishing", async () => {
        vi.mocked(fetchCarePlanTodayPreview).mockResolvedValue(preview);
        render(<CarePlanTodayPreviewPanel patientId="patient" planId="plan" disabled={false} />);
        fireEvent.click(screen.getByRole("button", { name: "Preview Today" }));
        expect(await screen.findByText("Legacy medication")).toBeInTheDocument();
        expect(screen.getByText(/2026-10-02 · America\/Los_Angeles/)).toBeInTheDocument();
        expect(screen.getByText(/completed · 8:00 AM/)).toBeInTheDocument();
        expect(screen.getByText(/Patient reminder time needed/)).toBeInTheDocument();
        expect(fetchCarePlanTodayPreview).toHaveBeenCalledWith("patient", "plan");
        expect(approveClinicianCarePlan).not.toHaveBeenCalled();
    });

    it("does not fetch when review is incomplete", () => {
        render(<CarePlanTodayPreviewPanel patientId="patient" planId="plan" disabled />);
        expect(screen.getByRole("button", { name: "Preview Today" })).toBeDisabled();
        expect(fetchCarePlanTodayPreview).not.toHaveBeenCalled();
    });

    it("shows a recoverable error and discards the previous snapshot when refresh fails", async () => {
        vi.mocked(fetchCarePlanTodayPreview).mockResolvedValueOnce(preview).mockRejectedValueOnce(new Error("Read unavailable"));
        render(<CarePlanTodayPreviewPanel patientId="patient" planId="plan" disabled={false} />);
        fireEvent.click(screen.getByRole("button", { name: "Preview Today" }));
        expect(await screen.findByText("Walk")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Refresh Today preview" }));
        expect(await screen.findByRole("alert")).toHaveTextContent("Read unavailable");
        expect(screen.queryByText("Walk")).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Preview Today" })).toBeEnabled();
    });

    it("explains an empty date without suggesting publication occurred", async () => {
        vi.mocked(fetchCarePlanTodayPreview).mockResolvedValue({ ...preview, feed: { ...preview.feed, tasks: [] } });
        render(<CarePlanTodayPreviewPanel patientId="patient" planId="plan" disabled={false} />);
        fireEvent.click(screen.getByRole("button", { name: "Preview Today" }));
        expect(await screen.findByText(/No activities on this date/)).toBeInTheDocument();
    });

    it("invalidates preview on draft editing, including a pending request", async () => {
        const item = { id: "item", source_fact_id: "fact", category: "movement", title: "Walking", instructions: "Walk 20 minutes", frequency: "daily", schedule: {}, medication: {}, uncertainty: [], conflict: {}, is_removed: false, reviewed_locale: "en-US" };
        vi.mocked(fetchClinicianCarePlanReviewContext).mockResolvedValue({ latest: { id: "plan", patient_id: "patient", version_number: 3, status: "draft", items: [item] }, active: null, patient_locale: "en-US", active_medications: [] });
        vi.mocked(fetchClinicianCarePlanGeneration).mockResolvedValue({ id: "gen", patient_id: "patient", status: "completed", attempts: 1, requested_at: "2026-10-02T18:00:00Z", completed_at: "2026-10-02T18:01:00Z", failure_code: null });
        let resolve!: (value: CarePlanTodayPreview) => void;
        vi.mocked(fetchCarePlanTodayPreview).mockReturnValue(new Promise((done) => { resolve = done; }));
        render(<CarePlanPanel patientId="patient" />);
        fireEvent.click(await screen.findByRole("button", { name: "Preview Today" }));
        fireEvent.change(screen.getByRole("textbox", { name: "Title" }), { target: { value: "Changed walking" } });
        resolve(preview);
        await waitFor(() => expect(screen.getByRole("button", { name: "Preview Today" })).toBeDisabled());
        expect(screen.queryByText("Legacy medication")).not.toBeInTheDocument();
    });
});
