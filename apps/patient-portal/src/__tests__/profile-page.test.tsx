import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProfilePage from "@/app/(app)/profile/page";
import {
    PatientProfileProvider,
    useSharedPatientProfile,
} from "@/hooks/use-patient-profile";
import type { Locale } from "@/types";

const {
    clearStoredSession,
    dispatch,
    get,
    post,
    put,
    replace,
    searchParamGet,
} = vi.hoisted(() => ({
    clearStoredSession: vi.fn(),
    dispatch: vi.fn(),
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    replace: vi.fn(),
    searchParamGet: vi.fn(),
}));

vi.mock("next/navigation", () => ({
    useRouter: () => ({ replace }),
    useSearchParams: () => ({ get: searchParamGet }),
}));

vi.mock("react-redux", () => ({
    useDispatch: () => dispatch,
    useSelector: (selector: (state: unknown) => unknown) =>
        selector({
            auth: { accessToken: "access-token" },
        }),
}));

vi.mock("@/services/api", () => ({
    api: { get, post, put },
}));

vi.mock("@/services/auth-session", () => ({
    clearStoredSession,
}));

const profileResponse = (locale: Locale = "en-US") => ({
    id: "synthetic-patient",
    first_name: "Synthetic",
    last_name: "Patient",
    email: "a-very-long-synthetic-email-for-mobile-layout@example.com",
    date_of_birth: "1985-03-15",
    gender: "female",
    timezone: "America/Los_Angeles",
    preferred_language: locale,
    created_at: "2026-01-10T00:00:00Z",
});

function SharedPreferenceProbe() {
    const shared = useSharedPatientProfile();
    return (
        <>
            <span data-testid="shared-preference">
                {shared?.profile?.preferredLanguage}
            </span>
            <button
                onClick={() => {
                    if (shared?.profile)
                        shared.updateProfile({
                            ...shared.profile,
                            preferredLanguage: "es-MX",
                        });
                }}
            >
                Change saved preference
            </button>
        </>
    );
}

describe("Patient profile page", () => {
    it.each(["en-US", "es-MX"] as const)(
        "keeps compact settings actions and helpers in %s",
        async (locale) => {
            get.mockImplementation(async (endpoint: string) =>
                endpoint === "/api/v1/patients/me"
                    ? profileResponse(locale)
                    : [
                          {
                              id: "synthetic-team",
                              status: "active",
                              role: "provider",
                              clinician_first_name: "Synthetic",
                              clinician_last_name: "Clinician",
                          },
                      ],
            );
            render(<ProfilePage />);
            const spanish = locale === "es-MX";
            const reminders = await screen.findByRole("link", {
                name: spanish
                    ? "Administrar recordatorios"
                    : "Manage reminders",
            });
            expect(reminders).toHaveAttribute("href", "/reminders");
            expect(reminders).toHaveTextContent(
                spanish
                    ? "Elige las horas y los días"
                    : "Choose the exact times and days",
            );
            expect(
                screen.queryByText(
                    spanish ? "Tú eliges" : "Patient controlled",
                ),
            ).not.toBeInTheDocument();
            expect(
                screen.getByRole("button", {
                    name: spanish ? "Cerrar sesión" : "Sign out",
                }),
            ).toHaveTextContent(
                spanish ? "compartes tu teléfono" : "shared phone",
            );
            expect(screen.getByText(/911/)).toHaveTextContent(
                spanish
                    ? "no se monitorean continuamente"
                    : "not continuously monitored",
            );
            expect(
                screen.getByRole("button", {
                    name: spanish
                        ? "Agregar un miembro del equipo de atención"
                        : "Add a care team member",
                }),
            ).toBeInTheDocument();
            fireEvent.click(
                screen.getByRole("button", {
                    name: spanish ? "Editar perfil" : "Edit profile",
                }),
            );
            const selects = screen
                .getByRole("dialog")
                .querySelectorAll("select");
            expect(selects).toHaveLength(2);
            selects.forEach((select) =>
                expect(select).toHaveClass(
                    "min-w-0",
                    "pr-10",
                    "min-h-[3.25rem]",
                ),
            );
        },
    );
    it.each(["en-US", "es-MX"] as const)(
        "directs an unlinked patient to the clinic sheet in %s",
        async (locale) => {
            get.mockImplementation(async (endpoint: string) =>
                endpoint === "/api/v1/patients/me"
                    ? profileResponse(locale)
                    : [],
            );
            render(<ProfilePage />);
            const name =
                locale === "es-MX"
                    ? "Agregar tu equipo de atención"
                    : "Add your care team";
            fireEvent.click(await screen.findByRole("button", { name }));
            expect(screen.getByRole("dialog", { name })).toBeInTheDocument();
            expect(
                screen.queryByText(/invite code below/i),
            ).not.toBeInTheDocument();
            expect(post).not.toHaveBeenCalled();
        },
    );
    it("keeps the edit sheet and draft while a profile save is pending", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me" ? profileResponse() : [],
        );
        let rejectSave!: (error: Error) => void;
        put.mockImplementation(
            () =>
                new Promise((_resolve, reject) => {
                    rejectSave = reject;
                }),
        );
        render(<ProfilePage />);
        fireEvent.click(
            await screen.findByRole("button", { name: "Edit profile" }),
        );
        fireEvent.change(screen.getByLabelText("First name"), {
            target: { value: "Updated" },
        });
        fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
        await waitFor(() => expect(put).toHaveBeenCalledOnce());
        fireEvent.keyDown(document, { key: "Escape" });
        fireEvent.click(screen.getByRole("button", { name: "Close" }));
        expect(
            screen.getByRole("dialog", { name: "Personal information" }),
        ).toBeInTheDocument();
        expect(screen.getByLabelText("First name")).toHaveValue("Updated");
        rejectSave(new Error("Unavailable"));
        await waitFor(() =>
            expect(
                screen.getByRole("button", { name: "Save changes" }),
            ).not.toBeDisabled(),
        );
        expect(screen.getByRole("alert")).toBeInTheDocument();
    });
    it("retains pending saves and errors when the language sheet closes", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me" ? profileResponse() : [],
        );
        let rejectSave!: (error: Error) => void;
        put.mockImplementation(
            () =>
                new Promise((_resolve, reject) => {
                    rejectSave = reject;
                }),
        );
        render(
            <PatientProfileProvider>
                <ProfilePage />
            </PatientProfileProvider>,
        );
        fireEvent.click(
            await screen.findByRole("button", { name: "English (US)" }),
        );
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), {
            target: { value: "es-MX" },
        });
        fireEvent.keyDown(document, { key: "Escape" });
        fireEvent.click(screen.getByRole("button", { name: "English (US)" }));
        expect(
            screen.getByRole("combobox", { name: "Language" }),
        ).toBeDisabled();
        expect(put).toHaveBeenCalledOnce();
        fireEvent.keyDown(document, { key: "Escape" });
        rejectSave(new Error("Unavailable"));
        await waitFor(() =>
            expect(
                screen.getByRole("combobox", {
                    name: "Language",
                    hidden: true,
                }),
            ).not.toBeDisabled(),
        );
        fireEvent.click(screen.getByRole("button", { name: "English (US)" }));
        expect(screen.getByRole("alert")).toHaveTextContent(
            "Could not save the language",
        );
    });
    it("keeps language settings available when care teams cannot load", async () => {
        get.mockImplementation(async (endpoint: string) => {
            if (endpoint === "/api/v1/patients/me") return profileResponse();
            throw new Error("Care teams unavailable");
        });
        render(
            <PatientProfileProvider>
                <ProfilePage />
            </PatientProfileProvider>,
        );
        fireEvent.click(
            await screen.findByRole("button", { name: "Preferred language" }),
        );
        await waitFor(() =>
            expect(
                screen.getByRole("combobox", { name: "Language" }),
            ).not.toBeDisabled(),
        );
    });
    it("opens the existing saved-language control in an accessible Profile sheet", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me" ? profileResponse() : [],
        );
        put.mockResolvedValue({ preferred_language: "es-MX" });
        render(
            <PatientProfileProvider>
                <ProfilePage />
                <SharedPreferenceProbe />
            </PatientProfileProvider>,
        );
        const trigger = await screen.findByRole("button", {
            name: "English (US)",
        });
        trigger.focus();
        fireEvent.click(trigger);
        expect(
            screen.getByRole("dialog", { name: "Preferred language" }),
        ).toBeInTheDocument();
        fireEvent.change(screen.getByRole("combobox", { name: "Language" }), {
            target: { value: "es-MX" },
        });
        await waitFor(() =>
            expect(screen.getByTestId("shared-preference")).toHaveTextContent(
                "es-MX",
            ),
        );
        expect(put).toHaveBeenCalledWith(
            "/api/v1/patients/me",
            { preferred_language: "es-MX" },
            { token: "access-token" },
        );
        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: "Español (México)" }),
        ).toHaveFocus();
    });
    beforeEach(() => {
        clearStoredSession.mockReset();
        dispatch.mockReset();
        get.mockReset();
        post.mockReset();
        put.mockReset();
        replace.mockReset();
        searchParamGet.mockReset();
        searchParamGet.mockReturnValue(null);
    });

    it("opens profile editing in a named sheet and returns focus on Escape without saving", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me" ? profileResponse() : [],
        );
        render(<ProfilePage />);
        const trigger = await screen.findByRole("button", {
            name: "Edit profile",
        });
        trigger.focus();
        fireEvent.click(trigger);
        expect(
            screen.getByRole("dialog", { name: "Personal information" }),
        ).toHaveAttribute("aria-modal", "true");
        expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
        expect(screen.getByLabelText("First name")).toBeRequired();
        expect(screen.getByLabelText("Last name")).toBeRequired();
        fireEvent.change(screen.getByLabelText("First name"), {
            target: { value: "Unsaved" },
        });
        fireEvent.keyDown(document, { key: "Escape" });
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
        expect(trigger).toHaveFocus();
        expect(put).not.toHaveBeenCalled();
        fireEvent.click(trigger);
        expect(screen.getByLabelText("First name")).toHaveValue("Synthetic");
        fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
        expect(trigger).toHaveFocus();
    });

    it("retains clinic draft and recovery feedback when reopening the join sheet", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me" ? profileResponse() : [],
        );
        post.mockRejectedValue(new Error("Uncertain transport outcome"));
        render(<ProfilePage />);
        const trigger = await screen.findByRole("button", {
            name: "Add your care team",
        });
        trigger.focus();
        fireEvent.click(trigger);
        expect(
            screen.getByRole("dialog", { name: "Add your care team" }),
        ).toHaveAttribute("aria-modal", "true");
        fireEvent.change(screen.getByLabelText("Invite code"), {
            target: { value: " CITY /8832 " },
        });
        fireEvent.click(screen.getByRole("button", { name: "Add to my care team" }));
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "Refresh to check your care team",
        );
        expect(post).toHaveBeenCalledWith(
            "/api/v1/patients/me/care-team/join?invite_code=CITY%20%2F8832",
            undefined,
            { token: "access-token" },
        );
        fireEvent.keyDown(document, { key: "Escape" });
        expect(trigger).toHaveFocus();
        fireEvent.click(trigger);
        expect(screen.getByLabelText("Invite code")).toHaveValue(
            " CITY /8832 ",
        );
        expect(screen.getByRole("alert")).toHaveTextContent(
            "Refresh to check your care team",
        );
        expect(post).toHaveBeenCalledOnce();
    });

    it("preserves reminder navigation and sign-out session cleanup", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me" ? profileResponse() : [],
        );
        render(<ProfilePage />);
        expect(
            await screen.findByRole("link", { name: "Manage reminders" }),
        ).toHaveAttribute("href", "/reminders");
        document.cookie = "patient-portal.locale=es-MX; Path=/";
        fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
        expect(clearStoredSession).toHaveBeenCalledOnce();
        expect(document.cookie).not.toContain("patient-portal.locale=");
        expect(dispatch).toHaveBeenCalledWith(
            expect.objectContaining({ type: "auth/logout" }),
        );
        expect(replace).toHaveBeenCalledWith("/login");
    });

    it("uses shared saved preference for all profile controls and retained notices", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me"
                ? profileResponse()
                : [
                      {
                          id: "team",
                          role: "registered_nurse",
                          status: "inactive",
                          clinician_first_name: "Synthetic",
                          clinician_last_name: "Nurse",
                      },
                  ],
        );
        const { container } = render(
            <PatientProfileProvider>
                <ProfilePage />
                <SharedPreferenceProbe />
            </PatientProfileProvider>,
        );
        expect(
            await screen.findByText("Synthetic Patient"),
        ).toBeInTheDocument();
        expect(screen.getByText(profileResponse().email)).toHaveClass(
            "break-all",
        );
        expect(screen.getByText("Inactive")).toBeInTheDocument();
        expect(container.querySelector("details")?.open ?? false).toBe(false);
        expect(
            screen.getByRole("button", { name: "Add a care team member" }),
        ).toBeInTheDocument();
        fireEvent.click(
            screen.getByRole("button", { name: "Change saved preference" }),
        );
        expect(
            screen.getByRole("heading", { name: "Perfil" }),
        ).toBeInTheDocument();
        expect(screen.getByText("Inactivo")).toBeInTheDocument();
        expect(
            screen.getByText("Personal de enfermería titulado"),
        ).toBeInTheDocument();
        expect(screen.getByText("Femenino")).toBeInTheDocument();
        expect(screen.getByText(/1985/)).toHaveAttribute("dateTime", "1985-03-15");
        fireEvent.click(screen.getByRole("button", { name: "Editar perfil" }));
        expect(screen.getByLabelText("Idioma preferido")).toHaveValue("es-MX");
        expect(
            screen.getByLabelText("Idioma preferido"),
        ).toHaveAccessibleDescription(/lo aprueba en inglés y en español|los aprueba en inglés y en español/);
        expect(screen.getByLabelText("Nombre")).toHaveValue("Synthetic");
        expect(
            screen.getByRole("option", { name: "Prefiero no decirlo" }),
        ).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: "Cancelar" }));
        expect(
            screen.getByRole("button", { name: "Cerrar sesión" }),
        ).toBeInTheDocument();
    });

    it.each(["en-US", "es-MX"] as const)(
        "notifies shared profile only after a successful save from %s",
        async (initialLocale) => {
            const nextLocale = initialLocale === "en-US" ? "es-MX" : "en-US";
            get.mockImplementation(async (endpoint: string) =>
                endpoint === "/api/v1/patients/me"
                    ? profileResponse(initialLocale)
                    : [],
            );
            put.mockResolvedValue({
                ...profileResponse(nextLocale),
                first_name: "Updated",
            });
            render(
                <PatientProfileProvider>
                    <ProfilePage />
                    <SharedPreferenceProbe />
                </PatientProfileProvider>,
            );
            fireEvent.click(
                await screen.findByRole("button", {
                    name:
                        initialLocale === "en-US"
                            ? "Edit profile"
                            : "Editar perfil",
                }),
            );
            fireEvent.change(
                screen.getByLabelText(
                    initialLocale === "en-US" ? "First name" : "Nombre",
                ),
                { target: { value: "Updated" } },
            );
            fireEvent.change(
                screen.getByLabelText(
                    initialLocale === "en-US"
                        ? "Preferred language"
                        : "Idioma preferido",
                ),
                { target: { value: nextLocale } },
            );
            expect(screen.getByTestId("shared-preference")).toHaveTextContent(
                initialLocale,
            );
            fireEvent.click(
                screen.getByRole("button", {
                    name:
                        initialLocale === "en-US"
                            ? "Save changes"
                            : "Guardar cambios",
                }),
            );
            expect(
                await screen.findByText("Updated Patient"),
            ).toBeInTheDocument();
            expect(screen.getByTestId("shared-preference")).toHaveTextContent(
                nextLocale,
            );
            expect(
                screen.getByText(
                    nextLocale === "es-MX"
                        ? "Tu perfil se actualizó correctamente."
                        : "Profile updated successfully.",
                ),
            ).toHaveAttribute("role", "status");
            expect(screen.getByText(/1985/)).toHaveAttribute("dateTime", "1985-03-15");
            expect(screen.getByTitle("America/Los_Angeles")).toHaveTextContent("Los Angeles");
        },
    );

    it.each(["en-US", "es-MX"] as const)(
        "keeps draft and saved preference on failure in %s",
        async (locale) => {
            get.mockImplementation(async (endpoint: string) =>
                endpoint === "/api/v1/patients/me"
                    ? profileResponse(locale)
                    : [],
            );
            put.mockRejectedValue(
                new Error("internal English transport detail"),
            );
            render(
                <PatientProfileProvider>
                    <ProfilePage />
                    <SharedPreferenceProbe />
                </PatientProfileProvider>,
            );
            fireEvent.click(
                await screen.findByRole("button", {
                    name: locale === "en-US" ? "Edit profile" : "Editar perfil",
                }),
            );
            fireEvent.change(
                screen.getByLabelText(
                    locale === "en-US"
                        ? "Preferred language"
                        : "Idioma preferido",
                ),
                { target: { value: locale === "en-US" ? "es-MX" : "en-US" } },
            );
            fireEvent.click(
                screen.getByRole("button", {
                    name:
                        locale === "en-US" ? "Save changes" : "Guardar cambios",
                }),
            );
            expect(await screen.findByRole("alert")).toHaveTextContent(
                locale === "en-US"
                    ? "Refresh to check your profile"
                    : "Actualiza la página para revisar tu perfil",
            );
            expect(screen.getByTestId("shared-preference")).toHaveTextContent(
                locale,
            );
            expect(
                screen.getByLabelText(
                    locale === "en-US"
                        ? "Preferred language"
                        : "Idioma preferido",
                ),
            ).toHaveValue(locale === "en-US" ? "es-MX" : "en-US");
            expect(
                screen.queryByText("internal English transport detail"),
            ).not.toBeInTheDocument();
            expect(put).toHaveBeenCalledTimes(1);
        },
    );

    it.each([false, true])(
        "opens the clinic sheet only when joinClinic forces it open (%s)",
        async (forceOpen) => {
            searchParamGet.mockReturnValue(forceOpen ? "1" : null);
            get.mockImplementation(async (endpoint: string) =>
                endpoint === "/api/v1/patients/me"
                    ? profileResponse()
                    : [
                          {
                              id: "active",
                              role: "physician",
                              status: "active",
                              clinician_first_name: "Synthetic",
                              clinician_last_name: "Clinician",
                          },
                          {
                              id: "transferred",
                              role: "pharmacist",
                              status: "transferred",
                              clinician_first_name: "Synthetic",
                              clinician_last_name: "Pharmacist",
                          },
                      ],
            );
            const { container } = render(<ProfilePage />);
            expect(
                await screen.findByText("Synthetic Clinician"),
            ).toBeInTheDocument();
            expect(container.querySelector("details")?.open ?? false).toBe(
                false,
            );
            if (forceOpen) {
                expect(
                    screen.getByRole("dialog", {
                        name: "Add a care team member",
                    }),
                ).toBeInTheDocument();
                fireEvent.keyDown(document, { key: "Escape" });
                // The sheet unmounts after its close animation; a slow CI runner can
                // take longer than the default one-second wait.
                await waitFor(
                    () =>
                        expect(
                            screen.queryByRole("dialog"),
                        ).not.toBeInTheDocument(),
                    { timeout: 3000 },
                );
            } else {
                expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
            }
            expect(screen.getByText("Linked")).toBeInTheDocument();
            expect(screen.getByText("Transferred")).toBeInTheDocument();
            expect(
                screen.getByRole("link", { name: "Message your care team" }),
            ).toHaveAttribute("href", "/chat");
        },
    );

    it("localizes load failures and retry from saved shared preference", async () => {
        get.mockImplementation(async (endpoint: string) => {
            if (endpoint === "/api/v1/patients/me")
                return profileResponse("es-MX");
            throw new Error("Internal care-team error");
        });
        render(
            <PatientProfileProvider>
                <ProfilePage />
            </PatientProfileProvider>,
        );
        expect(
            await screen.findByText("No se pudo cargar tu perfil"),
        ).toBeInTheDocument();
        expect(
            screen.getByRole("button", { name: "Intentar de nuevo" }),
        ).toBeInTheDocument();
        expect(
            screen.queryByText("Internal care-team error"),
        ).not.toBeInTheDocument();
    });

    it("localizes clinic validation and errors in Spanish without exposing server copy", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me" ? profileResponse("es-MX") : [],
        );
        post.mockRejectedValue(new Error("Invalid or expired invite code"));
        render(<ProfilePage />);
        fireEvent.click(
            await screen.findByRole("button", {
                name: "Agregar tu equipo de atención",
            }),
        );
        const invite = await screen.findByLabelText(
            "Código de invitación",
        );
        expect(invite).toHaveAccessibleDescription(
            "Usa el código que te dio tu clínico.",
        );
        fireEvent.click(
            screen.getByRole("button", { name: "Agregar a mi equipo" }),
        );
        expect(screen.getByRole("alert")).toHaveTextContent(
            "Ingresa un código de invitación para continuar.",
        );
        expect(post).not.toHaveBeenCalled();
        fireEvent.change(invite, { target: { value: "BAD-CODE" } });
        fireEvent.click(
            screen.getByRole("button", { name: "Agregar a mi equipo" }),
        );
        expect(await screen.findByRole("alert")).toHaveTextContent(
            "El código de invitación no es válido o ya venció",
        );
        expect(
            screen.queryByText("Invalid or expired invite code"),
        ).not.toBeInTheDocument();
    });

    it.each([
        ["en-US", "Assigned care provider", "Care team member"],
        [
            "es-MX",
            "Profesional de atención asignado",
            "Integrante del equipo de atención",
        ],
    ])(
        "renders translated care-team roles in %s without raw codes",
        async (locale, assigned, fallback) => {
            get.mockImplementation(async (endpoint: string) =>
                endpoint === "/api/v1/patients/me"
                    ? {
                          id: "synthetic-patient",
                          first_name: "Synthetic",
                          last_name: "Patient",
                          email: "synthetic@example.com",
                          date_of_birth: "1985-03-15",
                          created_at: "2026-01-10T00:00:00Z",
                          preferred_language: locale,
                      }
                    : ["assigned_provider", "unknown_internal_role"].map(
                          (role, index) => ({
                              id: `synthetic-team-${index}`,
                              clinician_first_name: "Synthetic",
                              clinician_last_name: "Provider",
                              role,
                              status: "active",
                          }),
                      ),
            );
            render(<ProfilePage />);
            expect(await screen.findByText(assigned!)).toBeInTheDocument();
            expect(screen.getByText(fallback!)).toBeInTheDocument();
            expect(
                screen.queryByText("assigned_provider"),
            ).not.toBeInTheDocument();
            expect(
                screen.queryByText("unknown_internal_role"),
            ).not.toBeInTheDocument();
        },
    );

    it("loads profile details and the linked care team", async () => {
        get.mockImplementation(async (endpoint: string) => {
            if (endpoint === "/api/v1/patients/me") {
                return {
                    created_at: "2026-01-10T00:00:00Z",
                    date_of_birth: "1985-03-15",
                    email: "sarah@example.com",
                    first_name: "Sarah",
                    id: "patient-1",
                    last_name: "Johnson",
                    preferred_language: "en-US",
                };
            }

            return [
                {
                    clinician_first_name: "Emily",
                    clinician_id: "clinician-1",
                    clinician_last_name: "Smith",
                    clinic_name: "City Health",
                    created_at: "2026-01-10T00:00:00Z",
                    id: "care-team-1",
                    patient_id: "patient-1",
                    role: "Primary Care",
                    status: "active",
                },
            ];
        });

        render(<ProfilePage />);

        expect(await screen.findByText("Sarah Johnson")).toBeInTheDocument();
        expect(screen.getByText("sarah@example.com")).toBeInTheDocument();
        expect(screen.getByText("Emily Smith")).toBeInTheDocument();
        expect(screen.getByText("City Health")).toBeInTheDocument();
    });

    it("persists profile edits through the patient API", async () => {
        get.mockImplementation(async (endpoint: string) => {
            if (endpoint === "/api/v1/patients/me") {
                return {
                    created_at: "2026-01-10T00:00:00Z",
                    date_of_birth: "1985-03-15",
                    email: "sarah@example.com",
                    first_name: "Sarah",
                    id: "patient-1",
                    last_name: "Johnson",
                    preferred_language: "en-US",
                };
            }

            return [];
        });
        put.mockResolvedValue({
            created_at: "2026-01-10T00:00:00Z",
            date_of_birth: "1985-03-15",
            email: "sarah@example.com",
            first_name: "Sara",
            gender: "female",
            id: "patient-1",
            last_name: "Johnson",
            preferred_language: "es-MX",
        });

        render(<ProfilePage />);

        fireEvent.click(
            await screen.findByRole("button", { name: /edit profile/i }),
        );
        fireEvent.change(screen.getByLabelText(/^first name$/i), {
            target: { value: "Sara" },
        });
        fireEvent.change(screen.getByLabelText(/^preferred language$/i), {
            target: { value: "es-MX" },
        });
        fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

        await waitFor(() => {
            expect(put).toHaveBeenCalledWith(
                "/api/v1/patients/me",
                {
                    first_name: "Sara",
                    gender: null,
                    last_name: "Johnson",
                    preferred_language: "es-MX",
                },
                { token: "access-token" },
            );
        });

        expect(
            await screen.findByText("Tu perfil se actualizó correctamente."),
        ).toBeInTheDocument();
        expect(screen.getByText("Sara Johnson")).toBeInTheDocument();
        expect(screen.getByText("Femenino")).toBeInTheDocument();
    });

    it("clears a saved gender when the patient chooses Not specified", async () => {
        const savedProfile = {
            created_at: "2026-01-10T00:00:00Z",
            date_of_birth: "1958-03-02",
            email: "morgan@example.com",
            first_name: "Morgan",
            gender: "female",
            id: "patient-1",
            last_name: "Lee",
            preferred_language: "en-US",
        };
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me" ? savedProfile : [],
        );
        put.mockResolvedValue({ ...savedProfile, gender: null });

        render(<ProfilePage />);

        expect(await screen.findByText("Female")).toBeInTheDocument();
        fireEvent.click(screen.getByRole("button", { name: /edit profile/i }));
        fireEvent.change(screen.getByLabelText(/^gender/i), {
            target: { value: "" },
        });
        fireEvent.click(screen.getByRole("button", { name: /save changes/i }));

        await waitFor(() => {
            expect(put).toHaveBeenCalledWith(
                "/api/v1/patients/me",
                {
                    first_name: "Morgan",
                    gender: null,
                    last_name: "Lee",
                    preferred_language: "en-US",
                },
                { token: "access-token" },
            );
        });
        expect(
            await screen.findByText("Profile updated successfully."),
        ).toBeInTheDocument();
        expect(screen.queryByText("Female")).not.toBeInTheDocument();
        expect(screen.queryByText(/^gender$/i)).not.toBeInTheDocument();
    });

    it("lets the patient join another clinic after onboarding", async () => {
        let careTeamResponse: Array<Record<string, string>> = [];
        get.mockImplementation(async (endpoint: string) => {
            if (endpoint === "/api/v1/patients/me") {
                return {
                    created_at: "2026-01-10T00:00:00Z",
                    date_of_birth: "1985-03-15",
                    email: "sarah@example.com",
                    first_name: "Sarah",
                    id: "patient-1",
                    last_name: "Johnson",
                    preferred_language: "en-US",
                };
            }

            return careTeamResponse;
        });
        post.mockImplementationOnce(async () => {
            careTeamResponse = [
                {
                    clinician_first_name: "Amir",
                    clinician_id: "clinician-2",
                    clinician_last_name: "Khan",
                    clinic_name: "Northside Clinic",
                    created_at: "2026-02-11T00:00:00Z",
                    id: "care-team-2",
                    patient_id: "patient-1",
                    role: "Cardiology",
                    status: "active",
                },
            ];
            return {};
        });

        render(<ProfilePage />);

        expect(
            await screen.findByText(/no care teams linked yet/i),
        ).toBeInTheDocument();

        fireEvent.click(
            screen.getByRole("button", { name: "Add your care team" }),
        );
        fireEvent.change(await screen.findByLabelText(/^invite code$/i), {
            target: { value: "NORTH-8832" },
        });
        fireEvent.click(
            await screen.findByRole("button", { name: /add to my care team/i }),
        );

        await waitFor(() => {
            expect(post).toHaveBeenCalledWith(
                "/api/v1/patients/me/care-team/join?invite_code=NORTH-8832",
                undefined,
                { token: "access-token" },
            );
        });

        expect(
            await screen.findByText(/added to your care team/i),
        ).toBeInTheDocument();
        expect(await screen.findByText("Amir Khan")).toBeInTheDocument();
        expect(screen.getByText("Northside Clinic")).toBeInTheDocument();
    });

    it.each([
        ["en-US", "Add a care team member", "Enter the invite code your clinician gave you."],
        ["es-MX", "Agregar un miembro del equipo de atención", "Ingresa el código de invitación que te dio tu clínico."],
    ])("words the add flow as adding a care team member, not joining a clinic (%s)", async (locale, title, help) => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me"
                ? { ...profileResponse(locale as "en-US" | "es-MX") }
                : [{ clinician_first_name: "Amir", clinician_id: "c2", clinician_last_name: "Khan", clinic_name: "Northside Clinic", created_at: "2026-02-11T00:00:00Z", id: "ct-2", patient_id: "patient-1", role: "Cardiology", status: "active" }],
        );
        render(<ProfilePage />);
        fireEvent.click(await screen.findByRole("button", { name: title }));
        expect(screen.getByRole("dialog", { name: title })).toBeInTheDocument();
        expect(screen.getByText(help)).toBeInTheDocument();
        expect(screen.queryByText(/join another clinic|vincular otra cl/i)).not.toBeInTheDocument();
    });

    it("keeps a flat list with the clinic in the subtitle for one clinic", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me"
                ? profileResponse()
                : [
                    { clinician_first_name: "Amir", clinician_id: "c2", clinician_last_name: "Khan", clinic_name: "Northside Clinic", created_at: "2026-02-11T00:00:00Z", id: "ct-2", patient_id: "patient-1", role: "Cardiology", status: "active" },
                    { clinician_first_name: "Priya", clinician_id: "c3", clinician_last_name: "Nair", clinic_name: "Northside Clinic", created_at: "2026-02-11T00:00:00Z", id: "ct-3", patient_id: "patient-1", role: "Nursing", status: "active" },
                ],
        );
        render(<ProfilePage />);
        await screen.findByText("Amir Khan");
        expect(screen.queryByRole("heading", { level: 4 })).not.toBeInTheDocument();
        expect(screen.getAllByText("Northside Clinic")).toHaveLength(2);
    });

    it("groups care team rows under clinic headings when the team spans two clinics", async () => {
        get.mockImplementation(async (endpoint: string) =>
            endpoint === "/api/v1/patients/me"
                ? profileResponse()
                : [
                    { clinician_first_name: "Amir", clinician_id: "c2", clinician_last_name: "Khan", clinic_name: "Northside Clinic", created_at: "2026-02-11T00:00:00Z", id: "ct-2", patient_id: "patient-1", role: "Cardiology", status: "active" },
                    { clinician_first_name: "Priya", clinician_id: "c3", clinician_last_name: "Nair", clinic_name: "Willow Terrace", created_at: "2026-02-11T00:00:00Z", id: "ct-3", patient_id: "patient-1", role: "Nursing", status: "active" },
                    { clinician_first_name: "Elena", clinician_id: "c4", clinician_last_name: "Park", clinic_name: "Willow Terrace", created_at: "2026-02-11T00:00:00Z", id: "ct-4", patient_id: "patient-1", role: "Cardiology", status: "active" },
                ],
        );
        render(<ProfilePage />);
        await screen.findByText("Amir Khan");
        const headings = screen.getAllByRole("heading", { level: 4 }).map((h) => h.textContent);
        expect(headings).toEqual(["Northside Clinic", "Willow Terrace"]);
        // The clinic is the heading, so it is not repeated in each row.
        expect(screen.getAllByText("Willow Terrace")).toHaveLength(1);
    });

    it("surfaces invite-code errors without leaving the page", async () => {
        get.mockImplementation(async (endpoint: string) => {
            if (endpoint === "/api/v1/patients/me") {
                return {
                    created_at: "2026-01-10T00:00:00Z",
                    date_of_birth: "1985-03-15",
                    email: "sarah@example.com",
                    first_name: "Sarah",
                    id: "patient-1",
                    last_name: "Johnson",
                    preferred_language: "en-US",
                };
            }

            return [];
        });
        post.mockRejectedValueOnce(new Error("Invalid or expired invite code"));

        render(<ProfilePage />);

        expect(
            await screen.findByText(/no care teams linked yet/i),
        ).toBeInTheDocument();

        fireEvent.click(
            screen.getByRole("button", { name: "Add your care team" }),
        );
        fireEvent.change(await screen.findByLabelText(/^invite code$/i), {
            target: { value: "BAD-CODE" },
        });
        fireEvent.click(
            await screen.findByRole("button", { name: /add to my care team/i }),
        );

        expect(
            await screen.findByText(/invalid or expired invite code/i),
        ).toBeInTheDocument();
        expect(replace).not.toHaveBeenCalledWith("/login");
    });

    it("shows onboarding join prompt when redirected from login", async () => {
        searchParamGet.mockImplementation((key: string) =>
            key === "joinClinic" ? "1" : null,
        );
        get.mockImplementation(async (endpoint: string) => {
            if (endpoint === "/api/v1/patients/me") {
                return {
                    created_at: "2026-01-10T00:00:00Z",
                    date_of_birth: "1985-03-15",
                    email: "sarah@example.com",
                    first_name: "Sarah",
                    id: "patient-1",
                    last_name: "Johnson",
                    preferred_language: "en-US",
                };
            }

            return [];
        });

        render(<ProfilePage />);

        expect(
            await screen.findByText(/no active care team is linked yet/i),
        ).toBeInTheDocument();
    });
});
