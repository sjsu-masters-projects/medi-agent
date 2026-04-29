import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const {
    dispatch,
    redirectToLogin,
    refreshClinicianSession,
    setAuthState,
    useAuthState,
    writeStoredSession,
} = vi.hoisted(() => {
    let authState = {
        loading: false,
        isAuthenticated: true,
        refreshToken: "refresh-token",
        expiresAt: 1_777_481_000,
    };

    return {
        dispatch: vi.fn(),
        redirectToLogin: vi.fn(),
        refreshClinicianSession: vi.fn(),
        setAuthState: (nextState: Partial<typeof authState>) => {
            authState = { ...authState, ...nextState };
        },
        useAuthState: () => authState,
        writeStoredSession: vi.fn(),
    };
});

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
    useSelector: (selector: (state: unknown) => unknown) => selector({ auth: useAuthState() }),
}));

vi.mock("@/services/auth-refresh", () => ({
    refreshClinicianSession,
}));

vi.mock("@/services/auth-session", () => ({
    writeStoredSession,
}));

vi.mock("@/services/auth-redirect", () => ({
    redirectToLogin,
}));

import { useAuthSessionRefresh } from "@/hooks/use-auth-session-refresh";

function TestHarness() {
    useAuthSessionRefresh();
    return null;
}

describe("useAuthSessionRefresh (clinician portal)", () => {
    beforeEach(() => {
        setAuthState({
            loading: false,
            isAuthenticated: true,
            refreshToken: "refresh-token",
            expiresAt: Math.floor(Date.now() / 1000) + 60,
        });
        dispatch.mockReset();
        redirectToLogin.mockReset();
        refreshClinicianSession.mockReset();
        writeStoredSession.mockReset();
    });

    it("refreshes an authenticated session before expiry and stores the new session", async () => {
        const refreshedSession = {
            accessToken: "new-access-token",
            refreshToken: "new-refresh-token",
            expiresAt: Math.floor(Date.now() / 1000) + 3600,
            user: { id: "clinician-1", email: "clinician@example.com", role: "clinician" },
        };
        refreshClinicianSession.mockResolvedValue(refreshedSession);

        render(<TestHarness />);

        await waitFor(() => {
            expect(refreshClinicianSession).toHaveBeenCalledWith("refresh-token");
        });
        expect(writeStoredSession).toHaveBeenCalledWith(refreshedSession);
        expect(dispatch).toHaveBeenCalledWith(
            expect.objectContaining({ type: "auth/hydrateSession" }),
        );
    });

    it("does not refresh when the access token is not close to expiry", async () => {
        setAuthState({ expiresAt: Math.floor(Date.now() / 1000) + 3600 });

        render(<TestHarness />);
        await Promise.resolve();

        expect(refreshClinicianSession).not.toHaveBeenCalled();
        expect(writeStoredSession).not.toHaveBeenCalled();
    });

    it("checks again on focus so a returning tab renews the session", async () => {
        const refreshedSession = {
            accessToken: "new-access-token",
            refreshToken: "new-refresh-token",
            expiresAt: Math.floor(Date.now() / 1000) + 3600,
            user: { id: "clinician-1", email: "clinician@example.com", role: "clinician" },
        };
        refreshClinicianSession.mockResolvedValue(refreshedSession);

        render(<TestHarness />);

        await waitFor(() => {
            expect(refreshClinicianSession).toHaveBeenCalledTimes(1);
        });

        window.dispatchEvent(new Event("focus"));

        await waitFor(() => {
            expect(refreshClinicianSession).toHaveBeenCalledTimes(2);
        });
    });

    it("logs out and redirects when refresh fails", async () => {
        refreshClinicianSession.mockRejectedValue(new Error("refresh failed"));

        render(<TestHarness />);

        await waitFor(() => {
            expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "auth/logout" }));
        });
        expect(redirectToLogin).toHaveBeenCalledWith({ reason: "session_expired" });
    });
});
