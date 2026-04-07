import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ErrorState } from "@/components/ui/error-state";

describe("ErrorState", () => {
    it("renders default error message", () => {
        render(<ErrorState />);
        expect(screen.getByText("Error")).toBeInTheDocument();
        expect(screen.getByText("Something went wrong. Please try again.")).toBeInTheDocument();
    });

    it("renders custom title and description", () => {
        render(<ErrorState description="Could not reach the server." title="Network error" />);
        expect(screen.getByText("Network error")).toBeInTheDocument();
        expect(screen.getByText("Could not reach the server.")).toBeInTheDocument();
    });

    it("calls onRetry when Try again is clicked", () => {
        const onRetry = vi.fn();
        render(<ErrorState onRetry={onRetry} />);
        fireEvent.click(screen.getByRole("button", { name: /try again/i }));
        expect(onRetry).toHaveBeenCalledOnce();
    });

    it("does not render retry button when onRetry is not provided", () => {
        render(<ErrorState />);
        expect(screen.queryByRole("button", { name: /try again/i })).not.toBeInTheDocument();
    });
});
