import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import MFASetupPage from "../app/(dashboard)/settings/mfa/page";
import { api } from "@/services/api";

const { dispatch, writeStoredSession } = vi.hoisted(() => ({
    dispatch: vi.fn(),
    writeStoredSession: vi.fn(),
}));

// Mock Next router
vi.mock("next/navigation", () => ({
    useRouter: () => ({
        push: vi.fn(),
        replace: vi.fn(),
    }),
}));

// Mock Redux hooks
vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
    useSelector: vi.fn((selector) =>
        selector({
            auth: {
                accessToken: "fake-jwt-token",
                refreshToken: "fake-refresh-token",
                user: {
                    email: "doctor@example.com",
                    id: "clinician-1",
                    role: "clinician",
                },
            },
        }),
    ),
}));

// Mock API client
vi.mock("@/services/api", () => ({
    api: {
        get: vi.fn(),
        post: vi.fn(),
    },
}));

vi.mock("@/services/auth-session", () => ({
    writeStoredSession,
}));

describe("MFA Setup Page", () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it("initially shows loading state while checking factors", () => {
        // Setup mock to never resolve immediately 
        vi.mocked(api.get).mockImplementation(() => new Promise(() => {}));
        
        render(<MFASetupPage />);
        expect(screen.getByText("Checking MFA status...")).toBeInTheDocument();
    });

    it("shows already enrolled state if user has verified factors", async () => {
        vi.mocked(api.get).mockResolvedValue({
            factors: [
                { id: "factor-1", friendly_name: "My Phone", status: "verified", created_at: "2026-01-01" },
            ]
        });

        render(<MFASetupPage />);

        // Wait for the loading to finish
        await waitFor(() => {
            expect(screen.getByText("MFA is enabled")).toBeInTheDocument();
        });

        expect(screen.getByText("My Phone")).toBeInTheDocument();
        expect(screen.getByText("Remove")).toBeInTheDocument();
    });

    it("shows enroll state if user has no verified factors", async () => {
        vi.mocked(api.get).mockResolvedValue({ factors: [] });

        render(<MFASetupPage />);

        await waitFor(() => {
            expect(screen.getByText("Set up authenticator")).toBeInTheDocument();
        });

        const setupBtn = screen.getByRole("button", { name: "Begin setup" });
        expect(setupBtn).toBeInTheDocument();
    });

    it("stores upgraded tokens after successful verification", async () => {
        vi.mocked(api.get).mockResolvedValue({ factors: [] });
        vi.mocked(api.post)
            .mockResolvedValueOnce({
                factor_id: "factor-1",
                friendly_name: "Authenticator",
                totp: {
                    qr_code: "data:image/png;base64,abc",
                    secret: "secret",
                    uri: "otpauth://totp/test",
                },
            })
            .mockResolvedValueOnce({
                access_token: "aal2-access",
                expires_at: 2234567890,
                refresh_token: "aal2-refresh",
                token_type: "bearer",
            });

        render(<MFASetupPage />);

        await waitFor(() => {
            expect(screen.getByText("Set up authenticator")).toBeInTheDocument();
        });

        fireEvent.click(screen.getByRole("button", { name: "Begin setup" }));

        await waitFor(() => {
            expect(screen.getByText("Scan QR code")).toBeInTheDocument();
        });

        fireEvent.change(screen.getByLabelText(/6-digit code/i), {
            target: { value: "123456" },
        });
        fireEvent.click(screen.getByRole("button", { name: /verify and enable/i }));

        await waitFor(() => {
            expect(writeStoredSession).toHaveBeenCalledWith({
                accessToken: "aal2-access",
                expiresAt: 2234567890,
                refreshToken: "aal2-refresh",
                user: {
                    email: "doctor@example.com",
                    id: "clinician-1",
                    role: "clinician",
                },
            });
        });
        expect(dispatch).toHaveBeenCalled();
    });
});
