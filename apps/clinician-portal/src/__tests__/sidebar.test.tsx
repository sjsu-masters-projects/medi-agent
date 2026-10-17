import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layouts/sidebar";
import { hydrateSession, logout } from "@/store/slices/auth-slice";
import { store } from "@/store/store";

const replaceMock = vi.fn();
const { profileGetMock } = vi.hoisted(() => ({
    profileGetMock: vi.fn(),
}));

const pathnameRef = vi.hoisted(() => ({ value: "/dashboard" }));
vi.mock("next/navigation", () => ({
    usePathname: () => pathnameRef.value,
    useRouter: () => ({ replace: replaceMock }),
}));

vi.mock("@/services/auth-session", () => ({
    clearStoredSession: vi.fn(),
}));

vi.mock("@/services/clinic-context", () => ({
    clearStoredClinicContext: vi.fn(),
    readStoredClinicContext: vi.fn(() => null),
}));

const { notificationSummary } = vi.hoisted(() => ({ notificationSummary: { current: null as null | { unread_count: number; action_item_count: number } } }));
vi.mock("@/components/features/notification-provider", () => ({
    useOptionalNotificationCentre: () => notificationSummary.current ? { summary: { data: notificationSummary.current, error: null } } : null,
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
        expect(screen.getByRole("link", { name: "Appointments" })).toHaveAttribute("href", "/appointments");
        expect(screen.getByText("Review Queue")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "ADR Reviews" })).toHaveAttribute("href", "/adr-reviews");
        expect(screen.getByRole("link", { name: "MedWatch" })).toHaveAttribute("href", "/medwatch");
        expect(screen.getByText("Messages")).toBeInTheDocument();
        expect(screen.getByText("Clinic Settings")).toBeInTheDocument();
        await waitFor(() => expect(profileGetMock).toHaveBeenCalled());
        expect(screen.getByText("Rajeevranjan Chaurasia")).toBeInTheDocument();
        expect(screen.getByText("Clinic Admin")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: /logout/i })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /risk radar/i }).className).toContain("bg-rail-active");
        expect(screen.getByRole("link", { name: /risk radar/i })).toHaveAttribute("aria-current", "page");
        expect(screen.getByRole("navigation", { name: "Clinician navigation" })).toBeInTheDocument();
    });

    it.each([
        ["/adr-reviews", "ADR Reviews", "MedWatch"],
        ["/adr-reviews/adr-1", "ADR Reviews", "MedWatch"],
        ["/medwatch", "MedWatch", "ADR Reviews"],
        ["/medwatch/draft-1", "MedWatch", "ADR Reviews"],
    ])("marks only the matching section active on %s", (path, active, inactive) => {
        pathnameRef.value = path;
        try {
            render(<Provider store={store}><Sidebar /></Provider>);
            expect(screen.getByRole("link", { name: active })).toHaveAttribute("aria-current", "page");
            expect(screen.getByRole("link", { name: inactive })).not.toHaveAttribute("aria-current");
        } finally {
            pathnameRef.value = "/dashboard";
        }
    });

    it("does not invent an invalid fallback email when the session is unavailable", () => {
        store.dispatch(logout());

        render(
            <Provider store={store}>
                <Sidebar />
            </Provider>,
        );

        expect(screen.getByRole("group", { name: "Signed-in clinician" })).toHaveTextContent("Clinician");
        expect(screen.queryByText("clinician@mediagent.local")).not.toBeInTheDocument();
    });

    it("keeps the actual clinician name and role in the compact account row", async () => {
        render(<Provider store={store}><Sidebar /></Provider>);
        const identity = screen.getByRole("group", { name: "Signed-in clinician" });
        expect(await within(identity).findByText("Rajeevranjan Chaurasia")).toBeInTheDocument();
        expect(within(identity).getByText("Clinic Admin")).toBeInTheDocument();
        expect(identity).not.toHaveClass("hidden");
        expect(identity).toHaveClass("flex", "min-w-0");
        // The email is not repeated in the rail; it remains the account row's tooltip.
        expect(within(identity).queryByText("dr.smith@cityhealth.org")).not.toBeInTheDocument();
        expect(identity).toHaveAttribute("title", "dr.smith@cityhealth.org");
    });

    it("collapses to an icon rail that keeps accessible labels and remembers the choice", async () => {
        window.localStorage.removeItem("clinician-portal.sidebar-collapsed");
        render(<Provider store={store}><Sidebar /></Provider>);
        const toggle = screen.getByRole("button", { name: "Collapse sidebar" });
        expect(toggle).toHaveAttribute("aria-expanded", "true");

        fireEvent.click(toggle);

        const expand = await screen.findByRole("button", { name: "Expand sidebar" });
        expect(expand).toHaveAttribute("aria-expanded", "false");
        expect(screen.getByRole("link", { name: "Appointments" })).toHaveAttribute("title", "Appointments");
        expect(screen.getByText("Appointments")).toHaveClass("md:sr-only");
        expect(window.localStorage.getItem("clinician-portal.sidebar-collapsed")).toBe("1");

        fireEvent.click(expand);
        expect(await screen.findByRole("button", { name: "Collapse sidebar" })).toBeInTheDocument();
        expect(window.localStorage.getItem("clinician-portal.sidebar-collapsed")).toBe("0");
    });
    it("shows the same unread count on Alerts as the header bell", () => {
        notificationSummary.current = { unread_count: 8, action_item_count: 11 };
        render(<Provider store={store}><Sidebar /></Provider>);
        const alerts = screen.getByRole("link", { name: /Alerts/ });
        expect(within(alerts).getByText("8")).toBeInTheDocument();
        expect(within(alerts).queryByText("11")).not.toBeInTheDocument();
        notificationSummary.current = null;
    });
});
