import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/button";

describe("Button", () => {
    it("renders the primary variant", () => {
        render(<Button variant="primary">Click me</Button>);
        const button = screen.getByRole("button", { name: /click me/i });
        expect(button).toBeInTheDocument();
        expect(button.className).toContain("bg-blue-600");
    });

    it("calls onClick handlers", () => {
        const handler = vi.fn();
        render(<Button onClick={handler}>Save</Button>);
        fireEvent.click(screen.getByRole("button", { name: /save/i }));
        expect(handler).toHaveBeenCalledOnce();
    });
});
