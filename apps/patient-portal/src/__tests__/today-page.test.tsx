import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import TodayPage from "@/app/(app)/today/page";
import { FeedTaskStatus, FeedTaskType, type FeedTask } from "@/types";
const destination = vi.hoisted(() => ({ params: new URLSearchParams() }));
vi.mock("next/navigation", () => ({ useSearchParams: () => destination.params }));
vi.mock("@/components/features/approved-plan-details", () => ({ ApprovedPlanDetails: ({ locale }: { locale: string }) => <p>Approved snapshot {locale}</p> }));

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
        error: null as string | null,
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
    afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); });
    beforeEach(() => {
        destination.params = new URLSearchParams();
        markComplete.mockReset();
        reportBarrier.mockReset();
        refreshFeed.mockReset();
        useFeedData.mockReset();
        usePatientProfile.mockReset();
        usePatientProfile.mockReturnValue(null);
    });

    it("opens the exact authorized activity from its canonical UUID, without changing completion", async () => {
        destination.params = new URLSearchParams("activity=exact-activity");
        const task = { id: "obligation:exact-activity:unscheduled", targetId: "exact-activity", type: FeedTaskType.OBLIGATION, name: "Exact approved activity", status: FeedTaskStatus.PENDING } as FeedTask;
        mockFeedData({ tasks: [task, { ...task, id: "other", targetId: "other", name: "Other activity" }] });
        render(<TodayPage />);
        const dialog = await screen.findByRole("dialog");
        expect(within(dialog).getByText("Exact approved activity")).toBeInTheDocument();
        expect(within(dialog).queryByText("Other activity")).not.toBeInTheDocument();
        expect(markComplete).not.toHaveBeenCalled();
    });

    it("shows unavailable for a non-scheduled activity and never selects the next task instead", () => {
        destination.params = new URLSearchParams("activity=not-today");
        mockFeedData({ tasks: [{ id: "other", targetId: "other", type: FeedTaskType.OBLIGATION, name: "Other activity", status: FeedTaskStatus.PENDING } as FeedTask] });
        render(<TodayPage />);
        expect(screen.getByText("This activity is unavailable today. Refresh your activities.")).toBeInTheDocument();
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    });

    it("opens approved-plan details even on a day with no scheduled activities", () => {
        destination.params = new URLSearchParams("view=care-plan");
        mockFeedData();
        render(<TodayPage />);
        expect(within(screen.getByRole("dialog")).getByText("Approved snapshot en-US")).toBeInTheDocument();
    });

    it("shows all today's occurrences of the exact activity without selecting an unrelated activity", async () => {
        destination.params = new URLSearchParams("activity=twice-daily");
        const task = { targetId: "twice-daily", type: FeedTaskType.MEDICATION, name: "Exact medication", status: FeedTaskStatus.PENDING } as FeedTask;
        mockFeedData({ tasks: [{ ...task, id: "morning", scheduledTime: "08:00" }, { ...task, id: "evening", scheduledTime: "20:00" }, { ...task, id: "unrelated", targetId: "other", name: "Unrelated medication" }] });
        render(<TodayPage />);
        const dialog = await screen.findByRole("dialog");
        expect(within(dialog).getAllByText("Exact medication")).toHaveLength(2);
        expect(within(dialog).queryByText("Unrelated medication")).not.toBeInTheDocument();
        expect(markComplete).not.toHaveBeenCalled();
    });

    it("localizes Spanish chrome and uses the saved timezone at a UTC day boundary", () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date("2026-10-10T01:00:00Z"));
        usePatientProfile.mockReturnValue({ firstName: "Morgan", preferredLanguage: "es-MX", timezone: "America/Los_Angeles" });
        mockFeedData();
        render(<TodayPage />);
        expect(useFeedData).toHaveBeenCalledWith("es-MX");
        expect(screen.getByRole("heading", { name: "Hola, Morgan" })).toBeInTheDocument();
        expect(screen.getByText("viernes, 9 de octubre")).toBeInTheDocument();
        expect(screen.getByRole("region", { name: "Progreso diario" })).toBeInTheDocument();
        expect(screen.getByText("1 de 2 tareas completadas")).toBeInTheDocument();
        expect(screen.getByText("Racha de 4 días")).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: "Actividades de hoy" })).toBeInTheDocument();
        expect(screen.getByText("No hay actividades programadas")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /Reportar un síntoma/ })).toHaveAttribute("href", "/chat");
    });

    it("uses UTC for an invalid saved timezone and keeps errors and retry localized", () => {
        vi.useFakeTimers();
        vi.setSystemTime(new Date("2026-10-10T01:00:00Z"));
        usePatientProfile.mockReturnValue({ preferredLanguage: "es-MX", timezone: "Invalid/Zone" });
        mockFeedData({ error: "No se pudieron cargar tus actividades." });
        render(<TodayPage />);
        expect(screen.getByText("sábado, 10 de octubre")).toBeInTheDocument();
        expect(screen.getByText("No se pudieron cargar las actividades")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Intentar de nuevo" }));
        expect(refreshFeed).toHaveBeenCalledOnce();
        expect(screen.queryByText("Try again")).not.toBeInTheDocument();
    });

    it("localizes reminder and plan labels while retaining clinical wording and completion semantics", async () => {
        usePatientProfile.mockReturnValue({ preferredLanguage: "es-MX", timezone: "America/Los_Angeles" });
        const task = { id: "synthetic", targetId: "synthetic-activity", type: FeedTaskType.OBLIGATION, name: "Source title", description: "Keep this source instruction unchanged.", frequency: "Every Monday", status: FeedTaskStatus.PENDING, requiresScheduleConfiguration: true, carePlan: { category: "follow_up", versionNumber: 3 } } as FeedTask;
        mockFeedData({ tasks: [task] });
        render(<TodayPage />);
        expect(screen.getByRole("link", { name: "Configurar horario del recordatorio" })).toHaveAttribute("href", "/reminders");
        expect(screen.getByText("Configurar horario del recordatorio")).toBeInTheDocument();
        expect(screen.getByText("Aprobado por tu equipo de atención")).toBeInTheDocument();
        expect(screen.getByText("Detalles del plan de atención")).toBeInTheDocument();
        expect(screen.getByText(task.name)).toBeInTheDocument();
        expect(screen.getByText(task.description!)).toBeInTheDocument();
        expect(screen.getByText(task.frequency!)).toBeInTheDocument();
        await act(async () => fireEvent.click(screen.getByRole("button", { name: "Marcar como completada" })));
        expect(markComplete).toHaveBeenCalledWith(task);
        fireEvent.click(screen.getByRole("button", { name: "Detalles del plan de atención" }));
        expect(screen.getByText(/Versión 3 del plan aprobado/)).toBeInTheDocument();
    });

    it.each([
        ["side_effects", "Efectos secundarios"], ["cost", "Costo"], ["access", "Acceso"],
        ["schedule", "Horario"], ["confusion", "Confusión"], ["other", "Enviar al equipo de atención"],
    ])("submits the original %s barrier code from Spanish controls and retains failed notes", async (code, label) => {
        usePatientProfile.mockReturnValue({ preferredLanguage: "es-MX" });
        reportBarrier.mockResolvedValue(false);
        const task = { id: "synthetic", name: "Source activity", type: FeedTaskType.OBLIGATION, status: FeedTaskStatus.PENDING } as FeedTask;
        mockFeedData({ tasks: [task], actionError: "No pudimos confirmar que se guardó tu respuesta." });
        render(<TodayPage />);
        fireEvent.click(screen.getByRole("button", { name: "No pude hacer esto" }));
        expect(screen.getByRole("button", { name: "Cerrar ventana" })).toBeInTheDocument();
        expect(screen.getByLabelText("Otro (describe el motivo)")).toBeInTheDocument();
        fireEvent.change(screen.getByRole("textbox"), { target: { value: "Synthetic note" } });
        fireEvent.click(screen.getByRole("button", { name: label }));
        await waitFor(() => expect(reportBarrier).toHaveBeenCalledWith(task, code, "Synthetic note"));
        expect(screen.getByRole("textbox")).toHaveValue("Synthetic note");
        expect(screen.getByRole("alert")).toHaveTextContent("No pudimos confirmar");
        fireEvent.click(screen.getByRole("button", { name: "Cerrar ventana" }));
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    });

    it("keeps a Spanish future dose upcoming without completion controls", () => {
        usePatientProfile.mockReturnValue({ preferredLanguage: "es-MX" });
        mockFeedData({ tasks: [{ id: "synthetic", name: "Source medication 500 mg", type: FeedTaskType.MEDICATION, status: FeedTaskStatus.PENDING, scheduledTime: "18:00", scheduledAt: new Date(Date.now() + 3_600_000).toISOString() } as FeedTask] });
        render(<TodayPage />);
        expect(within(screen.getByRole("list")).getByText("Próxima")).toBeInTheDocument();
        expect(screen.queryByText("Para ahora")).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Marcar como tomado" })).not.toBeInTheDocument();
    });

    it.each([
        ["medication", "medicamento"], ["nutrition", "nutrición"], ["movement", "movimiento"],
        ["hydration", "hidratación"], ["monitoring", "monitoreo"], ["follow_up", "seguimiento"],
        ["other", "otra actividad"], ["unknown", "Actividad de atención"],
    ])("localizes the %s approved category", (category, label) => {
        usePatientProfile.mockReturnValue({ preferredLanguage: "es-MX" });
        mockFeedData({ tasks: [{ id: "synthetic", name: "Source activity", type: FeedTaskType.OBLIGATION, status: FeedTaskStatus.PENDING, carePlan: { category, versionNumber: 1 } } as FeedTask] });
        render(<TodayPage />);
        fireEvent.click(screen.getByRole("button", { name: "Detalles del plan de atención" }));
        expect(screen.getByText(`Aprobado por tu equipo de atención • ${label}`)).toBeInTheDocument();
    });

    it("localizes due-now clock and saving copy while keeping controls disabled during submission", () => {
        usePatientProfile.mockReturnValue({ preferredLanguage: "es-MX" });
        const task = { id: "synthetic", name: "Source medication 500 mg", type: FeedTaskType.MEDICATION, status: FeedTaskStatus.PENDING, scheduledTime: "08:00", scheduledAt: new Date(Date.now() - 60_000).toISOString() } as FeedTask;
        mockFeedData({ tasks: [task] });
        const { rerender } = render(<TodayPage />);
        expect(screen.getByText(/^8:00/)).toBeInTheDocument();
        expect(screen.getByText("Para ahora")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "No pude hacer esto" }));
        mockFeedData({ tasks: [task], submitting: true });
        rerender(<TodayPage />);
        expect(screen.getByRole("button", { name: "Guardando…" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Efectos secundarios" })).toBeDisabled();
        expect(screen.getByRole("button", { name: "Marcar como tomado" })).toBeDisabled();
        fireEvent.click(screen.getByRole("button", { name: "Cerrar ventana" }));
        expect(screen.getByRole("textbox")).toBeInTheDocument();
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

        expect(screen.getByText("0 of 0 tasks completed")).toBeInTheDocument();
        expect(screen.getByTestId("today-progress-segments").children).toHaveLength(0);
        expect(screen.queryByText("NaN%")).not.toBeInTheDocument();
    });

    it("renders a calm loading state while the first feed load is pending", () => {
        mockFeedData({ loading: true, tasks: [] });

        const { container } = render(<TodayPage />);

        expect(container.querySelectorAll(".ma-skeleton")).toHaveLength(4);
        expect(screen.queryByText(/Today's schedule/i)).not.toBeInTheDocument();
    });

    it("shows an empty state when no care-plan tasks are scheduled", () => {
        mockFeedData({ tasks: [] });

        render(<TodayPage />);

        expect(screen.getByText(/Nothing scheduled/i)).toBeInTheDocument();
        expect(screen.getByText(/clinicians have not assigned anything/i)).toBeInTheDocument();
    });

    it("highlights due-now work and lets patients complete it", async () => {
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

        expect(screen.getByText(/^8:00\sAM$/i)).toBeInTheDocument();
        expect(screen.getByText("Due now")).toBeInTheDocument();
        expect(screen.getByText(/Lisinopril/i)).toBeInTheDocument();
        expect(screen.queryByText("Care-team approved • monitoring")).not.toBeInTheDocument();
        expect(screen.getByText("Care plan approved by Dr. Chen")).toBeInTheDocument();
        expect(screen.queryByText("Prescribed by Dr. Chen")).not.toBeInTheDocument();

        await act(async () => fireEvent.click(screen.getByRole("button", { name: /mark as taken/i })));
        expect(markComplete).toHaveBeenCalledWith(task);
        fireEvent.click(screen.getByRole("button", { name: "Care plan details" }));
        expect(screen.getByText(/Approved plan version 2/)).toBeInTheDocument();
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

    it.each([false, true])("only animates a confirmed completion (saved: %s)", async (saved) => {
        vi.useFakeTimers();
        const task = { id: "animation-task", targetId: "activity", type: FeedTaskType.OBLIGATION,
            name: "Drink water", status: FeedTaskStatus.PENDING } as FeedTask;
        markComplete.mockResolvedValue(saved);
        mockFeedData({ tasks: [task] });
        render(<TodayPage />);
        const hero = screen.getByRole("article");
        await act(async () => fireEvent.click(screen.getByRole("button", { name: "Mark as Done" })));
        expect(hero).toHaveAttribute("data-completion-phase", saved ? "checked" : "idle");
        if (saved) {
            expect(screen.getByRole("button", { name: "Mark as Done" })).toBeDisabled();
            act(() => vi.advanceTimersByTime(160));
            expect(hero).toHaveAttribute("data-completion-phase", "leaving");
            act(() => vi.advanceTimersByTime(160));
            expect(hero).toHaveAttribute("data-completion-phase", "idle");
        }
        expect(screen.getByRole("button", { name: "Mark as Done" })).toBeEnabled();
        expect(markComplete).toHaveBeenCalledOnce();
    });

    it("does not animate confirmed completion when reduced motion is requested", async () => {
        vi.stubGlobal("matchMedia", vi.fn(() => ({ matches: true })));
        markComplete.mockResolvedValue(true);
        mockFeedData({ tasks: [{ id: "reduced-motion", targetId: "activity", type: FeedTaskType.OBLIGATION,
            name: "Drink water", status: FeedTaskStatus.PENDING } as FeedTask] });
        render(<TodayPage />);
        await act(async () => fireEvent.click(screen.getByRole("button", { name: "Mark as Done" })));
        expect(screen.getByRole("article")).toHaveAttribute("data-completion-phase", "idle");
        expect(screen.getByRole("button", { name: "Mark as Done" })).toBeEnabled();
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

        const setupLink = screen.getByRole("link", { name: /^set reminder time$/i });
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
        expect(screen.getByText("1 of 4 tasks completed")).toBeInTheDocument();
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
