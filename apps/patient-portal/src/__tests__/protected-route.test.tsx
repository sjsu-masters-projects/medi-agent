import { render, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

const mockReplace = vi.fn();
const mockUseSelector = vi.fn();

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace: mockReplace }),
    usePathname: () => "/today",
    useSearchParams: () => new URLSearchParams("from=nav"),
}));

vi.mock("react-redux", () => ({
    useSelector: (selector: (state: unknown) => unknown) => mockUseSelector(selector),
}));

import { ProtectedRoute } from "@/components/layouts/protected-route";

describe("ProtectedRoute (patient portal)", () => {
    it("redirects to login with return_path when unauthenticated", async () => {
        mockUseSelector.mockReturnValue({ isAuthenticated: false, loading: false });

        render(
            <ProtectedRoute>
                <p>Protected content</p>
            </ProtectedRoute>,
        );

        await waitFor(() => {
            expect(mockReplace).toHaveBeenCalledWith(expect.stringContaining("/login?"));
        });

        const calledWith = mockReplace.mock.calls[0]?.[0] as string;
        expect(calledWith).toContain("return_path=%2Ftoday%3Ffrom%3Dnav");
    });
});
