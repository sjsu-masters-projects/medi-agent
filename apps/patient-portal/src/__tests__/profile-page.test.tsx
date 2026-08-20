import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ProfilePage from "@/app/(app)/profile/page";

const { clearStoredSession, dispatch, get, post, put, replace, searchParamGet } = vi.hoisted(() => ({
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

describe("Patient profile page", () => {
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
                    preferred_language: "en",
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
        expect(screen.getByText("Dr. Emily Smith")).toBeInTheDocument();
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
                    preferred_language: "en",
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

        fireEvent.click(await screen.findByRole("button", { name: /edit profile/i }));
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
                    last_name: "Johnson",
                    preferred_language: "es-MX",
                },
                { token: "access-token" },
            );
        });

        expect(await screen.findByText(/profile updated successfully/i)).toBeInTheDocument();
        expect(screen.getByText("Sara Johnson")).toBeInTheDocument();
        expect(screen.getByText("Female")).toBeInTheDocument();
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
                    preferred_language: "en",
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

        expect(await screen.findByText(/no care teams linked yet/i)).toBeInTheDocument();

        fireEvent.change(await screen.findByLabelText(/clinic invite code/i), {
            target: { value: "NORTH-8832" },
        });
        fireEvent.click(await screen.findByRole("button", { name: /join clinic/i }));

        await waitFor(() => {
            expect(post).toHaveBeenCalledWith(
                "/api/v1/patients/me/care-team/join?invite_code=NORTH-8832",
                undefined,
                { token: "access-token" },
            );
        });

        expect(await screen.findByText(/clinic linked successfully/i)).toBeInTheDocument();
        expect(await screen.findByText("Dr. Amir Khan")).toBeInTheDocument();
        expect(screen.getByText("Northside Clinic")).toBeInTheDocument();
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
                    preferred_language: "en",
                };
            }

            return [];
        });
        post.mockRejectedValueOnce(new Error("Invalid or expired invite code"));

        render(<ProfilePage />);

        expect(await screen.findByText(/no care teams linked yet/i)).toBeInTheDocument();

        fireEvent.change(await screen.findByLabelText(/clinic invite code/i), {
            target: { value: "BAD-CODE" },
        });
        fireEvent.click(await screen.findByRole("button", { name: /join clinic/i }));

        expect(await screen.findByText(/invalid or expired invite code/i)).toBeInTheDocument();
        expect(replace).not.toHaveBeenCalledWith("/login");
    });

    it("shows onboarding join prompt when redirected from login", async () => {
        searchParamGet.mockImplementation((key: string) => (key === "joinClinic" ? "1" : null));
        get.mockImplementation(async (endpoint: string) => {
            if (endpoint === "/api/v1/patients/me") {
                return {
                    created_at: "2026-01-10T00:00:00Z",
                    date_of_birth: "1985-03-15",
                    email: "sarah@example.com",
                    first_name: "Sarah",
                    id: "patient-1",
                    last_name: "Johnson",
                    preferred_language: "en",
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
