import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { dispatch, replace, post, writeStoredSession } = vi.hoisted(() => ({
    dispatch: vi.fn(),
    replace: vi.fn(),
    post: vi.fn(),
    writeStoredSession: vi.fn(),
}));

vi.mock("@/hooks/use-patient-profile", () => ({
    useSharedPatientProfile: () => null,
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
}));

vi.mock("@/services/api", () => ({
    api: { post },
}));

vi.mock("@/services/auth-session", () => ({
    writeStoredSession,
}));

import SignupPage from "@/app/(auth)/signup/page";

function fillSignup() {
    for (const [label, value] of [
        ["First name", "Synthetic"], ["Last name", "Patient"], ["Date of birth", "1990-01-01"],
        ["Email address", "patient@example.com"], ["Password", "SyntheticPass123!"], ["Confirm password", "SyntheticPass123!"],
    ]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

describe("Patient signup page", () => {
    beforeEach(() => {
        window.localStorage.clear();
        window.history.replaceState({}, "", "/");
        dispatch.mockReset();
        replace.mockReset();
        post.mockReset();
        writeStoredSession.mockReset();
    });

    it("starts without an invented birth date and translates password mismatch feedback", () => {
        render(<SignupPage />);
        expect(screen.getByLabelText("Date of birth")).toHaveValue("");
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "es-MX" } });
        fireEvent.change(screen.getByLabelText("Nombre"), { target: { value: "Paciente" } });
        fireEvent.change(screen.getByLabelText("Apellido"), { target: { value: "Sintético" } });
        fireEvent.change(screen.getByLabelText("Fecha de nacimiento"), { target: { value: "1990-01-01" } });
        fireEvent.change(screen.getByLabelText("Correo electrónico"), { target: { value: "patient@example.com" } });
        fireEvent.change(screen.getByLabelText("Contraseña"), { target: { value: "SyntheticPass123!" } });
        fireEvent.change(screen.getByLabelText("Confirmar contraseña"), { target: { value: "different" } });
        fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
        expect(screen.getByRole("alert")).toHaveTextContent("Las contraseñas no coinciden");
        expect(document.documentElement).toHaveAttribute("lang", "es-MX");
        expect(screen.getByRole("link", { name: "Iniciar sesión" })).toHaveAttribute("href", "/login?lang=es-MX");
        expect(post).not.toHaveBeenCalled();
    });

    it("preserves signup fields, session hydration and the localized onboarding route", async () => {
        post.mockResolvedValue({
            tokens: { access_token: "synthetic-access", expires_at: 1234567890, refresh_token: "synthetic-refresh" },
            user: { email: "patient@example.com", id: "synthetic-patient", role: "patient" },
        });
        render(<SignupPage />);
        fillSignup();
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "es-MX" } });
        fireEvent.click(screen.getByRole("button", { name: "Crear cuenta" }));
        await waitFor(() => expect(replace).toHaveBeenCalledWith("/onboarding?lang=es-MX"));
        expect(post).toHaveBeenCalledWith("/api/v1/auth/signup/patient", {
            date_of_birth: "1990-01-01", email: "patient@example.com", first_name: "Synthetic",
            last_name: "Patient", password: "SyntheticPass123!",
        });
        expect(writeStoredSession).toHaveBeenCalledWith({
            accessToken: "synthetic-access", expiresAt: 1234567890, refreshToken: "synthetic-refresh",
            user: { email: "patient@example.com", id: "synthetic-patient", role: "patient" },
        });
        expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({
            type: "onboarding/setOnboardingProfile",
            payload: { dateOfBirth: "1990-01-01", firstName: "Synthetic", lastName: "Patient" },
        }));
        expect(dispatch).toHaveBeenCalledWith(expect.objectContaining({ type: "auth/hydrateSession" }));
    });

    it("rejects a non-patient signup response without persisting or routing", async () => {
        post.mockResolvedValue({ user: { role: "provider" } });
        render(<SignupPage />);
        fillSignup();
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));
        expect(await screen.findByRole("alert")).toBeInTheDocument();
        expect(writeStoredSession).not.toHaveBeenCalled();
        expect(dispatch).not.toHaveBeenCalled();
        expect(replace).not.toHaveBeenCalled();
    });

    it.each([
        ["VALIDATION_ERROR", "Signup failed — email is already registered", true],
        ["VALIDATION_ERROR", "Signup failed — check email format or try a different email", false],
        ["VALIDATION_ERROR", "Signup failed — Supabase access token hook is misconfigured", false],
        ["REQUEST_VALIDATION_ERROR", "Signup failed — email is already registered", false],
    ])("classifies only the structured signup duplicate detail: %s, %s", async (code, message, duplicate) => {
        post.mockRejectedValue(Object.assign(new Error(message), { status: 422, details: { error: { code, message } } }));
        render(<SignupPage />);
        fillSignup();
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(duplicate ? "An account with this email already exists" : "Could not complete the request");
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "es-MX" } });
        expect(screen.getByRole("alert")).toHaveTextContent(duplicate ? "Ya existe una cuenta con este correo" : "No se pudo completar la solicitud");
        expect(screen.queryByText(/misconfigured/)).not.toBeInTheDocument();
    });

    it("renders a deferred duplicate failure in the newly selected language", async () => {
        let reject!: (error: unknown) => void;
        post.mockReturnValue(new Promise<never>((_, fail) => { reject = fail; }));
        render(<SignupPage />);
        fillSignup();
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "es-MX" } });
        await act(async () => reject(Object.assign(new Error("Synthetic duplicate"), { status: 422, details: { error: {
            code: "VALIDATION_ERROR", message: "Signup failed — email is already registered",
        } } })));
        expect(await screen.findByRole("alert")).toHaveTextContent("Ya existe una cuenta con este correo");
        expect(post).toHaveBeenCalledTimes(1);
    });

    it("updates already-visible password validation when the language changes", () => {
        render(<SignupPage />);
        fillSignup();
        fireEvent.change(screen.getByLabelText("Confirm password"), { target: { value: "different" } });
        fireEvent.click(screen.getByRole("button", { name: "Create account" }));
        expect(screen.getByRole("alert")).toHaveTextContent("Passwords do not match");
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "es-MX" } });
        expect(screen.getByRole("alert")).toHaveTextContent("Las contraseñas no coinciden");
        expect(post).not.toHaveBeenCalled();
    });

    it("lets patients inspect and hide both password fields", () => {
        render(<SignupPage />);

        const password = screen.getByLabelText(/^password$/i);
        const confirmPassword = screen.getByLabelText(/^confirm password$/i);

        expect(password).toHaveAttribute("type", "password");
        expect(confirmPassword).toHaveAttribute("type", "password");

        fireEvent.click(screen.getByRole("button", { name: /^show password$/i }));
        fireEvent.click(screen.getByRole("button", { name: /^show confirm password$/i }));

        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "text");
        expect(screen.getByLabelText(/^confirm password$/i)).toHaveAttribute("type", "text");

        fireEvent.click(screen.getByRole("button", { name: /^hide password$/i }));
        fireEvent.click(screen.getByRole("button", { name: /^hide confirm password$/i }));

        expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password");
        expect(screen.getByLabelText(/^confirm password$/i)).toHaveAttribute("type", "password");
    });
});
