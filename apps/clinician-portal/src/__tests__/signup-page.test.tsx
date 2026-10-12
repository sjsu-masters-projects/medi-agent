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
    useSelector: () => null,
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
        window.history.replaceState(null, "", "/signup");
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

    it("signs up from an addressed invitation and claims membership on the server", async () => {
        readStoredClinicContext.mockReturnValue(null);
        const invitation = "x".repeat(43);
        window.history.replaceState(null, "", `/signup#invitation=${invitation}`);

        post.mockResolvedValueOnce({ clinic_name: "City Health", email: "admin@example.com", role: "admin" });
        post.mockResolvedValueOnce({
            clinic: { clinic_code: "ABC123", clinic_id: "clinic-1", clinic_name: "City Health", status: "active" },
            invitation_status: "accepted",
            tokens: { access_token: "access-token", expires_at: 1234567890, refresh_token: "refresh-token" },
            user: { email: "admin@example.com", id: "clinician-admin-1", role: "clinician" },
        });

        render(<ClinicianSignupPage />);
        await screen.findByText("Invitation to join City Health");
        expect(window.location.hash).toBe("");
        expect(screen.getByLabelText(/^email$/i)).toHaveValue("admin@example.com");
        expect(screen.getByLabelText(/role access/i)).toHaveValue("admin");
        expect(screen.getByLabelText(/role access/i)).toBeDisabled();

        fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: "Amina" } });
        fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: "Khan" } });
        fireEvent.change(screen.getByLabelText(/^specialty$/i), { target: { value: "Primary Care" } });
        fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "SecurePass123!" } });
        fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "SecurePass123!" } });
        fireEvent.click(screen.getByRole("button", { name: /create clinician account/i }));

        await waitFor(() => expect(replace).toHaveBeenCalledWith("/dashboard"));
        const body = post.mock.calls[1][1] as Record<string, unknown>;
        expect(post.mock.calls[1][0]).toBe("/api/v1/auth/signup/clinician");
        expect(body.invitation_token).toBe(invitation);
        expect(body.clinic_code).toBeUndefined();
        expect(writeStoredClinicContext).toHaveBeenCalledWith({
            clinicCode: "ABC123", clinicId: "clinic-1", clinicName: "City Health", status: "active",
        });
        // No separate browser-side claim: the server already accepted.
        expect(post).toHaveBeenCalledTimes(2);
    });

    it("keeps a created account when the claim is still pending", async () => {
        readStoredClinicContext.mockReturnValue(null);
        window.history.replaceState(null, "", `/signup#invitation=${"y".repeat(43)}`);
        post.mockResolvedValueOnce({ clinic_name: "City Health", email: "nurse@example.com", role: "nurse" });
        post.mockResolvedValueOnce({
            invitation_status: "pending",
            tokens: { access_token: "access-token", expires_at: 1234567890, refresh_token: "refresh-token" },
            user: { email: "nurse@example.com", id: "clinician-2", role: "clinician" },
        });
        render(<ClinicianSignupPage />);
        await screen.findByText("Invitation to join City Health");
        fireEvent.change(screen.getByLabelText(/first name/i), { target: { value: "Ana" } });
        fireEvent.change(screen.getByLabelText(/last name/i), { target: { value: "Ruiz" } });
        fireEvent.change(screen.getByLabelText(/^specialty$/i), { target: { value: "Primary Care" } });
        fireEvent.change(screen.getByLabelText(/^password$/i), { target: { value: "SecurePass123!" } });
        fireEvent.change(screen.getByLabelText(/confirm password/i), { target: { value: "SecurePass123!" } });
        fireEvent.click(screen.getByRole("button", { name: /create clinician account/i }));
        expect(await screen.findByRole("alert")).toHaveTextContent(/account was created/);
        expect(writeStoredSession).toHaveBeenCalled();
        expect(replace).not.toHaveBeenCalled();
    });

    it("lets an existing account sign in to accept without a portal session", async () => {
        readStoredClinicContext.mockReturnValue(null);
        const invitation = "z".repeat(43);
        window.history.replaceState(null, "", `/signup#invitation=${invitation}`);
        post.mockResolvedValueOnce({ clinic_name: "City Health", email: "existing@example.com", role: "provider" });
        post.mockResolvedValueOnce({
            clinic: { clinic_code: "ABC123", clinic_id: "clinic-1", clinic_name: "City Health", status: "active" },
            status: "accepted",
        });
        render(<ClinicianSignupPage />);
        fireEvent.click(await screen.findByRole("button", { name: /sign in to accept/i }));
        fireEvent.change(screen.getByLabelText(/existing account password/i), { target: { value: "pw" } });
        fireEvent.click(screen.getByRole("button", { name: /^sign in to accept$/i }));
        await screen.findByText(/Invitation accepted/);
        expect(post).toHaveBeenLastCalledWith("/api/v1/auth/invitations/accept", {
            email: "existing@example.com", password: "pw", invitation_token: invitation,
        });
        expect(writeStoredSession).not.toHaveBeenCalled();
        expect(writeStoredClinicContext).toHaveBeenCalledWith(expect.objectContaining({ clinicCode: "ABC123" }));
        expect(screen.getByRole("link", { name: "Continue to sign in" })).toHaveAttribute("href", "/login");
    });

    it("ignores the legacy admin role query parameter", async () => {
        setSearchParams("role=admin");
        render(<ClinicianSignupPage />);
        expect(screen.getByLabelText(/role access/i)).toHaveValue("provider");
        expect(screen.getByLabelText(/role access/i)).not.toBeDisabled();
        expect(screen.queryByRole("option", { name: /clinic admin/i })).not.toBeInTheDocument();
    });
});
