import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PatientLanguageControl } from "@/components/layouts/patient-language-control";
import { BottomNav } from "@/components/layouts/bottom-nav";
import { PatientProfileProvider, usePatientProfile } from "@/hooks/use-patient-profile";

const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
let token: string | null;
vi.mock("@/services/api", () => ({ api: { get, put } }));
vi.mock("react-redux", () => ({ useSelector: (selector: (state: unknown) => unknown) => selector({ auth: { accessToken: token } }) }));
const raw = { id: "synthetic", first_name: "Morgan", last_name: "Ellis", email: "synthetic@example.test", date_of_birth: "1985-03-15", preferred_language: "en-US", timezone: "America/Los_Angeles" };
function Consumer() { const profile = usePatientProfile(); return <p data-testid="consumer">{profile?.preferredLanguage ?? "loading"}</p>; }
function Portal() { return <PatientProfileProvider><PatientLanguageControl /><Consumer /><Consumer /><BottomNav currentPath="/today" /></PatientProfileProvider>; }
beforeEach(() => { token = "synthetic-token"; get.mockReset(); put.mockReset(); get.mockResolvedValue(raw); document.documentElement.lang = "en-US"; });

describe("Portal language preference", () => {
  it("keeps the saved document language without a repeated screen control", async () => {
    get.mockResolvedValue({ ...raw, preferred_language: "es-MX" });
    render(<PatientProfileProvider><PatientLanguageControl visible={false} /><Consumer /><BottomNav currentPath="/today" /></PatientProfileProvider>);
    await waitFor(() => expect(document.documentElement.lang).toBe("es-MX"));
    expect(screen.queryByRole("combobox")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Hoy" })).toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();
  });
  it("offers a bilingual recovery action when the preference cannot be loaded", async () => {
    get.mockRejectedValueOnce(new Error("synthetic load failure"));
    render(<Portal />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Idioma no disponible");
    expect(screen.getByRole("combobox")).toBeDisabled();
    get.mockResolvedValueOnce({ ...raw, preferred_language: "es-MX" });
    fireEvent.click(screen.getByRole("button", { name: "Try again / Reintentar" }));
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveValue("es-MX"));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(put).not.toHaveBeenCalled();
  });
  it("loads one shared profile and updates all mounted consumers only after a saved change", async () => {
    let save!: (value: unknown) => void;
    put.mockReturnValue(new Promise((resolve) => { save = resolve; }));
    render(<Portal />);
    await screen.findByRole("combobox", { name: "Language" });
    await waitFor(() => expect(screen.getAllByTestId("consumer")[0]).toHaveTextContent("en-US"));
    expect(get).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "es-MX" } });
    expect(screen.getByRole("combobox")).toBeDisabled();
    expect(screen.getAllByTestId("consumer")[0]).toHaveTextContent("en-US");
    await act(async () => save({ preferred_language: "es-MX" }));
    expect(screen.getAllByTestId("consumer").every((node) => node.textContent === "es-MX")).toBe(true);
    expect(screen.getByRole("link", { name: "Hoy" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Registros" })).toBeInTheDocument();
    expect(document.documentElement.lang).toBe("es-MX");
    expect(put).toHaveBeenCalledWith("/api/v1/patients/me", { preferred_language: "es-MX" }, { token: "synthetic-token" });
  });

  it("keeps the saved language after failure and explains medical-text boundaries", async () => {
    put.mockRejectedValue(new Error("synthetic failure"));
    render(<Portal />);
    await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "es-MX" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("preference is unchanged");
    expect(screen.getByRole("combobox")).toHaveValue("en-US");
    expect(screen.getByText(/Medical instructions and previous messages keep their original wording/)).toBeInTheDocument();
    expect(put).toHaveBeenCalledTimes(1);
  });

  it("does not apply a late language save to a different session", async () => {
    let save!: (value: unknown) => void;
    put.mockReturnValue(new Promise((resolve) => { save = resolve; }));
    const { rerender } = render(<Portal />);
    await waitFor(() => expect(screen.getByRole("combobox")).toBeEnabled());
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "es-MX" } });
    token = "new-synthetic-token";
    get.mockResolvedValue({ ...raw, id: "other-synthetic" });
    rerender(<Portal />);
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    await act(async () => save({ preferred_language: "es-MX" }));
    expect(screen.getAllByTestId("consumer").every((node) => node.textContent === "en-US")).toBe(true);
  });
});
