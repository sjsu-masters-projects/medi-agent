import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { dispatch, redirectToLogin, refreshPatientSession, setAuthState, useAuthState, writeStoredSession } =
    vi.hoisted(() => {
        let authState = {
            loading: false,
            isAuthenticated: true,
            refreshToken: "refresh-token",
            expiresAt: 1_777_481_000,
        };

        return {
            dispatch: vi.fn(),
            redirectToLogin: vi.fn(),
            refreshPatientSession: vi.fn(),
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
    refreshPatientSession,
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

describe("useAuthSessionRefresh (patient portal)", () => {
    beforeEach(() => {
        setAuthState({
            loading: false,
            isAuthenticated: true,
            refreshToken: "refresh-token",
            expiresAt: Math.floor(Date.now() / 1000) + 60,
        });
        dispatch.mockReset();
        redirectToLogin.mockReset();
        refreshPatientSession.mockReset();
        writeStoredSession.mockReset();
    });

    it("refreshes an authenticated session before expiry and stores the new session", async () => {
        const refreshedSession = {
            accessToken: "new-access-token",
            refreshToken: "new-refresh-token",
            expiresAt: Math.floor(Date.now() / 1000) + 3600,
            user: { id: "patient-1", email: "patient@example.com", role: "patient" },
        };
        refreshPatientSession.mockResolvedValue(refreshedSession);

        render(<TestHarness />);

        await waitFor(() => {
            expect(refreshPatientSession).toHaveBeenCalledWith("refresh-token");
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

        expect(refreshPatientSession).not.toHaveBeenCalled();
        expect(writeStoredSession).not.toHaveBeenCalled();
    });

    it("checks again on focus so a returning tab renews the session", async () => {
        const refreshedSession = {
            accessToken: "new-access-token",
            refreshToken: "new-refresh-token",
            expiresAt: Math.floor(Date.now() / 1000) + 3600,
            user: { id: "patient-1", email: "patient@example.com", role: "patient" },
        };
        refreshPatientSession.mockResolvedValue(refreshedSession);

        render(<TestHarness />);

        await waitFor(() => {
            expect(refreshPatientSession).toHaveBeenCalledTimes(1);
        });

        window.dispatchEvent(new Event("focus"));

        await waitFor(() => {
            expect(refreshPatientSession).toHaveBeenCalledTimes(2);
        });
    });

    it("logs out and redirects when refresh fails", async () => {
        refreshPatientSession.mockRejectedValue(new Error("refresh failed"));

        render(<TestHarness />);

        await waitFor(() => {
            expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "auth/logout" }));
        });
        expect(redirectToLogin).toHaveBeenCalledWith({ reason: "session_expired" });
    });
});
