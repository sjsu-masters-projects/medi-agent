import { render, screen, waitFor } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layouts/sidebar";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import { store } from "@/store/store";

const replaceMock = vi.fn();
const { profileGetMock } = vi.hoisted(() => ({
    profileGetMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
    usePathname: () => "/dashboard",
    useRouter: () => ({ replace: replaceMock }),
}));

vi.mock("@/services/auth-session", () => ({
    clearStoredSession: vi.fn(),
}));

vi.mock("@/services/clinic-context", () => ({
    clearStoredClinicContext: vi.fn(),
}));

vi.mock("@/services/api", () => ({
    api: {
        get: profileGetMock,
    },
}));

describe("Sidebar", () => {
    beforeEach(() => {
        replaceMock.mockReset();
        profileGetMock.mockReset();
        profileGetMock.mockResolvedValue({
            first_name: "Rajeevranjan",
            last_name: "Chaurasia",
            role: "admin",
        });
        store.dispatch(
            hydrateSession({
                accessToken: "test-token",
                expiresAt: 1234567890,
                refreshToken: "refresh-token",
                user: {
                    email: "dr.smith@cityhealth.org",
                    id: "clinician-1",
                    role: "clinician",
                },
            }),
        );
    });

    it("renders all navigation items and highlights the active route", async () => {
        render(
            <Provider store={store}>
                <Sidebar />
            </Provider>,
        );

        expect(screen.getByText("Risk Radar")).toBeInTheDocument();
        expect(screen.getByText("Patient Roster")).toBeInTheDocument();
        expect(screen.getByText("Review Queue")).toBeInTheDocument();
        expect(screen.getByText("MedWatch Queue")).toBeInTheDocument();
        expect(screen.getByText("Messages")).toBeInTheDocument();
        expect(screen.getByText("Clinic Settings")).toBeInTheDocument();
        await waitFor(() => expect(profileGetMock).toHaveBeenCalled());
        expect(screen.getByText("Rajeevranjan Chaurasia")).toBeInTheDocument();
        expect(screen.getByText("Clinic Admin")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /risk radar/i }).className).toContain("bg-blue-600");
    });

    it("does not invent an invalid fallback email when the session is unavailable", () => {
        store.dispatch(logout());

        render(
            <Provider store={store}>
                <Sidebar />
            </Provider>,
        );

        expect(screen.getByText("Email unavailable")).toBeInTheDocument();
        expect(screen.queryByText("clinician@mediagent.local")).not.toBeInTheDocument();
    });
});
