import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmailPreferences } from "@/components/features/email-preferences";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@/services/api", () => ({ api: mocks }));
const account = { email: "demo@example.com", verified: true, synthetic: false,
  preferences: { messages: false, appointments: false, care_plans: false, records: false, reviews: false } };
beforeEach(() => { vi.resetAllMocks(); mocks.get.mockResolvedValue(account); });
afterEach(cleanup);

describe("optional email preferences", () => {
  it("does not silently opt into email", async () => {
    render(<EmailPreferences token="test-session" />);
    await screen.findByText("Email verified");
    for (const checkbox of screen.getAllByRole("checkbox")) expect(checkbox).not.toBeChecked();
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it("saves only after the explicit action with the current session", async () => {
    mocks.put.mockResolvedValue({ ...account, preferences: { ...account.preferences, messages: true } });
    render(<EmailPreferences token="test-session" />);
    fireEvent.click(await screen.findByLabelText("Unread care-team messages"));
    fireEvent.click(screen.getByRole("button", { name: "Save email preferences" }));
    await screen.findByText("Email preferences saved.");
    expect(mocks.put).toHaveBeenCalledWith("/api/v1/email/preferences", { ...account.preferences, messages: true }, { token: "test-session" });
  });
  it("does not offer sending or opt-in for nonexistent synthetic mailboxes", async () => {
    mocks.get.mockResolvedValue({ ...account, verified: false, synthetic: true });
    render(<EmailPreferences token="test-session" />);
    await screen.findByText("This demo login address cannot receive email. In-app notifications still work.");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Send verification code" })).not.toBeInTheDocument();
  });
  it("handles an expired code without claiming verification", async () => {
    mocks.get.mockResolvedValue({ ...account, verified: false });
    mocks.post.mockResolvedValue({ verified: false });
    render(<EmailPreferences token="test-session" />);
    fireEvent.change(await screen.findByLabelText("Six-digit code"), { target: { value: "123456" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify email" }));
    await screen.findByText("The code is invalid or expired. Request a new code.");
    expect(screen.queryByText("Email verified")).not.toBeInTheDocument();
  });
  it("redacts provider errors and supports retry", async () => {
    mocks.get.mockRejectedValueOnce(new Error("private-provider-error"));
    render(<EmailPreferences token="test-session" />);
    await screen.findByRole("alert");
    expect(screen.queryByText("private-provider-error")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("Email verified");
  });
  it("ignores a previous account's pending save after session change", async () => {
    let finish!: (value: typeof account) => void;
    mocks.put.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    const view = render(<EmailPreferences token="old-session" />);
    fireEvent.click(await screen.findByRole("button", { name: "Save email preferences" }));
    mocks.get.mockResolvedValue({ ...account, email: "new@example.com" });
    view.rerender(<EmailPreferences token="new-session" />);
    await screen.findByText("new@example.com");
    finish(account);
    await waitFor(() => expect(screen.queryByText("demo@example.com")).not.toBeInTheDocument());
    expect(screen.queryByText("Email preferences saved.")).not.toBeInTheDocument();
  });
});
