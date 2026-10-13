import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import OnboardingPage from "@/app/(auth)/onboarding/page";

const { dispatch, post, put, replace } = vi.hoisted(() => ({
    dispatch: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    replace: vi.fn(),
}));

vi.mock("@/hooks/use-patient-profile", () => ({
    useSharedPatientProfile: () => null,
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
    useSelector: (selector: (state: unknown) => unknown) =>
        selector({
            auth: { accessToken: "access-token" },
            onboarding: {
                profileDraft: {
                    dateOfBirth: "1990-01-01",
                    firstName: "Sarah",
                    lastName: "Jones",
                },
            },
        }),
}));

vi.mock("@/services/api", () => ({
    api: { post, put },
}));

describe("Patient onboarding page", () => {
    beforeEach(() => {
        window.localStorage.clear();
        window.history.replaceState({}, "", "/");
        replace.mockReset();
        dispatch.mockReset();
        post.mockReset();
        put.mockReset();
    });

    it("saves the selected Spanish preference and shows an honest medical-information step", async () => {
        put.mockResolvedValue({});
        post.mockResolvedValue({ clinician_first_name: "Synthetic" });
        render(<OnboardingPage />);
        fireEvent.click(screen.getByRole("button", { name: "Next" }));
        fireEvent.change(screen.getByRole("combobox", { name: "Preferred language" }), { target: { value: "es-MX" } });
        fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
        expect(screen.getByText(/La configuración no guarda alergias ni padecimientos/)).toBeInTheDocument();
        expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Siguiente" }));
        fireEvent.change(screen.getByLabelText("Código de invitación de la clínica"), { target: { value: "SYNTHETIC" } });
        fireEvent.click(screen.getByRole("button", { name: "Terminar configuración" }));
        await waitFor(() => expect(put).toHaveBeenCalledWith("/api/v1/patients/me", expect.objectContaining({ preferred_language: "es-MX" }), { token: "access-token" }));
        await waitFor(() => expect(replace).toHaveBeenCalledWith("/today"));
    });

    it.each(["profile", "join"])("localizes a deferred %s failure after switching language", async (stage) => {
        let reject!: (error: unknown) => void;
        const pending = new Promise<never>((_, fail) => { reject = fail; });
        if (stage === "profile") put.mockReturnValue(pending);
        else { put.mockResolvedValue({}); post.mockReturnValue(pending); }
        render(<OnboardingPage />);
        for (let step = 1; step < 4; step++) fireEvent.click(screen.getByRole("button", { name: "Next" }));
        fireEvent.change(screen.getByLabelText("Clinic invite code"), { target: { value: "SYNTHETIC-CODE" } });
        fireEvent.click(screen.getByRole("button", { name: "Finish setup" }));
        await waitFor(() => expect(stage === "profile" ? put : post).toHaveBeenCalledTimes(1));
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "es-MX" } });
        await act(async () => reject(Object.assign(new Error("Synthetic failure"), { status: 422 })));
        expect(await screen.findByRole("alert")).toHaveTextContent(stage === "join" ? "No se pudo usar el código de invitación" : "No se pudo completar la solicitud");
        fireEvent.change(screen.getByRole("combobox", { name: "Idioma" }), { target: { value: "en-US" } });
        expect(screen.getByRole("alert")).toHaveTextContent(stage === "join" ? "Could not use this invite code" : "Could not complete the request");
        expect(replace).not.toHaveBeenCalledWith("/today");
    });

    it("updates invite-code validation after changing language without resubmitting", () => {
        render(<OnboardingPage />);
        for (let step = 1; step < 4; step++) fireEvent.click(screen.getByRole("button", { name: "Next" }));
        fireEvent.click(screen.getByRole("button", { name: "Finish setup" }));
        expect(screen.getByRole("alert")).toHaveTextContent("Clinic invite code is required");
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), { target: { value: "es-MX" } });
        expect(screen.getByRole("alert")).toHaveTextContent("El código de invitación de la clínica es obligatorio");
        expect(put).not.toHaveBeenCalled();
        expect(post).not.toHaveBeenCalled();
    });

    it("requires invite code and surfaces join-clinic errors", async () => {
        put.mockResolvedValue({});
        post.mockRejectedValue(Object.assign(new Error("Invalid or expired invite code"), { status: 422 }));

        render(<OnboardingPage />);
        fireEvent.click(screen.getByRole("button", { name: /next/i }));
        fireEvent.click(screen.getByRole("button", { name: /next/i }));
        fireEvent.click(screen.getByRole("button", { name: /next/i }));

        fireEvent.click(screen.getByRole("button", { name: /finish setup/i }));
        expect(await screen.findByText(/clinic invite code is required/i)).toBeInTheDocument();

        fireEvent.change(screen.getByLabelText(/clinic invite code/i), {
            target: { value: "BAD-CODE" },
        });
        fireEvent.click(screen.getByRole("button", { name: /finish setup/i }));

        expect(await screen.findByText(/Could not use this invite code/i)).toBeInTheDocument();
        await waitFor(() => expect(replace).not.toHaveBeenCalledWith("/today"));
    });
});
