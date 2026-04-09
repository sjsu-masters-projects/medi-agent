import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import OnboardingPage from "@/app/(auth)/onboarding/page";

const { dispatch, post, put, replace } = vi.hoisted(() => ({
    dispatch: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
    useSelector: (selector: (state: unknown) => unknown) =>
        selector({
            auth: { accessToken: "access-token" },
            onboarding: {
                profileDraft: {
                    dateOfBirth: "1990-01-01",
                    firstName: "Sarah",
                    lastName: "Jones",
                },
            },
        }),
}));

vi.mock("@/services/api", () => ({
    api: { post, put },
}));

describe("Patient onboarding page", () => {
    beforeEach(() => {
        replace.mockReset();
        dispatch.mockReset();
        post.mockReset();
        put.mockReset();
    });

    it("surfaces join-clinic errors and lets the user continue", async () => {
        put.mockResolvedValue({});
        post.mockRejectedValue(new Error("Invalid or expired invite code"));

        render(<OnboardingPage />);
        fireEvent.click(screen.getByRole("button", { name: /next/i }));
        fireEvent.click(screen.getByRole("button", { name: /next/i }));
        fireEvent.click(screen.getByRole("button", { name: /next/i }));
        fireEvent.change(screen.getByLabelText(/clinic invite code/i), {
            target: { value: "BAD-CODE" },
        });
        fireEvent.click(screen.getByRole("button", { name: /finish setup/i }));

        expect(await screen.findByText(/invalid or expired invite code/i)).toBeInTheDocument();

        fireEvent.click(screen.getByRole("button", { name: /skip clinic for now/i }));

        await waitFor(() => {
            expect(replace).toHaveBeenCalledWith("/today");
        });
    });
});
