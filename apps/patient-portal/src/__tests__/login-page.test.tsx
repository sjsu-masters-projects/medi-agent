import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";

const { dispatch, get, post, replace, writeStoredSession, setSearchParams, getSearchParams } = vi.hoisted(() => {
    let searchParamsString = "";
    return {
        dispatch: vi.fn(),
        get: vi.fn(),
        post: vi.fn(),
        replace: vi.fn(),
        writeStoredSession: vi.fn(),
        setSearchParams: (value: string) => {
            searchParamsString = value;
        },
        getSearchParams: () => new URLSearchParams(searchParamsString),
    };
});

vi.mock("@/hooks/use-patient-profile", () => ({
    useSharedPatientProfile: () => null,
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
    useSearchParams: () => getSearchParams(),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
}));

vi.mock("@/services/api", () => ({
    api: { get, post },
}));

vi.mock("@/services/auth-session", () => ({
    writeStoredSession,
}));

import LoginPage from "@/app/login/page";

describe("Patient login page", () => {
    beforeEach(() => {
        window.localStorage.clear();
        window.history.replaceState({}, "", "/");
        replace.mockReset();
        dispatch.mockReset();
        get.mockReset();
        post.mockReset();
        writeStoredSession.mockReset();
        setSearchParams("");
    });

    it("localizes entry controls and session notices and carries only a guest preference", () => {
        setSearchParams("reason=session_expired");
        render(<LoginPage />);
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "es-MX" } });
        expect(screen.getByRole("heading", { name: "Bienvenido de nuevo" })).toBeInTheDocument();
        expect(screen.getByRole("status")).toHaveTextContent("Tu sesión expiró");
        expect(screen.getByLabelText("Correo electrónico")).toBeInTheDocument();
        expect(screen.getByRole("button", { name: "Mostrar contraseña" })).toBeInTheDocument();
        expect(screen.getByRole("link", { name: "Crear cuenta" })).toHaveAttribute("href", "/signup?lang=es-MX");
        expect(window.localStorage.getItem("patient-portal.guest.locale")).toBe("es-MX");
        expect(post).not.toHaveBeenCalled();
    });

    it("hides internal server errors behind a localized recovery message", async () => {
        window.history.replaceState({}, "", "/login?lang=es-MX");
        post.mockRejectedValue(new Error("Internal auth failure for UUID private-user-id"));
        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText("Correo electrónico"), { target: { value: "patient@example.com" } });
        fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "SyntheticPass123!" } });
        fireEvent.click(screen.getByRole("button", { name: "Iniciar sesión" }));
        expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo completar la solicitud");
        expect(screen.queryByText(/private-user-id/)).not.toBeInTheDocument();
    });

    it.each([false, true])("localizes an authentication failure when language changes, deferred=%s", async (deferred) => {
        const failure = Object.assign(new Error("Synthetic authentication failure"), { status: 401 });
        let reject!: (error: unknown) => void;
        if (deferred) post.mockReturnValue(new Promise<never>((_, fail) => { reject = fail; }));
        else post.mockRejectedValue(failure);
        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText("Email address"), { target: { value: "patient@example.com" } });
        fireEvent.change(screen.getByLabelText("Password"), { target: { value: "SyntheticPass123!" } });
        fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
        if (!deferred) expect(await screen.findByRole("alert")).toHaveTextContent("The email or password is incorrect");
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "es-MX" } });
        if (deferred) await act(async () => reject(failure));
        expect(await screen.findByRole("alert")).toHaveTextContent("El correo o la contraseña no son correctos");
        fireEvent.change(screen.getByRole("combobox", { name: "Idioma" }), { target: { value: "en-US" } });
        expect(screen.getByRole("alert")).toHaveTextContent("The email or password is incorrect");
        expect(post).toHaveBeenCalledTimes(1);
    });

    it("stores full session and redirects on successful patient login", async () => {
        post.mockResolvedValue({
            tokens: {
                access_token: "access-token",
                expires_at: 1234567890,
                refresh_token: "refresh-token",
            },
            user: {
                email: "patient@example.com",
                id: "patient-1",
                role: "patient",
            },
            requires_clinic_join: false,
        });

        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText(/email address/i), {
            target: { value: "patient@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        await waitFor(() => {
            expect(writeStoredSession).toHaveBeenCalledWith({
                accessToken: "access-token",
                expiresAt: 1234567890,
                refreshToken: "refresh-token",
                user: {
                    email: "patient@example.com",
                    id: "patient-1",
                    role: "patient",
                },
            });
        });
        expect(replace).toHaveBeenCalledWith("/today");
        expect(get).not.toHaveBeenCalled();
    });

    it("redirects to safe return_path after successful login when care team exists", async () => {
        post.mockResolvedValue({
            tokens: {
                access_token: "access-token",
                expires_at: 1234567890,
                refresh_token: "refresh-token",
            },
            user: {
                email: "patient@example.com",
                id: "patient-1",
                role: "patient",
            },
            requires_clinic_join: false,
        });

        setSearchParams("return_path=%2Ftoday%3Ftab%3Dfeed");

        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText(/email address/i), {
            target: { value: "patient@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        await waitFor(() => {
            expect(replace).toHaveBeenCalledWith("/today?tab=feed");
        });
    });

    it("redirects patients with no linked care team to profile join flow", async () => {
        post.mockResolvedValue({
            tokens: {
                access_token: "access-token",
                expires_at: 1234567890,
                refresh_token: "refresh-token",
            },
            user: {
                email: "newpatient@example.com",
                id: "patient-2",
                role: "patient",
            },
            requires_clinic_join: true,
        });

        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText(/email address/i), {
            target: { value: "newpatient@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        await waitFor(() => {
            expect(replace).toHaveBeenCalledWith("/profile?joinClinic=1");
        });
        expect(get).not.toHaveBeenCalled();
    });

    it("shows an error for clinician credentials", async () => {
        post.mockResolvedValue({
            tokens: {
                access_token: "access-token",
                expires_at: 1234567890,
                refresh_token: "refresh-token",
            },
            user: {
                email: "doctor@example.com",
                id: "clinician-1",
                role: "clinician",
            },
        });

        render(<LoginPage />);
        fireEvent.change(screen.getByLabelText(/email address/i), {
            target: { value: "doctor@example.com" },
        });
        fireEvent.change(screen.getByLabelText(/^password$/i), {
            target: { value: "SecurePass123!" },
        });
        fireEvent.click(screen.getByRole("button", { name: /sign in/i }));

        expect(await screen.findByText(/clinician account/i)).toBeInTheDocument();
        expect(replace).not.toHaveBeenCalled();
    });

    it("toggles password visibility while typing", async () => {
        render(<LoginPage />);

        const passwordInput = screen.getByLabelText(/^password$/i);
        fireEvent.change(passwordInput, {
            target: { value: "SecurePass123!" },
        });

        expect(passwordInput).toHaveAttribute("type", "password");

        fireEvent.click(screen.getByRole("button", { name: /show password/i }));
        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "text");

        fireEvent.click(screen.getByRole("button", { name: /hide password/i }));
        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password");
    });

    it("declares login autofill semantics", () => {
        render(<LoginPage />);

        expect(screen.getByLabelText(/email address/i)).toHaveAttribute("autocomplete", "email");
        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute(
            "autocomplete",
            "current-password"
        );
    });
});
