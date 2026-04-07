import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { RiskBadge } from "@/components/features/risk-badge";

describe("RiskBadge", () => {
    it("renders the correct label and styling for high risk", () => {
        const { container } = render(<RiskBadge level="high" />);
        const badge = screen.getByText("High");
        expect(badge).toBeInTheDocument();
        expect(container.firstElementChild?.className).toContain("bg-red-100");
    });
});
