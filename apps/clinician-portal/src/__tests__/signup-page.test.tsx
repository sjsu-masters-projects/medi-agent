import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { dispatch, post, replace, writeStoredSession, setSearchParams, getSearchParams } =
    vi.hoisted(() => {
        let searchParamsString = "";
        return {
            dispatch: vi.fn(),
            post: vi.fn(),
            replace: vi.fn(),
            writeStoredSession: vi.fn(),
            setSearchParams: (value: string) => {
                searchParamsString = value;
            },
            getSearchParams: () => new URLSearchParams(searchParamsString),
        };
    });

const { readStoredClinicContext, writeStoredClinicContext } = vi.hoisted(() => ({
    readStoredClinicContext: vi.fn(),
    writeStoredClinicContext: vi.fn(),
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
    useSearchParams: () => getSearchParams(),
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
    readStoredClinicContext,
    writeStoredClinicContext,
}));

import ClinicianSignupPage from "@/app/(auth)/signup/page";

describe("Clinician signup page", () => {
    beforeEach(() => {
        replace.mockReset();
        dispatch.mockReset();
        post.mockReset();
        writeStoredSession.mockReset();
        readStoredClinicContext.mockReset();
        writeStoredClinicContext.mockReset();
        setSearchParams("");
        readStoredClinicContext.mockReturnValue({
            clinicCode: "ABC123",
            clinicId: "clinic-1",
            clinicName: "City Health",
            status: "active",
        });
    });

    it("stores the full session and routes to the dashboard", async () => {
        post.mockResolvedValueOnce({
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

        render(<ClinicianSignupPage />);
        fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: "Amina" } });
        fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: "Khan" } });
        fireEvent.change(screen.getByLabelText(/^email$/i), { target: { value: "doctor@example.com" } });
        fireEvent.change(screen.getByLabelText(/^specialty$/i), { target: { value: "Primary Care" } });
        fireEvent.change(screen.getByLabelText(/role access/i), { target: { value: "nurse" } });
        fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "SecurePass123!" } });
        fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "SecurePass123!" } });
        fireEvent.click(screen.getByRole("button", { name: /create clinician account/i }));

        await waitFor(() => {
            expect(writeStoredSession).toHaveBeenCalledWith({
                accessToken: "access-token",
                expiresAt: 1234567890,
                refreshToken: "refresh-token",
                user: {
                    email: "doctor@example.com",
                    id: "clinician-1",
                    role: "clinician",
                },
            });
        });
        expect(post).toHaveBeenNthCalledWith(
            1,
            "/api/v1/auth/signup/clinician",
            expect.objectContaining({ clinic_code: "ABC123", role: "nurse" }),
        );
        expect(replace).toHaveBeenCalledWith("/dashboard");
    });

    it("hydrates invite params and signs up admin invitees", async () => {
        readStoredClinicContext.mockReturnValue(null);
        setSearchParams("email=admin%40example.com&role=admin&code=ABC123");

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
                email: "admin@example.com",
                id: "clinician-admin-1",
                role: "clinician",
            },
        });

        render(<ClinicianSignupPage />);

        await waitFor(() => {
            expect(writeStoredClinicContext).toHaveBeenCalledWith({
                clinicCode: "ABC123",
                clinicId: "clinic-1",
                clinicName: "City Health",
                status: "active",
            });
        });

        expect(screen.getByLabelText(/^email$/i)).toHaveValue("admin@example.com");
        expect(screen.getByLabelText(/role access/i)).toHaveValue("admin");
        expect(screen.getByLabelText(/role access/i)).toBeDisabled();

        fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: "Amina" } });
        fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: "Khan" } });
        fireEvent.change(screen.getByLabelText(/^specialty$/i), { target: { value: "Primary Care" } });
        fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "SecurePass123!" } });
        fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "SecurePass123!" } });
        fireEvent.click(screen.getByRole("button", { name: /create clinician account/i }));

        await waitFor(() => {
            expect(post).toHaveBeenCalledWith(
                "/api/v1/auth/signup/clinician",
                expect.objectContaining({ clinic_code: "ABC123", role: "admin" }),
            );
        });
    });
});
