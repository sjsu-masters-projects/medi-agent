import { fireEvent, render, screen, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { PasswordRecoveryForm } from "@/components/features/password-recovery-form";
import {
    readRecoveryTokenHash,
    readRecoveryTokens,
    withoutRecoveryQuery,
} from "../../../../packages/shared/src/utils/password-recovery";

const mocks = vi.hoisted(() => ({
    post: vi.fn(),
    create: vi.fn(),
    setSession: vi.fn(),
    getUser: vi.fn(),
    verifyOtp: vi.fn(),
    updateUser: vi.fn(),
    signOut: vi.fn(),
}));
vi.mock("@/services/api", () => ({ api: { post: mocks.post } }));
vi.mock("@/services/password-recovery", () => ({ createRecoveryClient: mocks.create }));

beforeEach(() => {
  document.cookie = "patient-portal.locale=; Path=/; Max-Age=0";
    vi.resetAllMocks();
    window.history.replaceState(null, "", "/reset-password");
    mocks.create.mockReturnValue({ auth: mocks });
    mocks.setSession.mockResolvedValue({ data: { session: {} }, error: null });
    mocks.getUser.mockResolvedValue({ data: { user: {} }, error: null });
    mocks.verifyOtp.mockResolvedValue({ data: { session: {}, user: {} }, error: null });
    mocks.updateUser.mockResolvedValue({ error: null });
    mocks.signOut.mockResolvedValue({ error: null });
    mocks.post.mockResolvedValue(undefined);
});
afterEach(cleanup);

describe("password recovery", () => {
    it("rejects ordinary login credentials and incomplete recovery links", () => {
        expect(readRecoveryTokens("#type=signup&access_token=a&refresh_token=b")).toBeNull();
        expect(readRecoveryTokens("#type=recovery&access_token=a")).toBeNull();
        expect(readRecoveryTokens("#type=recovery&error=expired&access_token=a&refresh_token=b")).toBeNull();
    });
    it("requests a fixed portal and locale without claiming delivery", async () => {
        render(<PasswordRecoveryForm mode="request" portal="patient" locale="es-MX" />);
        fireEvent.change(screen.getByLabelText("Correo electrónico"), { target: { value: "test@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Solicitar enlace" }));
        await screen.findByText(/Si existe una cuenta/);
        expect(mocks.post).toHaveBeenCalledWith("/api/v1/auth/password-reset", {
            email: "test@example.com", portal: "patient", locale: "es-MX",
        });
    });
    it("preserves the email after a failed request", async () => {
        mocks.post.mockRejectedValue(new Error("private provider details"));
        render(<PasswordRecoveryForm mode="request" portal="clinician" />);
        fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "test@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Request reset link" }));
        expect(await screen.findByRole("alert")).toHaveTextContent("Please try again");
        expect(screen.getByLabelText("Email address")).toHaveValue("test@example.com");
        expect(screen.queryByText("private provider details")).not.toBeInTheDocument();
    });
    it("moves focus to the neutral status that replaces the form", async () => {
        render(<PasswordRecoveryForm mode="request" portal="clinician" />);
        fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "test@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Request reset link" }));
        const status = await screen.findByText(/If an account exists/);
        await waitFor(() => expect(status).toHaveFocus());
    });
    it("describes request errors on the email field", async () => {
        mocks.post.mockRejectedValue(new Error("unavailable"));
        render(<PasswordRecoveryForm mode="request" portal="patient" />);
        fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "test@example.com" } });
        fireEvent.click(screen.getByRole("button", { name: "Request reset link" }));
        const alert = await screen.findByRole("alert");
        expect(screen.getByLabelText("Email address")).toHaveAttribute("aria-describedby", alert.id);
        expect(screen.getByLabelText("Email address")).toHaveAttribute("aria-invalid", "true");
    });
    it("does not offer password entry without a valid recovery link", async () => {
        render(<PasswordRecoveryForm mode="reset" portal="patient" />);
        await screen.findByText(/This link is unavailable/);
        expect(mocks.create).not.toHaveBeenCalled();
        expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Request another link" })).toHaveAttribute("href", "/forgot-password?lang=en-US");
    });
    it("scrubs the fragment and reports unavailable configuration", async () => {
        window.history.replaceState(null, "", "/reset-password#type=recovery&access_token=a&refresh_token=b");
        mocks.create.mockReturnValue(null);
        render(<PasswordRecoveryForm mode="reset" portal="patient" />);
        await screen.findByText(/Password recovery is not configured/);
        expect(window.location.hash).toBe("");
    });
    it("validates matching passwords and returns to normal login after success", async () => {
        window.history.replaceState(null, "", "/reset-password#type=recovery&access_token=a&refresh_token=b");
        render(<PasswordRecoveryForm mode="reset" portal="patient" />);
        await screen.findByLabelText("New password");
        expect(window.location.hash).toBe("");
        fireEvent.change(screen.getByLabelText("New password"), { target: { value: "SyntheticTest123!" } });
        fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "DifferentTest123!" } });
        fireEvent.click(screen.getByRole("button", { name: "Save password" }));
        const mismatch = await screen.findByRole("alert");
        expect(mismatch).toHaveTextContent("Passwords must match");
        expect(screen.getByLabelText("Confirm password")).toHaveAttribute("aria-describedby", mismatch.id);
        expect(mocks.updateUser).not.toHaveBeenCalled();
        fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "SyntheticTest123!" } });
        fireEvent.click(screen.getByRole("button", { name: "Save password" }));
        await screen.findByText(/Your password was updated/);
        expect(mocks.updateUser).toHaveBeenCalledWith({ password: "SyntheticTest123!" });
        await waitFor(() => expect(mocks.signOut).toHaveBeenCalledWith({ scope: "global" }));
        expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
    });
    it("reads scanner-safe query tokens only for recovery and keeps the language", () => {
        expect(readRecoveryTokenHash("?lang=es-MX&token_hash=abc&type=recovery")).toBe("abc");
        expect(readRecoveryTokenHash("?token_hash=abc&type=signup")).toBeNull();
        expect(readRecoveryTokenHash("?type=recovery")).toBeNull();
        expect(withoutRecoveryQuery("?lang=es-MX&token_hash=abc&type=recovery")).toBe("?lang=es-MX");
        expect(withoutRecoveryQuery("?token_hash=abc&type=recovery")).toBe("");
    });
    it("redeems a query token only after an explicit click, once", async () => {
        window.history.replaceState(null, "", "/reset-password?lang=en-US&token_hash=hash-1&type=recovery");
        render(<PasswordRecoveryForm mode="reset" portal="patient" />);
        const proceed = await screen.findByRole("button", { name: "Continue to choose a new password" });
        // Opening the page (as a mail scanner would) removes the secret and calls nothing.
        expect(window.location.search).toBe("?lang=en-US");
        expect(mocks.create).not.toHaveBeenCalled();
        expect(mocks.verifyOtp).not.toHaveBeenCalled();
        expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
        fireEvent.click(proceed);
        fireEvent.click(proceed);
        await screen.findByLabelText("New password");
        expect(mocks.verifyOtp).toHaveBeenCalledTimes(1);
        expect(mocks.verifyOtp).toHaveBeenCalledWith({ token_hash: "hash-1", type: "recovery" });
        expect(mocks.setSession).not.toHaveBeenCalled();
        fireEvent.change(screen.getByLabelText("New password"), { target: { value: "SyntheticTest123!" } });
        fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "SyntheticTest123!" } });
        fireEvent.click(screen.getByRole("button", { name: "Save password" }));
        await screen.findByText(/Your password was updated/);
        expect(mocks.updateUser).toHaveBeenCalledWith({ password: "SyntheticTest123!" });
    });
    it("removes query secrets from history before any network call", async () => {
        window.history.replaceState(null, "", "/reset-password?lang=es-MX&token_hash=hash-2&type=recovery");
        mocks.create.mockImplementation(() => {
            expect(window.location.search).toBe("?lang=es-MX");
            return { auth: mocks };
        });
        render(<PasswordRecoveryForm mode="reset" portal="patient" locale="es-MX" />);
        expect(window.location.href).not.toContain("hash-2");
        fireEvent.click(await screen.findByRole("button", { name: "Continuar para elegir una nueva contraseña" }));
        await screen.findByLabelText("Nueva contraseña");
        expect(mocks.create).toHaveBeenCalledTimes(1);
    });
    it("shows an invalid link when a query token is rejected", async () => {
        window.history.replaceState(null, "", "/reset-password?lang=en-US&token_hash=used&type=recovery");
        mocks.verifyOtp.mockResolvedValue({ data: { session: null, user: null }, error: { message: "expired" } });
        render(<PasswordRecoveryForm mode="reset" portal="patient" />);
        fireEvent.click(await screen.findByRole("button", { name: "Continue to choose a new password" }));
        await screen.findByText(/This link is unavailable/);
        expect(screen.queryByLabelText("New password")).not.toBeInTheDocument();
        expect(screen.queryByText("expired")).not.toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Request another link" })).toBeInTheDocument();
    });
    it("shows an invalid link when the Auth server rejects its session", async () => {
        window.history.replaceState(null, "", "/reset-password#type=recovery&access_token=a&refresh_token=b");
        mocks.setSession.mockResolvedValue({ data: { session: null }, error: {} });
        render(<PasswordRecoveryForm mode="reset" portal="patient" />);
        await screen.findByText(/This link is unavailable/);
        expect(mocks.getUser).not.toHaveBeenCalled();
    });
});
