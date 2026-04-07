import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Card } from "@/components/ui/card";

describe("Card", () => {
    it("renders children and applies padding classes", () => {
        const { container } = render(<Card padding="lg">Card body</Card>);
        const card = screen.getByText("Card body");
        expect(card).toBeInTheDocument();
        expect(container.firstElementChild?.className).toContain("p-6");
    });
});
