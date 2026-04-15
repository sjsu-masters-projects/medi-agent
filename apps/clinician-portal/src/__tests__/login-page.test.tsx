import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClinicianLoginPage from "@/app/(auth)/login/page";

const { dispatch, post, replace, writeStoredSession } = vi.hoisted(() => ({
    dispatch: vi.fn(),
    post: vi.fn(),
    replace: vi.fn(),
    writeStoredSession: vi.fn(),
}));

const { clearStoredClinicContext, readStoredClinicContext, writeStoredClinicContext } = vi.hoisted(
    () => ({
        clearStoredClinicContext: vi.fn(),
        readStoredClinicContext: vi.fn(),
        writeStoredClinicContext: vi.fn(),
    }),
);

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

vi.mock("@/services/clinic-context", () => ({
    clearStoredClinicContext,
    readStoredClinicContext,
    writeStoredClinicContext,
}));

describe("Clinician login page", () => {
    beforeEach(() => {
        replace.mockReset();
        dispatch.mockReset();
        post.mockReset();
        writeStoredSession.mockReset();
        clearStoredClinicContext.mockReset();
        readStoredClinicContext.mockReset();
        writeStoredClinicContext.mockReset();
        readStoredClinicContext.mockReturnValue(null);
    });

    it("rejects patient credentials on the clinician portal", async () => {
        post.mockResolvedValueOnce({
            clinic_code: "ABC123",
            clinic_id: "clinic-1",
            clinic_name: "City Health",
            status: "active",
        });
        post.mockResolvedValueOnce({
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

        fireEvent.change(screen.getByLabelText(/clinic code/i), {
            target: { value: "abc123" },
        });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));

        fireEvent.click(await screen.findByRole("button", { name: /already have an account/i }));

        fireEvent.change(screen.getByLabelText(/email/i), {
            target: { value: "patient@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        expect(await screen.findByText(/patient account/i)).toBeInTheDocument();
        expect(writeStoredClinicContext).toHaveBeenCalledWith(
            expect.objectContaining({ clinicCode: "ABC123", clinicName: "City Health" }),
        );
        expect(replace).not.toHaveBeenCalled();
    });

    it("shows a field error when clinic code is too short", async () => {
        render(<ClinicianLoginPage />);

        fireEvent.change(screen.getByLabelText(/clinic code/i), {
            target: { value: "78008" },
        });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));

        expect(await screen.findByText(/clinic code should have at least 6 characters/i)).toBeInTheDocument();
        expect(post).not.toHaveBeenCalled();
    });

    it("shows mapped backend validation errors for clinic code", async () => {
        post.mockRejectedValueOnce(new Error("Clinic code should have at least 6 characters"));

        render(<ClinicianLoginPage />);

        fireEvent.change(screen.getByLabelText(/clinic code/i), {
            target: { value: "abc123" },
        });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));

        expect(await screen.findByText(/clinic code should have at least 6 characters/i)).toBeInTheDocument();
    });
});
