import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import MFASetupPage from "../app/(dashboard)/settings/mfa/page";
import { api } from "@/services/api";

// Mock Next router
vi.mock("next/navigation", () => ({
    useRouter: () => ({
        push: vi.fn(),
        replace: vi.fn(),
    }),
}));

// Mock Redux hooks
vi.mock("react-redux", () => ({
    useSelector: vi.fn(() => "fake-jwt-token"), // Mock token from state.auth.token
}));

// Mock API client
vi.mock("@/services/api", () => ({
    api: {
        get: vi.fn(),
        post: vi.fn(),
    },
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
});
