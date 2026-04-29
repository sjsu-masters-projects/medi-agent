import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockReplace = vi.fn();
const mockUseSelector = vi.fn();

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace: mockReplace }),
    usePathname: () => "/dashboard",
    useSearchParams: () => new URLSearchParams("tab=risk"),
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

    it("redirects to login with return_path when unauthenticated", async () => {
        mockUseSelector.mockReturnValue({ isAuthenticated: false, loading: false });

        render(
            <ProtectedRoute>
                <p>Dashboard content</p>
            </ProtectedRoute>,
        );

        await waitFor(() => {
            expect(mockReplace).toHaveBeenCalledWith(
                expect.stringContaining("/login?"),
            );
        });

        const calledWith = mockReplace.mock.calls[0]?.[0] as string;
        expect(calledWith).toContain("return_path=%2Fdashboard%3Ftab%3Drisk");
    });
});
