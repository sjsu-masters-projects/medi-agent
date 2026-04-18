import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClinicianLoginPage from "@/app/(auth)/login/page";

const { dispatch, post, replace, writeStoredSession, isRetryableApiError } = vi.hoisted(() => ({
    dispatch: vi.fn(),
    post: vi.fn(),
    replace: vi.fn(),
    isRetryableApiError: vi.fn(() => false),
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
    isRetryableApiError,
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
        isRetryableApiError.mockReset();
        isRetryableApiError.mockReturnValue(false);
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

        fireEvent.change(await screen.findByLabelText(/clinic code/i), {
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

        expect(post).toHaveBeenNthCalledWith(2, "/api/v1/auth/login", {
            clinic_code: "ABC123",
            email: "patient@example.com",
            password: "SecurePass123!",
        });
        expect(await screen.findByText(/patient account/i)).toBeInTheDocument();
        expect(writeStoredClinicContext).toHaveBeenCalledWith(
            expect.objectContaining({ clinicCode: "ABC123", clinicName: "City Health" }),
        );
        expect(replace).not.toHaveBeenCalled();
    });

    it("shows a field error when clinic code is too short", async () => {
        render(<ClinicianLoginPage />);

        fireEvent.change(await screen.findByLabelText(/clinic code/i), {
            target: { value: "78008" },
        });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));

        expect(
            await screen.findByText(/clinic code should have at least 6 characters/i),
        ).toBeInTheDocument();
        expect(post).not.toHaveBeenCalled();
    });

    it("shows mapped backend validation errors for clinic code", async () => {
        post.mockRejectedValueOnce(new Error("Clinic code should have at least 6 characters"));

        render(<ClinicianLoginPage />);

        fireEvent.change(await screen.findByLabelText(/clinic code/i), {
            target: { value: "abc123" },
        });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));

        expect(
            await screen.findByText(/clinic code should have at least 6 characters/i),
        ).toBeInTheDocument();
    });

    it("prompts for MFA when the login response requires it", async () => {
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
            mfa_factors: [{ id: "factor-1", friendly_name: "Clinic Authenticator" }],
            mfa_required: true,
            user: {
                email: "doctor@example.com",
                id: "clinician-1",
                role: "clinician",
            },
        });

        render(<ClinicianLoginPage />);

        fireEvent.change(await screen.findByLabelText(/clinic code/i), {
            target: { value: "abc123" },
        });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));
        fireEvent.click(await screen.findByRole("button", { name: /already have an account/i }));

        fireEvent.change(screen.getByLabelText(/email/i), {
            target: { value: "doctor@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        expect(post).toHaveBeenNthCalledWith(2, "/api/v1/auth/login", {
            clinic_code: "ABC123",
            email: "doctor@example.com",
            password: "SecurePass123!",
        });
        expect(await screen.findByText(/verify mfa/i)).toBeInTheDocument();
        expect(screen.getByText(/clinic authenticator/i)).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /open mfa settings/i })).toHaveAttribute(
            "href",
            "/settings/mfa",
        );
        expect(writeStoredSession).not.toHaveBeenCalled();
        expect(replace).not.toHaveBeenCalled();
    });

    it("revalidates saved clinic context before trusting it", async () => {
        readStoredClinicContext.mockReturnValue({
            clinicCode: "ABC123",
            clinicId: "clinic-1",
            clinicName: "Old Name",
            status: "active",
        });
        post.mockResolvedValueOnce({
            clinic_code: "ABC123",
            clinic_id: "clinic-1",
            clinic_name: "City Health",
            status: "active",
        });

        render(<ClinicianLoginPage />);

        expect(await screen.findByText(/clinic verified: city health/i)).toBeInTheDocument();
        expect(post).toHaveBeenCalledWith("/api/v1/clinics/resolve-code", {
            clinic_code: "ABC123",
        });
        expect(writeStoredClinicContext).toHaveBeenCalledWith({
            clinicCode: "ABC123",
            clinicId: "clinic-1",
            clinicName: "City Health",
            status: "active",
        });
    });

    it("drops stale saved clinic context and forces re-verification", async () => {
        readStoredClinicContext.mockReturnValue({
            clinicCode: "ABC123",
            clinicId: "clinic-1",
            clinicName: "City Health",
            status: "active",
        });
        post.mockRejectedValueOnce(new Error("Clinic code is invalid"));

        render(<ClinicianLoginPage />);

        expect(await screen.findByText(/saved clinic access expired/i)).toBeInTheDocument();
        expect(await screen.findByLabelText(/clinic code/i)).toHaveValue("ABC123");
        expect(clearStoredClinicContext).toHaveBeenCalled();
    });

    it("forces clinic re-verification when login rejects the saved clinic", async () => {
        post.mockResolvedValueOnce({
            clinic_code: "ABC123",
            clinic_id: "clinic-1",
            clinic_name: "City Health",
            status: "active",
        });
        post.mockRejectedValueOnce(new Error("Clinic code is invalid"));

        render(<ClinicianLoginPage />);

        fireEvent.change(await screen.findByLabelText(/clinic code/i), {
            target: { value: "abc123" },
        });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));
        fireEvent.click(await screen.findByRole("button", { name: /already have an account/i }));

        fireEvent.change(screen.getByLabelText(/email/i), {
            target: { value: "doctor@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        expect(await screen.findByText(/saved clinic access expired/i)).toBeInTheDocument();
        expect(await screen.findByLabelText(/clinic code/i)).toHaveValue("ABC123");
        await waitFor(() => {
            expect(clearStoredClinicContext).toHaveBeenCalled();
        });
    });
});
