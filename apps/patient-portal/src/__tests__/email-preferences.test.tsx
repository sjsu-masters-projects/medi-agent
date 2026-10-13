import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { EmailPreferences } from "@/components/features/email-preferences";

const mocks = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn() }));
vi.mock("@/services/api", () => ({ api: mocks }));
const account = { email: "demo@example.com", verified: true, synthetic: false,
  preferences: { messages: false, appointments: false, care_plans: false, records: false, reviews: false } };
beforeEach(() => { vi.resetAllMocks(); mocks.get.mockResolvedValue(account); });
afterEach(cleanup);

describe("optional email preferences", () => {
  it("renders as a labelled Profile section with the address and a verified chip", async () => {
    render(<EmailPreferences token="test-session" />);
    const section = await screen.findByRole("region", { name: "Email notices" });
    expect(within(section).getByRole("heading", { level: 3, name: "Email notices" })).toBeInTheDocument();
    await within(section).findByText("Verified");
    expect(within(section).getByText("demo@example.com")).toHaveAttribute("title", "demo@example.com");
    expect(within(section).getByText("These choices don't affect account recovery emails.")).toBeInTheDocument();
    expect(within(section).getByText("No health details in emails. Replies aren't read.")).toBeInTheDocument();
  });
  it("does not silently opt into email", async () => {
    render(<EmailPreferences token="test-session" />);
    await screen.findByText("Verified");
    const toggles = screen.getAllByRole("checkbox");
    expect(toggles).toHaveLength(4);
    for (const checkbox of toggles) expect(checkbox).not.toBeChecked();
    expect(mocks.put).not.toHaveBeenCalled();
  });
  it("saves only after the explicit action with the current session", async () => {
    mocks.put.mockResolvedValue({ ...account, preferences: { ...account.preferences, messages: true } });
    render(<EmailPreferences token="test-session" />);
    fireEvent.click(await screen.findByLabelText("Unread care-team messages"));
    fireEvent.click(screen.getByRole("button", { name: "Save notices" }));
    await screen.findByText("Email notices saved.");
    expect(mocks.put).toHaveBeenCalledWith("/api/v1/email/preferences", { ...account.preferences, messages: true }, { token: "test-session" });
  });
  it("does not offer sending or opt-in for nonexistent synthetic mailboxes", async () => {
    mocks.get.mockResolvedValue({ ...account, verified: false, synthetic: true });
    render(<EmailPreferences token="test-session" />);
    await screen.findByText("Demo accounts can't receive email. In-app notifications stay on.");
    expect(screen.getByText("Email unavailable")).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Six-digit code")).not.toBeInTheDocument();
  });
  it("shows the code field only after a code is requested", async () => {
    mocks.get.mockResolvedValue({ ...account, verified: false });
    mocks.post.mockResolvedValue({ status: "queued" });
    render(<EmailPreferences token="test-session" />);
    await screen.findByText("Not verified");
    expect(screen.queryByLabelText("Six-digit code")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Send code" }));
    await screen.findByText("Code requested. Check your inbox; it may take a few minutes.");
    expect(screen.getByLabelText("Six-digit code")).toHaveAttribute("autocomplete", "one-time-code");
    expect(screen.getByText("Enter the 6-digit code we sent.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send a new code" })).toBeInTheDocument();
    expect(mocks.post).toHaveBeenCalledWith("/api/v1/email/verify/request", {}, { token: "test-session" });
  });
  it("handles an expired code without claiming verification", async () => {
    mocks.get.mockResolvedValue({ ...account, verified: false });
    mocks.post.mockResolvedValueOnce({ status: "queued" }).mockResolvedValueOnce({ verified: false });
    render(<EmailPreferences token="test-session" />);
    fireEvent.click(await screen.findByRole("button", { name: "Send code" }));
    fireEvent.change(await screen.findByLabelText("Six-digit code"), { target: { value: "12a3456" } });
    expect(screen.getByLabelText("Six-digit code")).toHaveValue("123456");
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    await screen.findByText("The code is invalid or expired. Request a new code.");
    expect(mocks.post).toHaveBeenLastCalledWith("/api/v1/email/verify", { code: "123456" }, { token: "test-session" });
    expect(screen.queryByText("Email verified")).not.toBeInTheDocument();
    expect(screen.queryByText("Verified")).not.toBeInTheDocument();
  });
  it("shows notice toggles after a successful verification", async () => {
    mocks.get.mockResolvedValueOnce({ ...account, verified: false }).mockResolvedValueOnce(account);
    mocks.post.mockResolvedValueOnce({ status: "queued" }).mockResolvedValueOnce({ verified: true });
    render(<EmailPreferences token="test-session" />);
    fireEvent.click(await screen.findByRole("button", { name: "Send code" }));
    fireEvent.change(await screen.findByLabelText("Six-digit code"), { target: { value: "654321" } });
    fireEvent.click(screen.getByRole("button", { name: "Verify" }));
    await screen.findByText("Email verified");
    await screen.findByText("Verified");
    expect(screen.getAllByRole("checkbox")).toHaveLength(4);
  });
  it("explains the daily code limit", async () => {
    mocks.get.mockResolvedValue({ ...account, verified: false });
    mocks.post.mockResolvedValue({ status: "limit" });
    render(<EmailPreferences token="test-session" />);
    fireEvent.click(await screen.findByRole("button", { name: "Send code" }));
    await screen.findByText(/requested several codes today/);
  });
  it("shows a calm notice before email setup is installed", async () => {
    mocks.get.mockResolvedValue({ ...account, verified: false, available: false });
    render(<EmailPreferences token="test-session" />);
    await screen.findByText("Email notices aren't available yet. In-app notifications still work.");
    expect(screen.queryByRole("button", { name: "Send code" })).not.toBeInTheDocument();
    expect(screen.queryByText("Not verified")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
  it("uses Spanish labels, chip and demo copy", async () => {
    mocks.get.mockResolvedValue({ ...account, verified: false, synthetic: true });
    render(<EmailPreferences token="test-session" locale="es-MX" />);
    await screen.findByRole("heading", { name: "Avisos por correo" });
    await screen.findByText("Correo no disponible");
    expect(screen.getByText("Las cuentas de demostración no reciben correos. Las notificaciones en la app siguen activas.")).toBeInTheDocument();
    expect(screen.getByText("Los correos no incluyen datos de salud. Las respuestas no se leen.")).toBeInTheDocument();
  });
  it("explains the daily code limit in Spanish", async () => {
    mocks.get.mockResolvedValue({ ...account, verified: false });
    mocks.post.mockResolvedValue({ status: "limit" });
    render(<EmailPreferences token="test-session" locale="es-MX" />);
    await screen.findByText("Sin verificar");
    fireEvent.click(screen.getByRole("button", { name: "Enviar código" }));
    await screen.findByText(/Ya solicitaste varios códigos hoy/);
  });
  it("redacts provider errors and supports retry", async () => {
    mocks.get.mockRejectedValueOnce(new Error("private-provider-error"));
    render(<EmailPreferences token="test-session" />);
    await screen.findByRole("alert");
    expect(screen.queryByText("private-provider-error")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findByText("Verified");
  });
  it("ignores a previous account's pending save after session change", async () => {
    let finish!: (value: typeof account) => void;
    mocks.put.mockReturnValue(new Promise(resolve => { finish = resolve; }));
    const view = render(<EmailPreferences token="old-session" />);
    fireEvent.click(await screen.findByRole("button", { name: "Save notices" }));
    mocks.get.mockResolvedValue({ ...account, email: "new@example.com" });
    view.rerender(<EmailPreferences token="new-session" />);
    await screen.findByText("new@example.com");
    finish(account);
    await waitFor(() => expect(screen.queryByText("demo@example.com")).not.toBeInTheDocument());
    expect(screen.queryByText("Email notices saved.")).not.toBeInTheDocument();
  });
});
