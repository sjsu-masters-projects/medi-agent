import { configureStore } from "@reduxjs/toolkit";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ADRFollowUpPanel } from "@/components/features/adr-follow-up-panel";
import { authSlice, hydrateSession } from "@/store/slices/auth-slice";

const { fetchRequests, respond } = vi.hoisted(() => ({
    fetchRequests: vi.fn(),
    respond: vi.fn(),
}));

vi.mock("@/services/adr-follow-up", () => ({
    fetchADRInformationRequests: fetchRequests,
    respondToADRInformationRequest: respond,
}));

function renderPanel() {
    const testStore = configureStore({ reducer: { auth: authSlice.reducer } });
    testStore.dispatch(
        hydrateSession({
            accessToken: "access-token",
            expiresAt: 9999999999,
            refreshToken: "refresh-token",
            user: {
                email: "maya@example.test",
                id: "patient-1",
                role: "patient",
            },
        }),
    );
    return render(
        <Provider store={testStore}>
            <ADRFollowUpPanel />
        </Provider>,
    );
}

describe("ADR follow-up panel", () => {
    beforeEach(() => {
        fetchRequests.mockReset();
        respond.mockReset();
    });

    it("collects, confirms, and submits only retrospective patient evidence", async () => {
        fetchRequests.mockResolvedValue([
            {
                id: "request-1",
                assessmentId: "assessment-1",
                symptom: "dizziness",
                symptomSeverity: 4,
                suspectMedicationName: "lisinopril",
                requestedInformation: ["dose_response", "similar_previous_reaction"],
                patientMessage: "Please describe what already happened.",
                createdAt: "2026-10-06T10:00:00Z",
            },
        ]);
        respond.mockResolvedValue({
            request_id: "request-1",
            adr_assessment_id: "assessment-1",
            status: "answered",
            naranjo_score: 4,
            causality: "Possible",
            responded_at: "2026-10-06T10:05:00Z",
        });

        renderPanel();

        expect(await screen.findByText(/A few questions about dizziness/i)).toBeInTheDocument();
        expect(screen.getByText(/Do not restart, stop, or change/i)).toBeInTheDocument();
        expect(screen.queryByText(/placebo/i)).not.toBeInTheDocument();
        expect(screen.queryByText(/objective evidence/i)).not.toBeInTheDocument();

        const fieldsets = screen.getAllByRole("group");
        fireEvent.click(within(fieldsets[0]).getByLabelText("Yes"));
        fireEvent.change(within(fieldsets[0]).getByRole("textbox"), {
            target: { value: "It improved after my clinician lowered the dose." },
        });
        fireEvent.click(within(fieldsets[1]).getByLabelText("I’m not sure"));

        fireEvent.click(screen.getByRole("button", { name: "Review answers" }));
        fireEvent.click(screen.getByRole("checkbox"));
        fireEvent.click(screen.getByRole("button", { name: "Send to care team" }));

        await waitFor(() =>
            expect(respond).toHaveBeenCalledWith("access-token", "request-1", [
                {
                    question: "dose_response",
                    answer: "yes",
                    evidence: "It improved after my clinician lowered the dose.",
                },
                {
                    question: "similar_previous_reaction",
                    answer: "do_not_know",
                    evidence: undefined,
                },
            ]),
        );
        expect(await screen.findByText(/answers were sent to your care team/i)).toBeInTheDocument();
    });

    it("keeps the response visible and retryable when submission fails", async () => {
        fetchRequests.mockResolvedValue([
            {
                id: "request-1",
                assessmentId: "assessment-1",
                symptom: "dizziness",
                symptomSeverity: 4,
                suspectMedicationName: "lisinopril",
                requestedInformation: ["dose_response"],
                patientMessage: "Please describe what already happened.",
                createdAt: "2026-10-06T10:00:00Z",
            },
        ]);
        respond.mockRejectedValue(new Error("The response could not be saved."));

        renderPanel();

        const fieldset = await screen.findByRole("group");
        fireEvent.click(within(fieldset).getByLabelText("I’m not sure"));
        fireEvent.click(screen.getByRole("button", { name: "Review answers" }));
        fireEvent.click(screen.getByRole("checkbox"));
        fireEvent.click(screen.getByRole("button", { name: "Send to care team" }));

        expect(await screen.findByRole("alert")).toHaveTextContent(
            "The response could not be saved.",
        );
        expect(screen.getByRole("button", { name: "Send to care team" })).toBeEnabled();
    });
});
