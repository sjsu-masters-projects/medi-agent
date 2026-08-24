import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const { dispatch, get, post, replace, writeStoredSession, setSearchParams, getSearchParams } = vi.hoisted(() => {
    let searchParamsString = "";
    return {
        dispatch: vi.fn(),
        get: vi.fn(),
        post: vi.fn(),
        replace: vi.fn(),
        writeStoredSession: vi.fn(),
        setSearchParams: (value: string) => {
            searchParamsString = value;
        },
        getSearchParams: () => new URLSearchParams(searchParamsString),
    };
});

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
    useSearchParams: () => getSearchParams(),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
}));

vi.mock("@/services/api", () => ({
    api: { get, post },
}));

vi.mock("@/services/auth-session", () => ({
    writeStoredSession,
}));

import LoginPage from "@/app/login/page";

describe("Patient login page", () => {
    beforeEach(() => {
        replace.mockReset();
        dispatch.mockReset();
        get.mockReset();
        post.mockReset();
        writeStoredSession.mockReset();
        setSearchParams("");
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
        get.mockResolvedValue([{ id: "team-1" }]);

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

    it("redirects to safe return_path after successful login when care team exists", async () => {
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
        get.mockResolvedValue([{ id: "team-1" }]);

        setSearchParams("return_path=%2Ftoday%3Ftab%3Dfeed");

        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText(/email address/i), {
            target: { value: "patient@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        await waitFor(() => {
            expect(replace).toHaveBeenCalledWith("/today?tab=feed");
        });
    });

    it("redirects patients with no linked care team to profile join flow", async () => {
        post.mockResolvedValue({
            tokens: {
                access_token: "access-token",
                expires_at: 1234567890,
                refresh_token: "refresh-token",
            },
            user: {
                email: "newpatient@example.com",
                id: "patient-2",
                role: "patient",
            },
        });
        get.mockResolvedValue([]);

        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText(/email address/i), {
            target: { value: "newpatient@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        await waitFor(() => {
            expect(replace).toHaveBeenCalledWith("/profile?joinClinic=1");
        });
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

    it("toggles password visibility while typing", async () => {
        render(<LoginPage />);

        const passwordInput = screen.getByLabelText(/^password$/i);
        fireEvent.change(passwordInput, {
            target: { value: "SecurePass123!" },
        });

        expect(passwordInput).toHaveAttribute("type", "password");

        fireEvent.click(screen.getByRole("button", { name: /show password/i }));
        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "text");

        fireEvent.click(screen.getByRole("button", { name: /hide password/i }));
        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password");
    });

    it("declares login autofill semantics", () => {
        render(<LoginPage />);

        expect(screen.getByLabelText(/email address/i)).toHaveAttribute("autocomplete", "email");
        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute(
            "autocomplete",
            "current-password"
        );
    });
});
