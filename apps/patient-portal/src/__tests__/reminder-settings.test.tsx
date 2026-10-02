import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ReminderSettingsPage from "@/app/(app)/reminders/page";

const { get, put, remove } = vi.hoisted(() => ({
    get: vi.fn(),
    put: vi.fn(),
    remove: vi.fn(),
}));
vi.mock("@/services/api", () => ({ api: { get, put, delete: remove } }));
vi.mock("react-redux", () => ({ useSelector: () => "synthetic-token" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ back: vi.fn() }) }));
vi.mock("@/services/timezones", () => ({
    getBrowserTimezone: () => "America/Los_Angeles",
    getSupportedTimezones: () => ["America/Los_Angeles", "America/New_York"],
}));

function target(id: string, name: string, automatic = true) {
    return {
        target_type: "obligation",
        target_id: id,
        name,
        frequency: automatic ? "three times per week" : "after each walking session",
        description: "Follow the clinician-approved instruction.",
        reminder_schedule: null,
        guidance: {
            supports_automatic_reminders: automatic,
            recommended_times_per_day: automatic ? 1 : null,
            recommended_days_per_week: automatic ? 3 : null,
            guidance_text: "Use the approved frequency.",
        },
    };
}

describe("Reminder settings", () => {
    beforeEach(() => {
        vi.clearAllMocks();
        get.mockImplementation((path: string) =>
            Promise.resolve(
                path.endsWith("/me")
                    ? { timezone: "America/Los_Angeles" }
                    : [target("walk", "Walking"), target("check", "After-walking check", false)],
            ),
        );
        put.mockResolvedValue({});
        remove.mockResolvedValue({});
    });

    it("starts with summaries, advanced timezone settings, and no open time editor", async () => {
        render(<ReminderSettingsPage />);
        await screen.findByText("Walking");
        expect(screen.queryByLabelText("Reminder time 1")).not.toBeInTheDocument();
        expect(screen.getByText(/Advanced settings/).closest("details")).not.toHaveAttribute("open");
        expect(screen.getAllByRole("button", { name: "Set reminder" })).toHaveLength(1);
        expect(screen.getByText("No routine reminder")).toBeInTheDocument();
    });

    it("requires patient-selected days and time and saves the exact choices", async () => {
        render(<ReminderSettingsPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Set reminder" }));
        const input = screen.getByLabelText("Reminder time 1");
        expect(input).toHaveValue("");
        expect(screen.getByRole("button", { name: "Save reminder schedule" })).toBeDisabled();
        for (const day of ["mon", "wed", "fri"]) fireEvent.click(screen.getByRole("checkbox", { name: day }));
        fireEvent.change(input, { target: { value: "18:30" } });
        fireEvent.click(screen.getByRole("button", { name: "Save reminder schedule" }));
        await waitFor(() =>
            expect(put).toHaveBeenCalledWith(
                "/api/v1/reminders/obligation/walk",
                {
                    timezone: "America/Los_Angeles",
                    times_of_day: ["18:30"],
                    days_of_week: ["monday", "wednesday", "friday"],
                    is_enabled: true,
                },
                { token: "synthetic-token" },
            ),
        );
        await waitFor(() => expect(screen.queryByLabelText("Reminder time 1")).not.toBeInTheDocument());
    });

    it("allows one editor at a time and cancel discards unsaved preferences", async () => {
        get.mockImplementation((path: string) =>
            Promise.resolve(
                path.endsWith("/me")
                    ? { timezone: "America/Los_Angeles" }
                    : [target("walk", "Walking"), target("water", "Hydration")],
            ),
        );
        render(<ReminderSettingsPage />);
        const buttons = await screen.findAllByRole("button", {
            name: "Set reminder",
        });
        fireEvent.click(buttons[0]);
        expect(screen.getByRole("button", { name: "Set reminder" })).toBeDisabled();
        fireEvent.change(screen.getByLabelText("Reminder time 1"), {
            target: { value: "12:45" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        fireEvent.click(screen.getAllByRole("button", { name: "Set reminder" })[0]);
        expect(screen.getByLabelText("Reminder time 1")).toHaveValue("");
        expect(put).not.toHaveBeenCalled();
    });

    it("retains an existing timezone and offers removal of unsafe legacy reminders without an editor", async () => {
        const entry = {
            ...target("check", "After-walking check", false),
            reminder_schedule: {
                id: "schedule",
                patient_id: "synthetic",
                target_type: "obligation",
                target_id: "check",
                timezone: "America/New_York",
                times_of_day: ["17:30:00"],
                days_of_week: ["monday"],
                is_enabled: true,
                created_at: "2026-10-02",
            },
        };
        get.mockImplementation((path: string) =>
            Promise.resolve(path.endsWith("/me") ? { timezone: "America/Los_Angeles" } : [entry]),
        );
        render(<ReminderSettingsPage />);
        await screen.findByText("After-walking check");
        expect(screen.getByText(/mon · 17:30 · America\/New_York/)).toBeInTheDocument();
        expect(screen.getByText("Review old reminder")).toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Edit reminder" })).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Clear schedule" }));
        await waitFor(() =>
            expect(remove).toHaveBeenCalledWith("/api/v1/reminders/obligation/check", { token: "synthetic-token" }),
        );
    });

    it("preserves entered preferences on a save error", async () => {
        put.mockRejectedValue(new Error("Synthetic save failed"));
        render(<ReminderSettingsPage />);
        fireEvent.click(await screen.findByRole("button", { name: "Set reminder" }));
        for (const day of ["mon", "wed", "fri"]) fireEvent.click(screen.getByRole("checkbox", { name: day }));
        fireEvent.change(screen.getByLabelText("Reminder time 1"), {
            target: { value: "18:30" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Save reminder schedule" }));
        await screen.findByText("Synthetic save failed");
        expect(screen.getByLabelText("Reminder time 1")).toHaveValue("18:30");
        expect(screen.getByRole("button", { name: "Save reminder schedule" })).toBeEnabled();
    });
});
