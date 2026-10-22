import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ReviewQueuePage from "@/app/(dashboard)/review-queue/page";
import { ApiClientError } from "@/services/api";
import { claimDocument, fetchCareTeamOptions } from "@/services/care-team-plans";
import { approveDocumentReview, fetchDocumentReviewQueue } from "@/services/clinicians";
import { store } from "@/store/store";
import { resetClinicFilter } from "@/test/clinic-filter-mock";

vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("@/services/clinicians", () => ({ fetchDocumentReviewQueue: vi.fn(), approveDocumentReview: vi.fn(), rejectDocumentReview: vi.fn() }));
vi.mock("@/services/care-team-plans", async (original) => ({ ...(await original<typeof import("@/services/care-team-plans")>()), claimDocument: vi.fn(), fetchCareTeamOptions: vi.fn() }));

const row = (extra: object = {}) => ({
    id: "doc-1", patientId: "patient-1", patientFirstName: "Ana", patientLastName: "Lopez", fileName: "labs.pdf", documentType: "other",
    parseStatus: "completed", createdAt: "2026-10-12T12:00:00Z", uploadedByRole: "patient", reviewStatus: "pending", ...extra,
}) as never;
const unrouted = (ids: string[] = ["team-1"]) => row({ needsClaim: true, claimableCareTeamIds: ids });
const apiError = (code: string, status = 409) => new ApiClientError(code, status, { error: { code, message: code } });

describe("claiming a Not sure upload", () => {
    beforeEach(() => { resetClinicFilter(); vi.resetAllMocks(); });

    it("labels an unrouted upload and offers Claim instead of Approve and Reject", async () => {
        vi.mocked(fetchDocumentReviewQueue).mockResolvedValue([unrouted()]);
        render(<Provider store={store}><ReviewQueuePage /></Provider>);
        expect(await screen.findByText("Patient uploaded · not routed to a care team")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Claim labs.pdf" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    });

    it("keeps a routed upload exactly as before", async () => {
        vi.mocked(fetchDocumentReviewQueue).mockResolvedValue([row()]);
        render(<Provider store={store}><ReviewQueuePage /></Provider>);
        expect(await screen.findByRole("button", { name: "Approve" })).toBeInTheDocument();
        expect(screen.queryByText(/not routed/)).not.toBeInTheDocument();
    });

    it("confirms before claiming, then unlocks review", async () => {
        vi.mocked(fetchDocumentReviewQueue).mockResolvedValue([unrouted()]);
        vi.mocked(claimDocument).mockResolvedValue({ document_id: "doc-1", care_team_id: "team-1", status: "claimed", replayed: false });
        render(<Provider store={store}><ReviewQueuePage /></Provider>);
        fireEvent.click(await screen.findByRole("button", { name: "Claim labs.pdf" }));
        const dialog = await screen.findByRole("dialog", { name: "Claim this document?" });
        expect(dialog).toHaveTextContent("it becomes yours");
        expect(claimDocument).not.toHaveBeenCalled();
        fireEvent.click(within(dialog).getByRole("button", { name: "Claim document" }));
        await waitFor(() => expect(claimDocument).toHaveBeenCalledWith("doc-1", "team-1"));
        expect(await screen.findByText("You claimed this document. You can now review it.")).toBeInTheDocument();
    });

    it("removes the row with a message when another care team claimed it first", async () => {
        vi.mocked(fetchDocumentReviewQueue).mockResolvedValue([unrouted()]);
        vi.mocked(claimDocument).mockRejectedValue(apiError("DOCUMENT_ALREADY_CLAIMED"));
        render(<Provider store={store}><ReviewQueuePage /></Provider>);
        fireEvent.click(await screen.findByRole("button", { name: "Claim labs.pdf" }));
        fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Claim document" }));
        expect(await screen.findByText("Another care team claimed this document first. It was removed from your queue.")).toBeInTheDocument();
        expect(screen.queryByText("labs.pdf")).not.toBeInTheDocument();
    });

    it("asks which care team when several can claim", async () => {
        vi.mocked(fetchDocumentReviewQueue).mockResolvedValue([unrouted(["team-1", "team-2"])]);
        vi.mocked(fetchCareTeamOptions).mockResolvedValue([
            { care_team_id: "team-1", patient_id: "patient-1", clinician_id: "c", clinic_id: "k1", clinic_name: "Cedar Grove" },
            { care_team_id: "team-2", patient_id: "patient-1", clinician_id: "c", clinic_id: "k2", clinic_name: "Willow Terrace" },
        ]);
        vi.mocked(claimDocument).mockResolvedValue({ document_id: "doc-1", care_team_id: "team-2", status: "claimed", replayed: false });
        render(<Provider store={store}><ReviewQueuePage /></Provider>);
        fireEvent.click(await screen.findByRole("button", { name: "Claim labs.pdf" }));
        const dialog = await screen.findByRole("dialog");
        const claim = within(dialog).getByRole("button", { name: "Claim document" });
        await within(dialog).findByRole("option", { name: "Willow Terrace" });
        expect(claim).toBeDisabled();
        fireEvent.change(within(dialog).getByRole("combobox"), { target: { value: "team-2" } });
        fireEvent.click(claim);
        await waitFor(() => expect(claimDocument).toHaveBeenCalledWith("doc-1", "team-2"));
    });

    it("turns DOCUMENT_CLAIM_REQUIRED on approve into the claim state", async () => {
        vi.mocked(fetchDocumentReviewQueue).mockResolvedValue([row()]);
        vi.mocked(approveDocumentReview).mockRejectedValue(apiError("DOCUMENT_CLAIM_REQUIRED", 422));
        render(<Provider store={store}><ReviewQueuePage /></Provider>);
        fireEvent.click(await screen.findByRole("button", { name: "Approve" }));
        expect(await screen.findByText(/not routed to a care team yet/)).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Claim labs.pdf" })).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Approve" })).not.toBeInTheDocument();
    });
});
