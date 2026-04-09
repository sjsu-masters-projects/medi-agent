import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import LoginPage from "@/app/login/page";

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

describe("Patient login page", () => {
    beforeEach(() => {
        replace.mockReset();
        dispatch.mockReset();
        post.mockReset();
        writeStoredSession.mockReset();
    });

    it("stores full session and redirects on successful patient login", async () => {
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

        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText(/email address/i), {
            target: { value: "patient@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        await waitFor(() => {
            expect(writeStoredSession).toHaveBeenCalledWith({
                accessToken: "access-token",
                expiresAt: 1234567890,
                refreshToken: "refresh-token",
                user: {
                    email: "patient@example.com",
                    id: "patient-1",
                    role: "patient",
                },
            });
        });
        expect(replace).toHaveBeenCalledWith("/today");
    });

    it("shows an error for clinician credentials", async () => {
        post.mockResolvedValue({
            tokens: {
                access_token: "access-token",
                expires_at: 1234567890,
                refresh_token: "refresh-token",
            },
            user: {
                email: "doctor@example.com",
                id: "clinician-1",
                role: "clinician",
            },
        });

        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText(/email address/i), {
            target: { value: "doctor@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        expect(await screen.findByText(/clinician account/i)).toBeInTheDocument();
        expect(replace).not.toHaveBeenCalled();
    });
});
