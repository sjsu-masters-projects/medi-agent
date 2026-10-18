import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EarlierMessages } from "@/components/features/operational-alerts";
import { fetchAllSentMessages, type ClinicianMessageInboxItem } from "@/services/clinicians";

vi.mock("@/hooks/use-clinic-filter", async () => (await import("@/test/clinic-filter-mock")).clinicFilterModule);
vi.mock("@/services/clinicians", () => ({
    fetchAllSentMessages: vi.fn(),
}));

afterEach(cleanup);

const message = (overrides: Partial<ClinicianMessageInboxItem> = {}): ClinicianMessageInboxItem => ({
    id: "msg-1",
    clinicianId: "clinician-1",
    patientId: "patient-1",
    channel: "in_app" as ClinicianMessageInboxItem["channel"],
    subject: "Follow-up",
    body: "Please bring your medication list to the next visit.",
    isRead: false,
    createdAt: "2026-05-10T10:00:00Z",
    patientFirstName: "Elena",
    patientLastName: "Park",
    ...overrides,
});

describe("Earlier messages", () => {
    beforeEach(() => vi.mocked(fetchAllSentMessages).mockReset());

    it("is a collapsed history section with a count", async () => {
        vi.mocked(fetchAllSentMessages).mockResolvedValue([message(), message({ id: "msg-2" })]);
        const { container } = render(<EarlierMessages />);
        expect(await screen.findByText("Earlier messages (2)")).toBeInTheDocument();
        expect(container.querySelector("details")).not.toHaveAttribute("open");
        expect(screen.getByText(/History only, not active work/)).toBeInTheDocument();
    });

    it("shows an empty state", async () => {
        vi.mocked(fetchAllSentMessages).mockResolvedValue([]);
        render(<EarlierMessages />);
        expect(await screen.findByText("No earlier messages.")).toBeInTheDocument();
    });

    it("shows human messages and summarizes escalation notices without their internal text", async () => {
        vi.mocked(fetchAllSentMessages).mockResolvedValue([
            message(),
            message({
                id: "msg-2",
                channel: "email" as ClinicianMessageInboxItem["channel"],
                subject: undefined,
                body: "Your lab results are ready.",
                patientFirstName: "Carlos",
                patientLastName: "Ruiz",
            }),
            message({
                id: "msg-3",
                subject: "Urgent patient chat escalation",
                body: "Chat escalation flagged (urgent/general) for patient 00000000-0000-0000-0000-000000000001.",
            }),
        ]);
        render(<EarlierMessages />);
        expect(await screen.findByText("Please bring your medication list to the next visit.")).toBeInTheDocument();
        expect(screen.getByText("Sent by email")).toBeInTheDocument();
        expect(screen.getByText(/Chat escalation · urgent/)).toBeInTheDocument();
        expect(screen.queryByText(/00000000-0000-0000-0000-000000000001/)).not.toBeInTheDocument();
    });
});

// Kept apart from the reset hook above: resetting a mock that then rejects makes Vitest
// report the handled rejection as unhandled.
describe("Earlier messages failure", () => {
    it("reports a load failure in the visible header", async () => {
        vi.mocked(fetchAllSentMessages).mockImplementation(async () => {
            throw new Error("Unable to load messages.");
        });
        render(<EarlierMessages />);
        expect(await screen.findByRole("alert")).toHaveTextContent("Unable to load messages.");
    });
});
