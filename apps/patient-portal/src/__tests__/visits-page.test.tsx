import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import VisitsPage from "@/app/(app)/visits/page";

vi.mock("next/navigation", () => ({
    useRouter: () => ({ back: vi.fn() }),
}));

describe("VisitsPage", () => {
    it("shows an empty state instead of hardcoded visit data", () => {
        render(<VisitsPage />);

        expect(screen.getByText(/No visits scheduled yet/i)).toBeInTheDocument();
        expect(screen.queryByText(/Blood pressure follow-up/i)).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: /Message care team/i })).toBeInTheDocument();
    });
});
