import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }));

vi.mock("react-redux", () => ({
    useSelector: (selector: (state: { auth: { accessToken: string } }) => unknown) =>
        selector({ auth: { accessToken: "session" } }),
}));
vi.mock("@/services/api", () => ({ api: mocks }));
vi.mock("@/components/features/email-preferences", () => ({ EmailPreferences: () => null }));
vi.mock("@/components/features/email-invitations", () => ({
    EmailInvitations: () => <section aria-label="Invitation history" />,
}));

import SettingsPage from "@/app/(dashboard)/settings/page";

const staff = [
    { id: "clinician-1", email: "provider@example.com", first_name: "Pat", last_name: "Lee", role: "provider", specialty: "", created_at: null },
    { id: "clinician-2", email: "admin@example.com", first_name: "Ada", last_name: "Admin", role: "admin", specialty: "", created_at: null },
];

function mockSignedInAs(role: string) {
    mocks.get.mockImplementation(async (path: string) => {
        if (path === "/api/v1/staff/") return { staff, clinic_name: "City Health", clinic_code: "ABC123" };
        if (path === "/api/v1/clinicians/me") {
            return { id: "clinician-1", email: "provider@example.com", first_name: "Pat", last_name: "Lee", specialty: "", role };
        }
        if (path === "/api/v1/clinicians/me/invite-codes") return { invites: [] };
        throw new Error(`Unexpected request ${path}`);
    });
}

async function openTeamTab() {
    render(<SettingsPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
    await screen.findByText("Active Staff (2)");
}

describe("Settings team and roles", () => {
    beforeEach(() => vi.resetAllMocks());
    afterEach(cleanup);

    it("offers team invitations and their history to clinic admins", async () => {
        mockSignedInAs("admin");
        await openTeamTab();
        expect(await screen.findByRole("heading", { name: "Invite Team Member" })).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Send Invite" })).toBeInTheDocument();
        expect(screen.getByRole("region", { name: "Invitation history" })).toBeInTheDocument();
        expect(screen.queryByText("Only clinic admins can invite team members.")).not.toBeInTheDocument();
    });

    it("shows providers a read-only note and the active staff list", async () => {
        mockSignedInAs("provider");
        await openTeamTab();
        expect(await screen.findByRole("note")).toHaveTextContent("Only clinic admins can invite team members.");
        expect(screen.queryByRole("heading", { name: "Invite Team Member" })).not.toBeInTheDocument();
        expect(screen.queryByRole("button", { name: "Send Invite" })).not.toBeInTheDocument();
        expect(screen.queryByLabelText("Email Address")).not.toBeInTheDocument();
        expect(screen.queryByRole("region", { name: "Invitation history" })).not.toBeInTheDocument();
        expect(screen.getByText("admin@example.com")).toBeInTheDocument();
        // The role comes from the profile already loaded; no extra role lookup.
        expect(mocks.get.mock.calls.map(([path]) => path)).not.toContain("/api/v1/email/invitations");
    });

    it("copies the clinic code and says so next to the button", async () => {
        mockSignedInAs("provider");
        const writeText = vi.fn().mockResolvedValue(undefined);
        Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
        try {
            render(<SettingsPage />);
            const copy = await screen.findByRole("button", { name: "Copy clinic code" });
            await screen.findByText("ABC123");
            fireEvent.click(copy);
            expect(await screen.findByText("Copied")).toHaveAttribute("role", "status");
            expect(writeText).toHaveBeenCalledWith("ABC123");
        } finally {
            Reflect.deleteProperty(navigator, "clipboard");
        }
    });

    describe("clinic-scoped actions", () => {
        const clinicA = { clinic_id: "clinic-a", clinic_code: "AAA111", clinic_name: "City Health", role: "admin", status: "active" };
        const clinicB = { clinic_id: "clinic-b", clinic_code: "BBB222", clinic_name: "Bay Clinic", role: "provider", status: "active" };

        class ClinicRequired extends Error {
            readonly details = { error: { code: "CLINIC_REQUIRED" } };
            readonly status = 422;
        }

        function mockClinics(clinics: unknown[], profileRole = "admin", defaultClinicId: string | null = null) {
            mocks.get.mockImplementation(async (path: string) => {
                if (path === "/api/v1/clinicians/me/clinics") return { clinics, default_clinic_id: defaultClinicId };
                if (path.startsWith("/api/v1/staff/")) {
                    if (clinics.length > 1 && !path.includes("clinic_id=")) throw new ClinicRequired("Choose the clinic for this action.");
                    return { staff, clinic_name: path.includes("clinic-b") ? "Bay Clinic" : "City Health", clinic_code: "ABC123" };
                }
                if (path === "/api/v1/clinicians/me") {
                    return { id: "clinician-1", email: "provider@example.com", first_name: "Pat", last_name: "Lee", specialty: "", role: profileRole };
                }
                if (path.startsWith("/api/v1/clinicians/me/invite-codes")) {
                    if (clinics.length > 1 && !path.includes("clinic_id=")) throw new ClinicRequired("Choose the clinic for this action.");
                    return { invites: [] };
                }
                throw new Error(`Unexpected request ${path}`);
            });
        }

        it("shows staff role and removal actions only to an admin at the picked clinic", async () => {
            mockClinics([clinicA, clinicB], "admin", "clinic-a");
            render(<SettingsPage />);
            fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
            await screen.findByText("Active Staff (2)");
            // Admin at City Health: actions on the other member.
            expect(screen.getByRole("button", { name: "Actions for Ada Admin" })).toBeInTheDocument();

            // Provider at Bay Clinic: the server would refuse them, so they are not offered.
            fireEvent.change(screen.getByLabelText("Clinic"), { target: { value: "clinic-b" } });
            await screen.findByRole("note");
            expect(screen.queryByRole("button", { name: /^Actions for/ })).not.toBeInTheDocument();
            expect(screen.getByText("admin@example.com")).toBeInTheDocument();
        });

        it("warns that removal ends the member's patient links at that clinic", async () => {
            mockClinics([clinicA, clinicB], "admin", "clinic-a");
            mocks.delete.mockResolvedValue({});
            const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
            render(<SettingsPage />);
            fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
            await screen.findByText("Active Staff (2)");
            fireEvent.click(screen.getByRole("button", { name: "Actions for Ada Admin" }));
            fireEvent.click(screen.getByRole("button", { name: "Remove from clinic" }));
            expect(confirm).toHaveBeenCalledWith(expect.stringContaining("Their patient links at City Health end; patients keep their other care-team members."));
            expect(mocks.delete).not.toHaveBeenCalled();
            confirm.mockRestore();
        });

        it("hides staff actions from a provider who is the only clinic's member", async () => {
            mockClinics([{ ...clinicA, role: "provider" }], "provider");
            render(<SettingsPage />);
            fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
            await screen.findByText("Active Staff (2)");
            expect(screen.queryByRole("button", { name: /^Actions for/ })).not.toBeInTheDocument();
        });

        it("sends the only clinic automatically", async () => {
            mockClinics([clinicA]);
            render(<SettingsPage />);
            fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
            await screen.findByText("Active Staff (2)");

            expect(mocks.get).toHaveBeenCalledWith("/api/v1/staff/?clinic_id=clinic-a", { token: "session" });
            expect(mocks.get).toHaveBeenCalledWith("/api/v1/clinicians/me/invite-codes?clinic_id=clinic-a", { token: "session" });
            // One clinic: no picker.
            expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
        });

        it("asks which clinic when the server requires a choice, then scopes every action to it", async () => {
            mockClinics([clinicA, clinicB]);
            mocks.post.mockResolvedValue({ status: "queued", email_sent: false });
            render(<SettingsPage />);

            fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
            const picker = await screen.findByLabelText("Clinic");
            expect(await screen.findByText(/choose which one this applies to/i)).toBeInTheDocument();
            // The refusal is a prompt, not an error.
            expect(screen.queryByRole("alert")).not.toBeInTheDocument();

            fireEvent.change(picker, { target: { value: "clinic-a" } });
            await screen.findByText("Active Staff (2)");
            expect(mocks.get).toHaveBeenCalledWith("/api/v1/staff/?clinic_id=clinic-a", { token: "session" });

            fireEvent.change(await screen.findByLabelText("Email Address"), { target: { value: "new@example.com" } });
            fireEvent.click(screen.getByRole("button", { name: "Send Invite" }));
            await waitFor(() =>
                expect(mocks.post).toHaveBeenCalledWith(
                    "/api/v1/staff/invite",
                    { email: "new@example.com", role: "provider", clinic_id: "clinic-a" },
                    { token: "session" },
                ),
            );
        });

        it("uses the role held at the chosen clinic, not the profile role", async () => {
            mockClinics([clinicA, clinicB], "admin");
            render(<SettingsPage />);
            fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
            fireEvent.change(await screen.findByLabelText("Clinic"), { target: { value: "clinic-b" } });
            await screen.findByText("Active Staff (2)");

            // Admin at City Health, provider at Bay Clinic: no admin controls here.
            expect(await screen.findByRole("note")).toHaveTextContent("Only clinic admins can invite team members.");
            expect(screen.queryByRole("button", { name: "Send Invite" })).not.toBeInTheDocument();
        });

        it("starts on the default clinic when there are several", async () => {
            mockClinics([clinicA, clinicB], "admin", "clinic-b");
            render(<SettingsPage />);
            fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
            await screen.findByText("Active Staff (2)");
            expect(mocks.get).toHaveBeenCalledWith("/api/v1/staff/?clinic_id=clinic-b", { token: "session" });
            expect(await screen.findByLabelText("Clinic")).toHaveValue("clinic-b");
        });

        it("shows the clinic picker only on the clinic-scoped tabs", async () => {
            mockClinics([clinicA, clinicB], "admin", "clinic-a");
            render(<SettingsPage />);
            await screen.findByRole("button", { name: "Team & Roles" });
            // The picker is only for the Team and Patient Invites tabs; General Profile's
            // Your clinics card scopes each action per row.
            expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
            fireEvent.click(screen.getByRole("button", { name: "Patient Invites" }));
            expect(await screen.findByLabelText("Clinic")).toBeInTheDocument();
            fireEvent.click(screen.getByRole("button", { name: "Interoperability" }));
            expect(screen.queryByLabelText("Clinic")).not.toBeInTheDocument();
        });

        it("does not list a suspended clinic", async () => {
            const suspended = { ...clinicB, clinic_id: "clinic-c", clinic_name: "Closed Clinic", status: "suspended" };
            mockClinics([clinicA, clinicB, suspended], "admin", "clinic-a");
            render(<SettingsPage />);
            fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
            const picker = await screen.findByLabelText("Clinic");
            expect(picker).toHaveTextContent("Bay Clinic");
            expect(picker).not.toHaveTextContent("Closed Clinic");
        });

        it("follows the role at the selected clinic when switching", async () => {
            mockClinics([clinicA, clinicB], "admin", "clinic-a");
            render(<SettingsPage />);
            fireEvent.click(await screen.findByRole("button", { name: "Team & Roles" }));
            expect(await screen.findByRole("button", { name: "Send Invite" })).toBeInTheDocument();
            fireEvent.change(await screen.findByLabelText("Clinic"), { target: { value: "clinic-b" } });
            await waitFor(() => expect(screen.queryByRole("button", { name: "Send Invite" })).not.toBeInTheDocument());
            fireEvent.change(screen.getByLabelText("Clinic"), { target: { value: "clinic-a" } });
            expect(await screen.findByRole("button", { name: "Send Invite" })).toBeInTheDocument();
        });

        it("generates a patient invite code for the chosen clinic", async () => {
            mockClinics([clinicA, clinicB]);
            mocks.post.mockResolvedValue({ invite_code: "ABCD1234", care_team_id: "team-1" });
            render(<SettingsPage />);
            fireEvent.click(await screen.findByRole("button", { name: "Patient Invites" }));
            fireEvent.change(await screen.findByLabelText("Clinic"), { target: { value: "clinic-a" } });
            fireEvent.click(await screen.findByRole("button", { name: /generate/i }));
            await waitFor(() =>
                expect(mocks.post).toHaveBeenCalledWith(
                    "/api/v1/clinicians/me/invite-code",
                    { clinic_id: "clinic-a" },
                    { token: "session" },
                ),
            );
        });
    });
});
