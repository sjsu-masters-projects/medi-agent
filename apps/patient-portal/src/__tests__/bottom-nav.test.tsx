import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BottomNav } from "@/components/layouts/bottom-nav";

describe("BottomNav", () => {
    it("marks the active destination and keeps chat accessible", () => {
        render(<BottomNav currentPath="/records" />);

        expect(screen.getByRole("link", { name: /records/i })).toHaveAttribute(
            "aria-current",
            "page",
        );
        expect(screen.getByRole("link", { name: /open care chat/i })).toHaveAttribute(
            "href",
            "/chat",
        );
        expect(screen.getByRole("link", { name: /today/i })).not.toHaveAttribute(
            "aria-current",
        );
    });
});
