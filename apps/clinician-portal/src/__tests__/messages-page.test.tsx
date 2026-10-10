import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OperationalAlerts as MessagesPage } from "@/components/features/operational-alerts";
import { fetchAllSentMessages } from "@/services/clinicians";

vi.mock("@/services/clinicians", () => ({
    fetchAllSentMessages: vi.fn(),
}));

afterEach(cleanup);

describe("MessagesPage", () => {
    beforeEach(() => {
        vi.mocked(fetchAllSentMessages).mockReset();
    });

    it("shows loading skeletons while fetching", () => {
        vi.mocked(fetchAllSentMessages).mockReturnValue(new Promise(() => {}));

        render(<MessagesPage />);

        expect(screen.getByText("Operational alert history")).toBeInTheDocument();
        // Skeletons are rendered during load
        expect(screen.queryByText("No operational alerts yet")).not.toBeInTheDocument();
    });

    it("renders the empty state when no messages exist", async () => {
        vi.mocked(fetchAllSentMessages).mockResolvedValue([]);

        render(<MessagesPage />);

        expect(await screen.findByText("No operational alerts yet")).toBeInTheDocument();
        expect(
            screen.getByText(/Operational notification history/i),
        ).toBeInTheDocument();
    });

    it("renders sent messages with patient name and channel badge", async () => {
        vi.mocked(fetchAllSentMessages).mockResolvedValue([
            {
                id: "msg-1",
                clinicianId: "clinician-1",
                patientId: "patient-1",
                channel: "in_app",
                subject: "Follow-up",
                body: "Please bring your medication list to the next visit.",
                isRead: false,
                createdAt: "2026-05-10T10:00:00Z",
                patientFirstName: "Elena",
                patientLastName: "Park",
            },
            {
                id: "msg-2",
                clinicianId: "clinician-1",
                patientId: "patient-2",
                channel: "email",
                body: "Your lab results are ready.",
                isRead: false,
                createdAt: "2026-05-09T08:00:00Z",
                patientFirstName: "Carlos",
                patientLastName: "Rivera",
            },
        ]);

        render(<MessagesPage />);

        expect(await screen.findByText("Elena Park")).toBeInTheDocument();
        expect(screen.getByText("Carlos Rivera")).toBeInTheDocument();
        expect(screen.getByText("Follow-up")).toBeInTheDocument();
        expect(screen.getByText(/medication list/i)).toBeInTheDocument();
        expect(screen.getAllByText("In-app").length).toBeGreaterThanOrEqual(1);
        expect(screen.getAllByText("Email").length).toBeGreaterThanOrEqual(1);
    });

    it("shows an error banner when the fetch fails", async () => {
        vi.mocked(fetchAllSentMessages).mockRejectedValue(
            new Error("Network failure"),
        );

        render(<MessagesPage />);

        const alert = await screen.findByRole("alert");
        expect(alert).toHaveTextContent("Network failure");
    });

    it("refreshes messages when the Refresh button is clicked", async () => {
        vi.mocked(fetchAllSentMessages).mockResolvedValue([]);

        render(<MessagesPage />);

        await screen.findByText("No operational alerts yet");
        expect(fetchAllSentMessages).toHaveBeenCalledTimes(1);

        vi.mocked(fetchAllSentMessages).mockResolvedValue([
            {
                id: "msg-3",
                clinicianId: "clinician-1",
                patientId: "patient-3",
                channel: "in_app",
                body: "New message after refresh.",
                isRead: false,
                createdAt: "2026-05-11T12:00:00Z",
                patientFirstName: "Maya",
                patientLastName: "Chen",
            },
        ]);

        fireEvent.click(screen.getByRole("button", { name: /refresh/i }));

        await waitFor(() =>
            expect(fetchAllSentMessages).toHaveBeenCalledTimes(2),
        );
        expect(await screen.findByText("Maya Chen")).toBeInTheDocument();
    });

    it("displays summary counts correctly", async () => {
        vi.mocked(fetchAllSentMessages).mockResolvedValue([
            {
                id: "msg-a",
                clinicianId: "c1",
                patientId: "p1",
                channel: "in_app",
                body: "Hello",
                isRead: false,
                createdAt: "2026-05-10T10:00:00Z",
                patientFirstName: "A",
                patientLastName: "B",
            },
            {
                id: "msg-b",
                clinicianId: "c1",
                patientId: "p2",
                channel: "email",
                body: "Hi",
                isRead: false,
                createdAt: "2026-05-10T11:00:00Z",
                patientFirstName: "C",
                patientLastName: "D",
            },
        ]);

        render(<MessagesPage />);

        // Wait for data to load
        await screen.findByText("A B");

        // Total sent = 2, In-app = 1, Email = 1
        const counts = screen.getAllByText("1");
        expect(counts.length).toBeGreaterThanOrEqual(2);
        expect(screen.getByText("2")).toBeInTheDocument();
    });
});
