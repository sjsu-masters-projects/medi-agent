import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
});
