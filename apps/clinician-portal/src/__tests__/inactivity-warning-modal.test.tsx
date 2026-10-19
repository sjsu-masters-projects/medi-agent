import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { InactivityWarningModal, formatCountdown } from "@/components/layouts/inactivity-warning-modal";

describe("InactivityWarningModal", () => {
    it("formats the countdown as minutes and seconds", () => {
        expect(formatCountdown(120_000)).toBe("2:00");
        expect(formatCountdown(59_001)).toBe("1:00");
        expect(formatCountdown(5_000)).toBe("0:05");
    });

    it("shows the countdown and keeps the session on Stay signed in", () => {
        const onStay = vi.fn();
        render(<InactivityWarningModal onStay={onStay} remainingMs={120_000} />);
        expect(screen.getByText(/You'll be signed out in 2:00 for inactivity/)).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Stay signed in" }));
        expect(onStay).toHaveBeenCalled();
    });

    it("renders nothing when no warning is due", () => {
        render(<InactivityWarningModal onStay={vi.fn()} remainingMs={null} />);
        expect(screen.queryByRole("dialog")).toBeNull();
    });
});
