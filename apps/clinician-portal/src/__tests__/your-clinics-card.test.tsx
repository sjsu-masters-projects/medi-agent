import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@/services/api", () => ({ api: mocks }));

import { YourClinicsCard } from "@/components/features/your-clinics-card";

const clinicA = { clinic_id: "clinic-a", clinic_code: "AAA111", clinic_name: "City Health", role: "admin", status: "active" };
const clinicB = { clinic_id: "clinic-b", clinic_code: "BBB222", clinic_name: "Bay Clinic", role: "provider", status: "active" };

function mockAccount(clinics: unknown[], defaultId: string, staffAdmins: number) {
    mocks.get.mockImplementation(async (path: string) => {
        if (path === "/api/v1/clinicians/me/clinics") return { clinics, default_clinic_id: defaultId };
        if (path.startsWith("/api/v1/staff/")) {
            return {
                staff: Array.from({ length: staffAdmins }, (_, index) => ({ id: `admin-${index}`, role: "admin" })),
            };
        }
        throw new Error(`Unexpected request ${path}`);
    });
}

describe("Your clinics card", () => {
    beforeEach(() => vi.resetAllMocks());
    afterEach(cleanup);

    it("lists each clinic with its role, the default badge, and the clinic code for admins only", async () => {
        mockAccount([clinicA, clinicB], "clinic-a", 2);
        render(<YourClinicsCard onChanged={vi.fn()} token="session" />);

        const city = (await screen.findByText("City Health")).closest("li") as HTMLElement;
        const bay = screen.getByText("Bay Clinic").closest("li") as HTMLElement;
        expect(within(city).getByText("Clinic Admin")).toBeInTheDocument();
        expect(within(city).getByText("Default")).toBeInTheDocument();
        expect(within(city).getByText("AAA111")).toBeInTheDocument();
        expect(within(city).getByRole("button", { name: "Copy clinic code for City Health" })).toBeInTheDocument();
        expect(within(city).queryByRole("button", { name: /make city health/i })).not.toBeInTheDocument();
        expect(within(bay).getByText("Provider")).toBeInTheDocument();
        expect(within(bay).queryByText("Default")).not.toBeInTheDocument();
        expect(within(bay).queryByText("BBB222")).not.toBeInTheDocument();
    });

    it("makes another clinic the default without leaving anything", async () => {
        mockAccount([clinicA, clinicB], "clinic-a", 2);
        mocks.put.mockResolvedValue({ clinic_id: "clinic-b", default_clinic_id: "clinic-b", role: "provider" });
        const onChanged = vi.fn();
        render(<YourClinicsCard onChanged={onChanged} token="session" />);

        fireEvent.click(await screen.findByRole("button", { name: "Make Bay Clinic your default clinic" }));

        await waitFor(() =>
            expect(mocks.put).toHaveBeenCalledWith(
                "/api/v1/clinicians/me/default-clinic",
                { clinic_id: "clinic-b" },
                { token: "session" },
            ),
        );
        expect(await screen.findByText("Bay Clinic is now your default clinic.")).toBeInTheDocument();
        expect(onChanged).toHaveBeenCalled();
        expect(mocks.post).not.toHaveBeenCalled();
    });

    it("explains what leaving does, then leaves only after confirmation", async () => {
        mockAccount([clinicA, clinicB], "clinic-a", 2);
        mocks.post.mockResolvedValue({ status: "left", clinic_id: "clinic-b", links_ended: 3, default_clinic_id: "clinic-a" });
        const onChanged = vi.fn();
        render(<YourClinicsCard onChanged={onChanged} token="session" />);

        fireEvent.click(await screen.findByRole("button", { name: "Leave Bay Clinic" }));
        const dialog = await screen.findByRole("dialog");
        expect(dialog).toHaveTextContent(/patient links and unused invite codes at Bay Clinic will end/i);
        expect(dialog).toHaveTextContent(/nothing is deleted/i);
        expect(mocks.post).not.toHaveBeenCalled();

        fireEvent.click(within(dialog).getByRole("button", { name: "Leave Bay Clinic" }));
        await waitFor(() =>
            expect(mocks.post).toHaveBeenCalledWith("/api/v1/clinicians/me/clinics/clinic-b/leave", {}, { token: "session" }),
        );
        expect(await screen.findByText("You left Bay Clinic.")).toBeInTheDocument();
        expect(onChanged).toHaveBeenCalled();
    });

    it("lets the user cancel without leaving", async () => {
        mockAccount([clinicA, clinicB], "clinic-a", 2);
        render(<YourClinicsCard onChanged={vi.fn()} token="session" />);
        fireEvent.click(await screen.findByRole("button", { name: "Leave Bay Clinic" }));
        fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Cancel" }));
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        expect(mocks.post).not.toHaveBeenCalled();
    });

    it("disables Leave with a reason for the last clinic", async () => {
        mockAccount([clinicB], "clinic-b", 1);
        render(<YourClinicsCard onChanged={vi.fn()} token="session" />);
        const leave = await screen.findByRole("button", { name: "Leave Bay Clinic" });
        expect(leave).toBeDisabled();
        expect(screen.getByText("This is your only clinic.")).toBeInTheDocument();
    });

    it("disables Leave with a reason for the only admin of a clinic", async () => {
        mockAccount([clinicA, clinicB], "clinic-b", 1);
        render(<YourClinicsCard onChanged={vi.fn()} token="session" />);
        const leave = await screen.findByRole("button", { name: "Leave City Health" });
        await waitFor(() => expect(leave).toBeDisabled());
        expect(screen.getByText("You're the only admin here.")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Leave Bay Clinic" })).toBeEnabled();
    });

    it("shows the server's reason when a leave is refused", async () => {
        mockAccount([clinicA, clinicB], "clinic-a", 2);
        mocks.post.mockRejectedValue(
            Object.assign(new Error("refused"), { details: { error: { code: "SOLE_ADMIN" } }, status: 422 }),
        );
        render(<YourClinicsCard onChanged={vi.fn()} token="session" />);
        fireEvent.click(await screen.findByRole("button", { name: "Leave City Health" }));
        fireEvent.click(within(await screen.findByRole("dialog")).getByRole("button", { name: "Leave City Health" }));
        expect(await screen.findByRole("alert")).toHaveTextContent("You are the only admin here.");
    });
});
