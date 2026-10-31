import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PatientTimeline } from "@/components/features/patient-timeline";
import { fetchPatientTimeline, type PatientTimelineResponse } from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({ fetchPatientTimeline: vi.fn() }));

const snapshot: PatientTimelineResponse = {
    patient_id: "synthetic-patient",
    retrieved_at: "2026-10-21T12:00:00Z",
    events: [{
        id: "medication-record", domain: "medication", source_table: "medications", source_id: "synthetic-medication",
        occurred_at: "2026-10-01T12:00:00Z", timestamp_label: "Recorded", title: "Medication recorded",
        details: { name: "Synthetic medication", end_date: null },
        source_href: "/patients/synthetic-patient?tab=timeline#source-medication-record", destination_href: null,
    }, {
        id: "message-record", domain: "message", source_table: "care_conversation_messages", source_id: "synthetic-message",
        occurred_at: "2026-10-02T12:00:00Z", timestamp_label: "Recorded", title: "Private message",
        details: { sender_role: "patient" },
        source_href: "/patients/synthetic-patient?tab=timeline#source-message-record", destination_href: "/messages?conversation=own-thread",
    }],
    sources: [{ source: "medications.created_at", returned: 1, limit: 40, has_more: true, status: "available", omitted_invalid: 0, conversation_limit: null, conversations_truncated: null }],
};

afterEach(() => {
    vi.resetAllMocks();
    window.history.replaceState(null, "", window.location.pathname);
});

describe("PatientTimeline", () => {
    it("preserves recorded names and filenames while expanding status codes", async () => {
        vi.mocked(fetchPatientTimeline).mockResolvedValue({
            ...snapshot,
            events: [
                { ...snapshot.events[0]!, details: { name: "metformin_er", status: "pending_review" } },
                { ...snapshot.events[1]!, details: { file_name: "lab_results.pdf" } },
            ],
        });
        render(<PatientTimeline patientId="synthetic-patient" />);
        await screen.findByRole("heading", { name: "Medication recorded" });
        expect(screen.getAllByText("metformin_er")).toHaveLength(2);
        expect(screen.getAllByText("lab_results.pdf")).toHaveLength(2);
        expect(screen.getByText("Pending review")).toBeInTheDocument();
        expect(screen.queryByText("Metformin er")).not.toBeInTheDocument();
        expect(screen.queryByText("Lab results pdf")).not.toBeInTheDocument();
    });

    it("loads actual source dates and links to exact records and own conversation", async () => {
        vi.mocked(fetchPatientTimeline).mockResolvedValue(snapshot);
        const { container } = render(<PatientTimeline patientId="synthetic-patient" />);
        expect(screen.getByRole("status")).toHaveTextContent("Loading timeline");
        await screen.findByRole("heading", { name: "Medication recorded" });
        expect(screen.getByText(/At most 40 records per source/)).toBeInTheDocument();
        expect(screen.getByText(/not a full audit trail/)).toBeInTheDocument();
        expect(container.querySelector('time[datetime="2026-10-01T12:00:00Z"]')).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /Open your conversation/ })).toHaveAttribute("href", "/messages?conversation=own-thread");
        const link = screen.getByRole("link", { name: /Source record for Medication/ });
        expect(link).toHaveAttribute("href", snapshot.events[0]!.source_href);
        link.addEventListener("click", (event) => event.preventDefault());
        fireEvent.click(link);
        expect(document.getElementById("source-medication-record")).toHaveAttribute("open");
        expect(document.getElementById("source-medication-record")).toHaveFocus();
        fireEvent.click(document.getElementById("source-medication-record")!.querySelector("summary")!);
        expect(document.getElementById("source-medication-record")).not.toHaveAttribute("open");
        fireEvent.click(link);
        expect(document.getElementById("source-medication-record")).toHaveAttribute("open");
        expect(screen.getByText("Not recorded")).toBeInTheDocument();
        expect(screen.getByText("End date")).toBeInTheDocument();
        expect(screen.getByText("Medications", { selector: "span" })).toBeInTheDocument();
        expect(screen.queryByText(/medications\.created_at/)).not.toBeInTheDocument();
        expect(link).not.toHaveAccessibleName(/synthetic-medication/);
        expect(screen.getByText(/More records exist outside this view/)).toBeInTheDocument();
    });

    it("exposes partial read failures and invalid dates without claiming an empty history", async () => {
        vi.mocked(fetchPatientTimeline).mockResolvedValue({ ...snapshot, events: [], sources: [
            { ...snapshot.sources[0]!, status: "unavailable", has_more: null, returned: 0 },
            { ...snapshot.sources[0]!, source: "symptom_reports.created_at", omitted_invalid: 2 },
        ] });
        const { container } = render(<PatientTimeline patientId="synthetic-patient" />);
        await screen.findByText(/source read failed/);
        expect(screen.getByText(/2 records omitted/)).toBeInTheDocument();
        expect(container.querySelector("details")).toHaveAttribute("open");
        expect(screen.getByText(/No dated events returned in this bounded view/)).toBeInTheDocument();
    });

    it("shows retrieval failure and retries", async () => {
        vi.mocked(fetchPatientTimeline).mockRejectedValueOnce(new Error("failed")).mockResolvedValue(snapshot);
        render(<PatientTimeline patientId="synthetic-patient" />);
        await screen.findByText("Unable to load timeline");
        expect(screen.getByText(/No empty-history conclusion/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Refresh timeline" }));
        await screen.findByRole("heading", { name: "Medication recorded" });
        expect(fetchPatientTimeline).toHaveBeenCalledTimes(2);
    });

    it("ignores a late response from another patient", async () => {
        let resolveOld!: (value: PatientTimelineResponse) => void;
        vi.mocked(fetchPatientTimeline).mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve; }))
            .mockResolvedValueOnce({ ...snapshot, patient_id: "other-patient", events: [] });
        const view = render(<PatientTimeline patientId="synthetic-patient" />);
        view.rerender(<PatientTimeline patientId="other-patient" />);
        await screen.findByText(/No dated events returned/);
        await act(async () => { resolveOld(snapshot); });
        expect(screen.queryByText("Synthetic medication")).not.toBeInTheDocument();
    });

    it("opens an exact source record on direct hash navigation", async () => {
        window.history.replaceState(null, "", "#source-medication-record");
        vi.mocked(fetchPatientTimeline).mockResolvedValue(snapshot);
        render(<PatientTimeline patientId="synthetic-patient" />);
        await waitFor(() => expect(document.getElementById("source-medication-record")).toHaveAttribute("open"));
    });
});
