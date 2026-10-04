import { act, render, screen, waitFor } from "@testing-library/react";
import { hydrateRoot } from "react-dom/client";
import { renderToString } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

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
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it.each([true, false])("hydrates without a mismatch when restored authentication is %s", async (isAuthenticated) => {
        const content = (
            <ProtectedRoute>
                <aside>Clinician appointments</aside>
            </ProtectedRoute>
        );
        mockUseSelector.mockReturnValue({ isAuthenticated: false, loading: true });
        const container = document.createElement("div");
        container.innerHTML = renderToString(content);
        expect(container.textContent).not.toContain("Clinician appointments");
        document.body.appendChild(container);

        mockUseSelector.mockReturnValue({ isAuthenticated, loading: false });
        const onRecoverableError = vi.fn();
        let root: ReturnType<typeof hydrateRoot> | undefined;
        try {
            await act(async () => {
                root = hydrateRoot(container, content, { onRecoverableError });
            });
            expect(onRecoverableError).not.toHaveBeenCalled();
            if (isAuthenticated) {
                expect(screen.getByText("Clinician appointments")).toBeInTheDocument();
                expect(mockReplace).not.toHaveBeenCalled();
            } else {
                expect(container.innerHTML).toBe("");
                expect(mockReplace).toHaveBeenCalledWith(
                    "/login?return_path=%2Fdashboard%3Ftab%3Drisk",
                );
            }
        } finally {
            await act(async () => root?.unmount());
            container.remove();
        }
    });

    it("keeps protected content hidden and does not redirect while restoring a session", () => {
        mockUseSelector.mockReturnValue({ isAuthenticated: false, loading: true });
        const { container, rerender } = render(
            <ProtectedRoute>
                <p>Dashboard content</p>
            </ProtectedRoute>,
        );
        expect(container.firstChild).not.toBeNull();
        expect(screen.queryByText("Dashboard content")).not.toBeInTheDocument();
        expect(mockReplace).not.toHaveBeenCalled();

        mockUseSelector.mockReturnValue({ isAuthenticated: true, loading: false });
        rerender(
            <ProtectedRoute>
                <p>Dashboard content</p>
            </ProtectedRoute>,
        );
        expect(screen.getByText("Dashboard content")).toBeInTheDocument();
        expect(mockReplace).not.toHaveBeenCalled();
    });

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
