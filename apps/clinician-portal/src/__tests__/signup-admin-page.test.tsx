import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClinicAdminSignupPage from "@/app/(auth)/signup/admin/page";

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

describe("Clinic admin signup page", () => {
    beforeEach(() => {
        replace.mockReset();
        dispatch.mockReset();
        post.mockReset();
        writeStoredSession.mockReset();
    });

    it("creates clinic admin account and navigates to dashboard", async () => {
        post.mockResolvedValueOnce({
            tokens: {
                access_token: "access-token",
                expires_at: 1234567890,
                refresh_token: "refresh-token",
            },
            user: {
                email: "admin@example.com",
                id: "clinician-admin-1",
                role: "clinician",
            },
        });

        render(<ClinicAdminSignupPage />);

        fireEvent.change(screen.getByLabelText(/clinic name/i), { target: { value: "City Health" } });
        fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: "Amina" } });
        fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: "Khan" } });
        fireEvent.change(screen.getByLabelText(/^email$/i), { target: { value: "admin@example.com" } });
        fireEvent.change(screen.getByLabelText(/^specialty$/i), { target: { value: "Primary Care" } });
        fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "SecurePass123!" } });
        fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "SecurePass123!" } });
        fireEvent.click(screen.getByRole("button", { name: /create clinic admin account/i }));

        await waitFor(() => {
            expect(post).toHaveBeenCalledWith(
                "/api/v1/auth/signup/clinic-admin",
                expect.objectContaining({
                    clinic_name: "City Health",
                    email: "admin@example.com",
                    first_name: "Amina",
                    last_name: "Khan",
                }),
            );
        });

        expect(writeStoredSession).toHaveBeenCalledWith(
            expect.objectContaining({
                user: expect.objectContaining({ email: "admin@example.com", role: "clinician" }),
            }),
        );
        expect(replace).toHaveBeenCalledWith("/dashboard");
    });

    it("shows existing-clinic guidance when clinic is already provisioned", async () => {
        post.mockRejectedValueOnce(new Error("Clinic already exists"));

        render(<ClinicAdminSignupPage />);

        fireEvent.change(screen.getByLabelText(/clinic name/i), { target: { value: "City Health" } });
        fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: "Amina" } });
        fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: "Khan" } });
        fireEvent.change(screen.getByLabelText(/^email$/i), { target: { value: "admin@example.com" } });
        fireEvent.change(screen.getByLabelText(/^specialty$/i), { target: { value: "Primary Care" } });
        fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "SecurePass123!" } });
        fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "SecurePass123!" } });
        fireEvent.click(screen.getByRole("button", { name: /create clinic admin account/i }));

        expect(await screen.findByText(/clinic already exists/i)).toBeInTheDocument();
        expect(await screen.findByText(/this clinic is already provisioned/i)).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /go to clinician sign in/i })).toBeInTheDocument();
        expect(replace).not.toHaveBeenCalled();
    });
});
