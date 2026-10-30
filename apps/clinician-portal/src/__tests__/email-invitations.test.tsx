import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { EmailInvitations } from "@/components/features/email-invitations";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock("@/services/api", () => ({ api: mocks }));
const item = { id: "invite-1", email: "demo@example.com", role: "provider", expires_at: "2099-01-01T00:00:00Z", accepted_at: null, revoked_at: null, delivery_state: "accepted" };
beforeEach(() => { vi.resetAllMocks(); mocks.get.mockResolvedValue({ items: [item] }); });
afterEach(cleanup);

it("keeps email delivery separate from membership and does not call the mail service a provider", async () => {
  render(<EmailInvitations token="session" revision={null} />);
  await screen.findByText("Email sent — delivery not yet confirmed");
  expect(screen.getByText("Provider · Awaiting acceptance")).toBeInTheDocument();
  expect(screen.queryByText(/Provider accepted|Provider confirmed/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Revoke invitation" })).toBeInTheDocument();
});
it("revokes the exact unused invitation and refreshes its authoritative status", async () => {
  mocks.post.mockResolvedValue({ status: "revoked" });
  render(<EmailInvitations token="session" revision={null} />);
  fireEvent.click(await screen.findByRole("button", { name: "Revoke invitation" }));
  await waitFor(() => expect(mocks.post).toHaveBeenCalledWith("/api/v1/email/invitations/invite-1/revoke", {}, { token: "session" }));
  await waitFor(() => expect(mocks.get).toHaveBeenCalledTimes(2));
});
it("does not offer revocation for an accepted membership", async () => {
  mocks.get.mockResolvedValue({ items: [{ ...item, accepted_at: "2026-10-11T00:00:00Z" }] });
  render(<EmailInvitations token="session" revision={null} />);
  await screen.findByText(/Provider · Accepted/);
  expect(screen.queryByRole("button", { name: "Revoke invitation" })).not.toBeInTheDocument();
});
it("reads one clinic's invitation history when a clinic is named", async () => {
  render(<EmailInvitations clinicId="clinic-a" token="session" revision={null} />);
  await screen.findByText("Email sent — delivery not yet confirmed");
  expect(mocks.get).toHaveBeenCalledWith("/api/v1/email/invitations?clinic_id=clinic-a", { token: "session" });
});
it("explains a refusal for a clinic where the clinician is not an admin", async () => {
  mocks.get.mockRejectedValue(Object.assign(new Error("Only clinic admins can manage staff"), { status: 403, details: { error: { code: "AUTHORIZATION_ERROR" } } }));
  render(<EmailInvitations clinicId="clinic-b" token="session" revision={null} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Only clinic admins can manage staff");
});
