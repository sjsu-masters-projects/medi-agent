import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ClinicianLoginPage from "@/app/(auth)/login/page";

const { ApiClientError, dispatch, get, post, replace, writeStoredSession, isRetryableApiError } = vi.hoisted(() => ({
    ApiClientError: class ApiClientError extends Error {
        readonly details: unknown;
        readonly status: number;

        constructor(message: string, status: number, details: unknown) {
            super(message);
            this.details = details;
            this.status = status;
        }
    },
    dispatch: vi.fn(),
    get: vi.fn(),
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
    useSearchParams: () => new URLSearchParams(""),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
}));

vi.mock("@/services/api", () => ({
    ApiClientError,
    api: { get, post },
    isRetryableApiError,
}));

vi.mock("@/services/auth-session", () => ({
    consumeSignOutReason: () => null,
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
        get.mockReset();
        get.mockRejectedValue(new Error("clinic list unavailable"));
        writeStoredSession.mockReset();
        isRetryableApiError.mockReset();
        isRetryableApiError.mockReturnValue(false);
        clearStoredClinicContext.mockReset();
        readStoredClinicContext.mockReset();
        writeStoredClinicContext.mockReset();
        readStoredClinicContext.mockReturnValue(null);
    });

    const CLINICIAN_LOGIN = {
        tokens: {
            access_token: "access-token",
            expires_at: 1234567890,
            refresh_token: "refresh-token",
        },
        user: { email: "doctor@example.com", id: "clinician-1", role: "clinician" },
    };

    const MFA_LOGIN = {
        ...CLINICIAN_LOGIN,
        tokens: {
            access_token: "aal1-access-token",
            expires_at: 1234567890,
            refresh_token: "aal1-refresh-token",
        },
        mfa_factors: [{ id: "factor-1", friendly_name: "Clinic Authenticator" }],
        mfa_required: true,
    };

    const RESOLVED_CLINIC = {
        clinic_code: "ABC123",
        clinic_id: "clinic-1",
        clinic_name: "City Health",
        status: "active",
    };

    function signInWith(email: string, password: string, button = /^sign in$/i) {
        fireEvent.change(screen.getByLabelText(/email/i), { target: { value: email } });
        fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: password } });
        fireEvent.click(screen.getByRole("button", { name: button }));
    }

    async function openAddClinicSignIn() {
        fireEvent.click(await screen.findByRole("button", { name: /join a clinic/i }));
        fireEvent.change(await screen.findByLabelText(/clinic code/i), {
            target: { value: "abc123" },
        });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));
        fireEvent.click(await screen.findByRole("button", { name: /already have an account/i }));
    }

    it("opens on sign in with no clinic code", async () => {
        render(<ClinicianLoginPage />);

        expect(await screen.findByRole("heading", { name: /^sign in$/i })).toBeInTheDocument();
        expect(screen.getByLabelText(/email/i)).toHaveAttribute("autocomplete", "email");
        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("autocomplete", "current-password");
        expect(screen.queryByLabelText(/clinic code/i)).not.toBeInTheDocument();
        expect(screen.getByRole("button", { name: /join a clinic/i })).toBeInTheDocument();
    });

    it("signs in with email and password only and lands on the dashboard", async () => {
        post.mockResolvedValueOnce(CLINICIAN_LOGIN);

        render(<ClinicianLoginPage />);
        signInWith("doctor@example.com", "SecurePass123!");

        await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
        expect(post).toHaveBeenCalledTimes(1);
        expect(post).toHaveBeenCalledWith("/api/v1/auth/login", {
            email: "doctor@example.com",
            password: "SecurePass123!",
        });
        expect(writeStoredSession).toHaveBeenCalled();
        // No clinic chooser step: nothing between sign-in and the dashboard.
        expect(screen.queryByText(/choose a clinic/i)).not.toBeInTheDocument();
    });

    it("rejects patient credentials on the clinician portal", async () => {
        post.mockResolvedValueOnce({
            ...CLINICIAN_LOGIN,
            user: { email: "patient@example.com", id: "patient-1", role: "patient" },
        });

        render(<ClinicianLoginPage />);
        signInWith("patient@example.com", "SecurePass123!");

        expect(await screen.findByText(/registered as a patient/i)).toBeInTheDocument();
        expect(writeStoredSession).not.toHaveBeenCalled();
        expect(replace).not.toHaveBeenCalled();
    });

    it("keeps the user on the sign-in form for invalid credentials", async () => {
        post.mockRejectedValueOnce(
            new ApiClientError("Invalid email or password", 401, {
                error: { code: "AUTHENTICATION_ERROR", message: "Invalid email or password" },
            }),
        );

        render(<ClinicianLoginPage />);
        signInWith("doctor@example.com", "wrong-password");

        expect(await screen.findByText(/invalid email or password/i)).toBeInTheDocument();
        expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
        expect(screen.getByLabelText(/^password$/i)).toHaveValue("wrong-password");
        expect(replace).not.toHaveBeenCalled();
    });

    it("explains an account with no active clinic", async () => {
        post.mockRejectedValueOnce(
            new ApiClientError("Your account is not active at any clinic.", 401, {
                error: { code: "NO_ACTIVE_CLINIC" },
            }),
        );

        render(<ClinicianLoginPage />);
        signInWith("doctor@example.com", "SecurePass123!");

        expect(await screen.findByText(/not active at any clinic\. ask a clinic admin to invite you/i)).toBeInTheDocument();
        expect(replace).not.toHaveBeenCalled();
    });

    it("prompts for MFA when the login response requires it", async () => {
        post.mockResolvedValueOnce(MFA_LOGIN);

        render(<ClinicianLoginPage />);
        signInWith("doctor@example.com", "SecurePass123!");

        expect(await screen.findByText(/verify mfa/i)).toBeInTheDocument();
        expect(screen.getAllByText(/clinic authenticator/i).length).toBeGreaterThan(0);
        expect(screen.getByLabelText(/6-digit code/i)).toBeInTheDocument();
        expect(writeStoredSession).not.toHaveBeenCalled();
        expect(replace).not.toHaveBeenCalled();
    });

    it("verifies MFA code and completes login", async () => {
        post.mockResolvedValueOnce(MFA_LOGIN);
        post.mockResolvedValueOnce({
            access_token: "aal2-access-token",
            expires_at: 2234567890,
            refresh_token: "aal2-refresh-token",
            token_type: "bearer",
        });

        render(<ClinicianLoginPage />);
        signInWith("doctor@example.com", "SecurePass123!");
        await screen.findByText(/verify mfa/i);

        fireEvent.change(screen.getByLabelText(/6-digit code/i), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: /verify and continue/i }));

        expect(post).toHaveBeenNthCalledWith(
            2,
            "/api/v1/auth/mfa/verify",
            { code: "123456", factor_id: "factor-1" },
            {
                headers: { "X-Refresh-Token": "aal1-refresh-token" },
                token: "aal1-access-token",
            },
        );

        await waitFor(() => {
            expect(writeStoredSession).toHaveBeenCalledWith({
                accessToken: "aal2-access-token",
                expiresAt: 2234567890,
                refreshToken: "aal2-refresh-token",
                user: { email: "doctor@example.com", id: "clinician-1", role: "clinician" },
            }, { signIn: true });
            expect(replace).toHaveBeenCalledWith("/dashboard");
        });
    });

    it("shows the sidebar clinic name only for a single clinic", async () => {
        post.mockResolvedValueOnce(CLINICIAN_LOGIN);
        get.mockReset();
        get.mockResolvedValueOnce({
            default_clinic_id: "clinic-1",
            clinics: [
                { clinic_code: "ABC123", clinic_id: "clinic-1", clinic_name: "City Health", role: "provider", status: "active" },
            ],
        });

        render(<ClinicianLoginPage />);
        signInWith("doctor@example.com", "SecurePass123!");

        await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
        expect(writeStoredClinicContext).toHaveBeenCalledWith({
            clinicCode: "ABC123",
            clinicId: "clinic-1",
            clinicName: "City Health",
            status: "active",
        });
    });

    it("keeps no single clinic in the sidebar when the account has several", async () => {
        post.mockResolvedValueOnce(CLINICIAN_LOGIN);
        get.mockReset();
        get.mockResolvedValueOnce({
            default_clinic_id: "clinic-1",
            clinics: [
                { clinic_code: "ABC123", clinic_id: "clinic-1", clinic_name: "City Health", role: "provider", status: "active" },
                { clinic_code: "XYZ789", clinic_id: "clinic-2", clinic_name: "Bay Clinic", role: "admin", status: "active" },
            ],
        });

        render(<ClinicianLoginPage />);
        signInWith("doctor@example.com", "SecurePass123!");

        await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
        expect(writeStoredClinicContext).not.toHaveBeenCalled();
        expect(clearStoredClinicContext).toHaveBeenCalled();
    });

    it("shows a field error when the clinic code is too short", async () => {
        render(<ClinicianLoginPage />);
        fireEvent.click(await screen.findByRole("button", { name: /join a clinic/i }));

        fireEvent.change(await screen.findByLabelText(/clinic code/i), { target: { value: "78008" } });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));

        expect(
            await screen.findByText(/clinic code should have at least 6 characters/i),
        ).toBeInTheDocument();
        expect(post).not.toHaveBeenCalled();
    });

    it("shows mapped backend validation errors for the clinic code", async () => {
        post.mockRejectedValueOnce(new Error("Clinic code should have at least 6 characters"));

        render(<ClinicianLoginPage />);
        fireEvent.click(await screen.findByRole("button", { name: /join a clinic/i }));
        fireEvent.change(await screen.findByLabelText(/clinic code/i), { target: { value: "abc123" } });
        fireEvent.click(screen.getByRole("button", { name: /verify clinic code/i }));

        expect(
            await screen.findByText(/clinic code should have at least 6 characters/i),
        ).toBeInTheDocument();
    });

    it("adds a clinic to an existing account: signs in, then joins by code", async () => {
        post.mockResolvedValueOnce(RESOLVED_CLINIC);
        post.mockResolvedValueOnce(CLINICIAN_LOGIN);
        post.mockResolvedValueOnce({
            status: "joined",
            clinic_code: "ABC123",
            clinic_id: "clinic-1",
            clinic_name: "City Health",
            clinic_status: "active",
            role: "nurse",
        });

        render(<ClinicianLoginPage />);
        await openAddClinicSignIn();
        expect(screen.getByText(/adding clinic:/i)).toHaveTextContent("City Health");
        fireEvent.change(screen.getByLabelText(/your role at this clinic/i), { target: { value: "nurse" } });
        signInWith("doctor@example.com", "SecurePass123!", /sign in and add clinic/i);

        await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
        expect(post).toHaveBeenNthCalledWith(2, "/api/v1/auth/login", {
            email: "doctor@example.com",
            password: "SecurePass123!",
        });
        expect(post).toHaveBeenNthCalledWith(
            3,
            "/api/v1/clinicians/me/clinics",
            { clinic_code: "ABC123", role: "nurse" },
            { token: "access-token" },
        );
        expect(writeStoredSession).toHaveBeenCalled();
    });

    it("adds a clinic only after the second factor", async () => {
        post.mockResolvedValueOnce(RESOLVED_CLINIC);
        post.mockResolvedValueOnce(MFA_LOGIN);
        post.mockResolvedValueOnce({
            access_token: "aal2-access-token",
            expires_at: 2234567890,
            refresh_token: "aal2-refresh-token",
        });
        post.mockResolvedValueOnce({
            status: "joined",
            clinic_code: "ABC123",
            clinic_id: "clinic-1",
            clinic_name: "City Health",
            clinic_status: "active",
            role: "provider",
        });

        render(<ClinicianLoginPage />);
        await openAddClinicSignIn();
        signInWith("doctor@example.com", "SecurePass123!", /sign in and add clinic/i);
        await screen.findByText(/verify mfa/i);
        // The clinic is not added before the code is verified.
        expect(post).toHaveBeenCalledTimes(2);

        fireEvent.change(screen.getByLabelText(/6-digit code/i), { target: { value: "123456" } });
        fireEvent.click(screen.getByRole("button", { name: /verify and continue/i }));

        await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
        expect(post).toHaveBeenNthCalledWith(
            4,
            "/api/v1/clinicians/me/clinics",
            { clinic_code: "ABC123", role: "provider" },
            { token: "aal2-access-token" },
        );
    });

    it("says what to do when the clinic admin ended the membership", async () => {
        post.mockResolvedValueOnce(RESOLVED_CLINIC);
        post.mockResolvedValueOnce(CLINICIAN_LOGIN);
        post.mockRejectedValueOnce(
            new ApiClientError("Your membership at this clinic was ended.", 403, {
                error: { code: "MEMBERSHIP_INACTIVE" },
            }),
        );

        render(<ClinicianLoginPage />);
        await openAddClinicSignIn();
        signInWith("doctor@example.com", "SecurePass123!", /sign in and add clinic/i);

        expect(
            await screen.findByText(/ask that clinic's admin to invite you again/i),
        ).toBeInTheDocument();
        expect(replace).not.toHaveBeenCalled();
        expect(writeStoredSession).not.toHaveBeenCalled();

        fireEvent.click(screen.getByRole("button", { name: /continue to my dashboard/i }));
        await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
        expect(writeStoredSession).toHaveBeenCalled();
    });

    it("goes back to plain sign in from the clinic code path", async () => {
        render(<ClinicianLoginPage />);
        fireEvent.click(await screen.findByRole("button", { name: /join a clinic/i }));
        fireEvent.click(await screen.findByRole("button", { name: /back to sign in/i }));

        expect(await screen.findByRole("heading", { name: /^sign in$/i })).toBeInTheDocument();
        expect(screen.queryByLabelText(/clinic code/i)).not.toBeInTheDocument();
    });

    it("toggles password visibility while typing", async () => {
        render(<ClinicianLoginPage />);

        const passwordInput = await screen.findByLabelText(/^password$/i);
        fireEvent.change(passwordInput, { target: { value: "SecurePass123!" } });
        expect(passwordInput).toHaveAttribute("type", "password");

        fireEvent.click(screen.getByRole("button", { name: /show password/i }));
        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "text");

        fireEvent.click(screen.getByRole("button", { name: /hide password/i }));
        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password");
    });
});
