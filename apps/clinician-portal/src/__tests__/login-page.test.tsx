import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClinicianLoginPage from "@/app/(auth)/login/page";

const { dispatch, post, replace, writeStoredSession } = vi.hoisted(() => ({
    dispatch: vi.fn(),
    post: vi.fn(),
    replace: vi.fn(),
    writeStoredSession: vi.fn(),
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
}));

vi.mock("@/services/api", () => ({
    api: { post },
}));

vi.mock("@/services/auth-session", () => ({
    writeStoredSession,
}));

describe("Clinician login page", () => {
    beforeEach(() => {
        replace.mockReset();
        dispatch.mockReset();
        post.mockReset();
        writeStoredSession.mockReset();
    });

    it("rejects patient credentials on the clinician portal", async () => {
        post.mockResolvedValue({
            tokens: {
                access_token: "access-token",
                expires_at: 1234567890,
                refresh_token: "refresh-token",
            },
            user: {
                email: "patient@example.com",
                id: "patient-1",
                role: "patient",
            },
        });

        render(<ClinicianLoginPage />);
        fireEvent.change(screen.getByLabelText(/email/i), {
            target: { value: "patient@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        expect(await screen.findByText(/patient account/i)).toBeInTheDocument();
        expect(replace).not.toHaveBeenCalled();
    });
});
