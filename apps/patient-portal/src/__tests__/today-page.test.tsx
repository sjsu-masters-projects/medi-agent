import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import TodayPage from "@/app/(app)/today/page";
import { FeedTaskStatus, FeedTaskType, type FeedTask } from "@/types";

const { markComplete, reportBarrier, refreshFeed, useFeedData, usePatientProfile } = vi.hoisted(() => ({
    markComplete: vi.fn(),
    reportBarrier: vi.fn(),
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
        error: null,
        loading: false,
        markComplete,
        reportBarrier,
        actionError: null as string | null,
        submitting: false,
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
        markComplete.mockReset();
        reportBarrier.mockReset();
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

    it("renders a safe zero percent when adherence is not finite", () => {
        mockFeedData({
            summary: { completed: 0, total: 0 },
            adherenceStats: {
                currentStreakDays: 0,
                overallScore: Number.NaN,
            },
        });

        render(<TodayPage />);

        expect(screen.getByText("0%")).toBeInTheDocument();
        expect(screen.queryByText("NaN%")).not.toBeInTheDocument();
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
            carePlan: {
                category: "monitoring",
                versionNumber: 2,
            },
            requiresScheduleConfiguration: false,
            scheduledTime: "08:00",
            scheduledAt: new Date(Date.now() - 60_000).toISOString(),
            status: FeedTaskStatus.PENDING,
            targetId: "medication-1",
            type: FeedTaskType.MEDICATION,
        };
        mockFeedData({ tasks: [task] });

        render(<TodayPage />);

        expect(screen.getByText(/8:00 AM .* Now/i)).toBeInTheDocument();
        expect(screen.getByText(/Lisinopril/i)).toBeInTheDocument();
        expect(screen.getByText("Care-team approved • monitoring")).toBeInTheDocument();
        expect(screen.getByText("Care plan approved by Dr. Chen")).toBeInTheDocument();
        expect(screen.queryByText("Prescribed by Dr. Chen")).not.toBeInTheDocument();
        expect(screen.getByText(/Approved plan version 2/)).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /mark as taken/i }));
        expect(markComplete).toHaveBeenCalledWith(task);
    });

    it("keeps a future scheduled dose upcoming instead of due now", () => {
        mockFeedData({ tasks: [{
            id: "future-dose", targetId: "med-1", type: FeedTaskType.MEDICATION,
            name: "Metformin 500 mg", description: "With dinner", frequency: "twice daily",
            scheduledTime: "18:00", scheduledAt: new Date(Date.now() + 3_600_000).toISOString(),
            status: FeedTaskStatus.PENDING,
        }] });
        render(<TodayPage />);
        expect(screen.queryByText("Due now")).not.toBeInTheDocument();
        expect(screen.queryByText(/• Now/)).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: /Mark as Taken/i })).not.toBeInTheDocument();
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

    it("renders obligations without a frequency", () => {
        const incompleteObligation = {
            description: "Record a blood-pressure reading",
            id: "task-3",
            name: "Blood pressure check",
            requiresScheduleConfiguration: false,
            scheduledTime: undefined,
            status: FeedTaskStatus.PENDING,
            targetId: "obligation-2",
            type: FeedTaskType.OBLIGATION,
        } as unknown as FeedTask;
        mockFeedData({
            tasks: [incompleteObligation],
        });

        render(<TodayPage />);

        expect(screen.getByText("Blood pressure check")).toBeInTheDocument();
        expect(screen.getByText("Record a blood-pressure reading")).toBeInTheDocument();
        expect(screen.getByText("Any time")).toBeInTheDocument();
    });

    it("uses today's completion count rather than the 30-day score", () => {
        mockFeedData({ summary: { completed: 1, total: 4 }, adherenceStats: { currentStreakDays: 0, overallScore: 0.9 } });
        render(<TodayPage />);
        expect(screen.getByText("25%")).toBeInTheDocument();
        expect(screen.queryByText("90%")).not.toBeInTheDocument();
    });

    it("shows a saved barrier as reported, not upcoming", () => {
        mockFeedData({ tasks: [{ id: "task-4", name: "Walk", status: FeedTaskStatus.SKIPPED, type: FeedTaskType.OBLIGATION } as FeedTask] });
        render(<TodayPage />);
        expect(screen.getByText("Barrier reported")).toBeInTheDocument();
        expect(screen.queryByText("upcoming")).not.toBeInTheDocument();
    });

    it("keeps the barrier modal and note open when saving fails", async () => {
        reportBarrier.mockResolvedValue(false);
        const task = { id: "task-4", name: "Walk", status: FeedTaskStatus.PENDING, type: FeedTaskType.OBLIGATION } as FeedTask;
        mockFeedData({ tasks: [task] });
        render(<TodayPage />);
        fireEvent.click(screen.getByRole("button", { name: "I couldn't do this" }));
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "Synthetic QA barrier" } });
        fireEvent.click(screen.getByRole("button", { name: "Send to care team" }));
        await waitFor(() => expect(reportBarrier).toHaveBeenCalledWith(task, "other", "Synthetic QA barrier"));
        expect(screen.getByRole("textbox")).toHaveValue("Synthetic QA barrier");
    });

});
