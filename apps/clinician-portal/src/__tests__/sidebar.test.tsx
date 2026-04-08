import { render, screen } from "@testing-library/react";
import { Provider } from "react-redux";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Sidebar } from "@/components/layouts/sidebar";
import { hydrateSession } from "@/store/slices/auth-slice";
import { store } from "@/store/store";

vi.mock("next/navigation", () => ({
    usePathname: () => "/dashboard",
}));

describe("Sidebar", () => {
    beforeEach(() => {
        store.dispatch(
            hydrateSession({
                token: "test-token",
                user: {
                    email: "dr.smith@cityhealth.org",
                    id: "clinician-1",
                    role: "clinician",
                },
            }),
        );
    });

    it("renders all navigation items and highlights the active route", () => {
        render(
            <Provider store={store}>
                <Sidebar />
            </Provider>,
        );

        expect(screen.getByText("Risk Radar")).toBeInTheDocument();
        expect(screen.getByText("Patient Roster")).toBeInTheDocument();
        expect(screen.getByText("MedWatch Queue")).toBeInTheDocument();
        expect(screen.getByText("Messages")).toBeInTheDocument();
        expect(screen.getByText("Clinic Settings")).toBeInTheDocument();
        expect(screen.getByRole("link", { name: /risk radar/i }).className).toContain("bg-blue-600");
    });
});
