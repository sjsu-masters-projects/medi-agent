import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TodayPage from "@/app/(app)/today/page";
import { FeedTaskStatus, FeedTaskType, type FeedTask } from "@/types";

const { importDocumentFile, markComplete, refreshFeed, useFeedData, usePatientProfile } = vi.hoisted(() => ({
    importDocumentFile: vi.fn(),
    markComplete: vi.fn(),
    refreshFeed: vi.fn(),
    useFeedData: vi.fn(),
    usePatientProfile: vi.fn(),
}));

vi.mock("@/hooks/use-feed-data", () => ({
    useFeedData,
}));

vi.mock("@/hooks/use-patient-profile", () => ({
    usePatientProfile,
}));

function mockFeedData(overrides: Partial<ReturnType<typeof baseFeedData>> = {}) {
    useFeedData.mockReturnValue({ ...baseFeedData(), ...overrides });
}

function baseFeedData() {
    return {
        adherenceStats: {
            currentStreakDays: 4,
            overallScore: 0.5,
        },
        documentImportError: null,
        documentImporting: false,
        error: null,
        importDocumentFile,
        loading: false,
        markComplete,
        refreshFeed,
        summary: {
            completed: 1,
            total: 2,
        },
        tasks: [] as FeedTask[],
    };
}

describe("TodayPage", () => {
    beforeEach(() => {
        importDocumentFile.mockReset();
        markComplete.mockReset();
        refreshFeed.mockReset();
        useFeedData.mockReset();
        usePatientProfile.mockReset();
        usePatientProfile.mockReturnValue(null);
    });

    it("uses the logged-in patient profile for the greeting and avatar", () => {
        usePatientProfile.mockReturnValue({ firstName: "Vatsal" });
        mockFeedData({ tasks: [] });

        render(<TodayPage />);

        expect(screen.getByRole("heading", { name: "Hi, Vatsal" })).toBeInTheDocument();
        expect(screen.getByText("V")).toBeInTheDocument();
    });

    it("renders a calm loading state while the first feed load is pending", () => {
        mockFeedData({ loading: true, tasks: [] });

        const { container } = render(<TodayPage />);

        expect(container.querySelectorAll(".animate-pulse")).toHaveLength(3);
        expect(screen.queryByText(/Today's schedule/i)).not.toBeInTheDocument();
    });

    it("shows an empty state when no care-plan tasks are scheduled", () => {
        mockFeedData({ tasks: [] });

        render(<TodayPage />);

        expect(screen.getByText(/Nothing scheduled/i)).toBeInTheDocument();
        expect(screen.getByText(/clinicians have not assigned anything/i)).toBeInTheDocument();
    });

    it("highlights due-now work and lets patients complete it", () => {
        const task = {
            description: "Take with water",
            frequency: "daily",
            id: "task-1",
            name: "Lisinopril 10mg",
            provider: {
                clinicName: "City Health",
                id: "provider-1",
                name: "Dr. Chen",
                specialty: "Primary care",
            },
            requiresScheduleConfiguration: false,
            scheduledTime: "08:00",
            status: FeedTaskStatus.PENDING,
            targetId: "medication-1",
            type: FeedTaskType.MEDICATION,
        };
        mockFeedData({ tasks: [task] });

        render(<TodayPage />);

        expect(screen.getByText(/8:00 AM .* Now/i)).toBeInTheDocument();
        expect(screen.getByText(/Lisinopril/i)).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /mark as taken/i }));
        expect(markComplete).toHaveBeenCalledWith(task);
    });

    it("surfaces reminder schedule gaps with a direct setup link", () => {
        mockFeedData({
            tasks: [
                {
                    description: "Walk for 10 minutes",
                    frequency: "daily walk",
                    id: "task-2",
                    name: "Short walk",
                    requiresScheduleConfiguration: true,
                    scheduledTime: undefined,
                    status: FeedTaskStatus.PENDING,
                    targetId: "obligation-1",
                    type: FeedTaskType.OBLIGATION,
                },
            ],
        });

        render(<TodayPage />);

        const setupLink = screen.getByRole("link", { name: /set reminder times/i });
        expect(setupLink).toHaveAttribute("href", "/reminders");
        expect(screen.getByText(/^Set reminder time$/i)).toBeInTheDocument();
    });

    it("opens the file picker when patients import a clinical document", () => {
        const inputClick = vi
            .spyOn(HTMLInputElement.prototype, "click")
            .mockImplementation(() => {});
        mockFeedData();

        render(<TodayPage />);

        fireEvent.click(screen.getByRole("button", { name: /^Import$/i }));

        expect(inputClick).toHaveBeenCalledOnce();
        inputClick.mockRestore();
    });

    it("imports the selected clinical document file", () => {
        mockFeedData();

        const { container } = render(<TodayPage />);
        const input = container.querySelector<HTMLInputElement>('input[type="file"]');
        const file = new File(["test"], "vatsal-discharge-summary.pdf", {
            type: "application/pdf",
        });

        fireEvent.change(input!, { target: { files: [file] } });

        expect(importDocumentFile).toHaveBeenCalledWith(file);
    });
});
