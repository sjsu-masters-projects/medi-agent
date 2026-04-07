import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockReplace = vi.fn();
const mockUseSelector = vi.fn();

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace: mockReplace }),
}));

vi.mock("react-redux", () => ({
    useSelector: (selector: (state: unknown) => unknown) => mockUseSelector(selector),
}));

import { ProtectedRoute } from "@/components/layouts/protected-route";

describe("ProtectedRoute", () => {
    it("renders children when authenticated", () => {
        mockUseSelector.mockReturnValue({ isAuthenticated: true, loading: false });
        render(
            <ProtectedRoute>
                <p>Dashboard content</p>
            </ProtectedRoute>,
        );
        expect(screen.getByText("Dashboard content")).toBeInTheDocument();
    });

    it("renders nothing when not authenticated and not loading", () => {
        mockUseSelector.mockReturnValue({ isAuthenticated: false, loading: false });
        const { container } = render(
            <ProtectedRoute>
                <p>Dashboard content</p>
            </ProtectedRoute>,
        );
        expect(container.innerHTML).toBe("");
    });
});
