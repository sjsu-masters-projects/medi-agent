import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import ReminderSettingsPage from "@/app/(app)/reminders/page";

const { get, put, remove } = vi.hoisted(() => ({
  get: vi.fn(),
  put: vi.fn(),
  remove: vi.fn(),
}));
vi.mock("@/services/api", () => ({ api: { get, put, delete: remove } }));
vi.mock("react-redux", () => ({ useSelector: () => "synthetic-token" }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ back: vi.fn() }) }));
vi.mock("@/services/timezones", () => ({
  getBrowserTimezone: () => "America/Los_Angeles",
  getSupportedTimezones: () => ["America/Los_Angeles", "America/New_York"],
}));

function target(id: string, name: string, automatic = true) {
  return {
    target_type: "obligation",
    target_id: id,
    name,
    frequency: automatic
      ? "three times per week"
      : "after each walking session",
    description: "Follow the clinician-approved instruction.",
    reminder_schedule: null,
    guidance: {
      supports_automatic_reminders: automatic,
      recommended_times_per_day: automatic ? 1 : null,
      recommended_days_per_week: automatic ? 3 : null,
      guidance_text: "Use the approved frequency.",
    },
  };
}

const profileSettings = vi.hoisted(() => ({
  locale: "en-US" as "en-US" | "es-MX",
}));
vi.mock("@/hooks/use-patient-profile", () => ({
  usePatientProfile: () => ({
    preferredLanguage: profileSettings.locale,
    timezone: "America/Los_Angeles",
  }),
  useSharedPatientProfile: () => null,
}));

describe("Reminder settings", () => {
  it.each(["en-US", "es-MX"] as const)(
    "suppresses only exact trimmed title/instruction duplicates in %s",
    async (locale) => {
      profileSettings.locale = locale;
      const repeated = "Caminar durante veinte minutos";
      const distinct = "Caminar durante veinte minutos después de comer";
      const caseDistinct = "caminar durante veinte minutos";
      const frequencyInstruction = "tres veces por semana";
      get.mockResolvedValue([
        { ...target("repeated", repeated), description: `  ${repeated}  ` },
        { ...target("distinct", "Movimiento diario"), description: distinct },
        {
          ...target("case-distinct", "Actividad diaria"),
          description: caseDistinct,
        },
        {
          ...target("frequency", "Horario de actividad"),
          frequency: frequencyInstruction,
          description: frequencyInstruction,
        },
      ]);
      render(<ReminderSettingsPage />);
      await screen.findByRole("heading", { name: repeated });
      expect(screen.getAllByText(repeated)).toHaveLength(1);
      expect(screen.getByText(distinct)).toBeInTheDocument();
      expect(screen.getByText(caseDistinct)).toBeInTheDocument();
      expect(screen.getAllByText(frequencyInstruction)).toHaveLength(2);
      expect(put).not.toHaveBeenCalled();
    },
  );
  beforeEach(() => {
    profileSettings.locale = "en-US";
    vi.clearAllMocks();
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/me")
          ? { timezone: "America/Los_Angeles" }
          : [
              target("walk", "Walking"),
              target("check", "After-walking check", false),
            ],
      ),
    );
    put.mockResolvedValue({});
    remove.mockResolvedValue({});
  });

  it("starts with summaries, advanced timezone settings, and no open time editor", async () => {
    render(<ReminderSettingsPage />);
    await screen.findByText("Walking");
    expect(screen.queryByLabelText("Reminder time 1")).not.toBeInTheDocument();
    expect(
      screen.getByText(/Advanced settings/).closest("details"),
    ).not.toHaveAttribute("open");
    expect(
      screen.getAllByRole("button", { name: "Set reminder" }),
    ).toHaveLength(1);
    expect(screen.getByText("No routine reminder")).toBeInTheDocument();
  });

  it("keeps explicitly prescribed weekdays selected and locked", async () => {
    const entry = target("walk", "Walking");
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/me")
          ? { timezone: "America/Los_Angeles" }
          : [
              {
                ...entry,
                guidance: {
                  ...entry.guidance,
                  required_days_of_week: ["monday", "wednesday", "friday"],
                },
              },
            ],
      ),
    );
    render(<ReminderSettingsPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Set reminder" }),
    );
    for (const day of ["mon", "wed", "fri"]) {
      expect(screen.getByRole("checkbox", { name: day })).toBeChecked();
      expect(screen.getByRole("checkbox", { name: day })).toBeDisabled();
    }
    expect(screen.getByRole("checkbox", { name: "tue" })).not.toBeChecked();
    expect(screen.getByRole("checkbox", { name: "tue" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reminder time 1"), {
      target: { value: "18:30" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save reminder schedule" }),
    );
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith(
        "/api/v1/reminders/obligation/walk",
        expect.objectContaining({
          days_of_week: ["monday", "wednesday", "friday"],
        }),
        { token: "synthetic-token" },
      ),
    );
  });

  it("requires patient-selected days and time and saves the exact choices", async () => {
    render(<ReminderSettingsPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Set reminder" }),
    );
    const input = screen.getByLabelText("Reminder time 1");
    expect(input).toHaveValue("");
    expect(
      screen.getByRole("button", { name: "Save reminder schedule" }),
    ).toBeDisabled();
    for (const day of ["mon", "wed", "fri"])
      fireEvent.click(screen.getByRole("checkbox", { name: day }));
    fireEvent.change(input, { target: { value: "18:30" } });
    fireEvent.click(
      screen.getByRole("button", { name: "Save reminder schedule" }),
    );
    await waitFor(() =>
      expect(put).toHaveBeenCalledWith(
        "/api/v1/reminders/obligation/walk",
        {
          timezone: "America/Los_Angeles",
          times_of_day: ["18:30"],
          days_of_week: ["monday", "wednesday", "friday"],
          is_enabled: true,
        },
        { token: "synthetic-token" },
      ),
    );
    await waitFor(() =>
      expect(
        screen.queryByLabelText("Reminder time 1"),
      ).not.toBeInTheDocument(),
    );
  });

  it("allows one editor at a time and cancel discards unsaved preferences", async () => {
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/me")
          ? { timezone: "America/Los_Angeles" }
          : [target("walk", "Walking"), target("water", "Hydration")],
      ),
    );
    render(<ReminderSettingsPage />);
    const buttons = await screen.findAllByRole("button", {
      name: "Set reminder",
    });
    fireEvent.click(buttons[0]);
    expect(screen.getByRole("button", { name: "Set reminder" })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Reminder time 1"), {
      target: { value: "12:45" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Set reminder" })[0]);
    expect(screen.getByLabelText("Reminder time 1")).toHaveValue("");
    expect(put).not.toHaveBeenCalled();
  });

  it("retains an existing timezone and offers removal of unsafe legacy reminders without an editor", async () => {
    const entry = {
      ...target("check", "After-walking check", false),
      reminder_schedule: {
        id: "schedule",
        patient_id: "synthetic",
        target_type: "obligation",
        target_id: "check",
        timezone: "America/New_York",
        times_of_day: ["17:30:00"],
        days_of_week: ["monday"],
        is_enabled: true,
        created_at: "2026-10-02",
      },
    };
    get.mockImplementation((path: string) =>
      Promise.resolve(
        path.endsWith("/me") ? { timezone: "America/Los_Angeles" } : [entry],
      ),
    );
    render(<ReminderSettingsPage />);
    await screen.findByText("After-walking check");
    expect(
      screen.getByText("17:30").closest("div"),
    ).toHaveTextContent(/Mon.*17:30.*Eastern Time · New York/);
    expect(screen.getByText("Review old reminder")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Edit reminder" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear schedule" }));
    await waitFor(() =>
      expect(remove).toHaveBeenCalledWith(
        "/api/v1/reminders/obligation/check",
        { token: "synthetic-token" },
      ),
    );
  });

  it("preserves entered preferences on a save error", async () => {
    put.mockRejectedValue(new Error("Synthetic save failed"));
    render(<ReminderSettingsPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Set reminder" }),
    );
    for (const day of ["mon", "wed", "fri"])
      fireEvent.click(screen.getByRole("checkbox", { name: day }));
    fireEvent.change(screen.getByLabelText("Reminder time 1"), {
      target: { value: "18:30" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Save reminder schedule" }),
    );
    await screen.findByText(/We could not confirm your change/);
    expect(screen.queryByText("Synthetic save failed")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Reminder time 1")).toHaveValue("18:30");
    expect(
      screen.getByRole("button", { name: "Save reminder schedule" }),
    ).toBeEnabled();
  });

  it("localizes the editor and saved weekdays while preserving clinical source wording", async () => {
    profileSettings.locale = "es-MX";
    render(<ReminderSettingsPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Configurar recordatorio" }),
    );
    expect(
      screen.getAllByText("Follow the clinician-approved instruction."),
    ).toHaveLength(2);
    expect(screen.getByText("three times per week")).toBeInTheDocument();
    for (const day of ["lun", "mié", "vie"])
      fireEvent.click(screen.getByRole("checkbox", { name: day }));
    fireEvent.change(screen.getByLabelText("Hora del recordatorio 1"), {
      target: { value: "18:30" },
    });
    put.mockRejectedValue(new Error("private schedule_constraint"));
    fireEvent.click(
      screen.getByRole("button", { name: "Guardar recordatorio" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No pudimos confirmar el cambio",
    );
    expect(screen.getByLabelText("Hora del recordatorio 1")).toHaveValue(
      "18:30",
    );
    expect(screen.queryByText(/schedule_constraint/)).not.toBeInTheDocument();
    expect(
      get.mock.calls.some(([path]) => path === "/api/v1/patients/me"),
    ).toBe(false);
  });

  it("keeps an open draft when the saved interface language changes", async () => {
    const view = render(<ReminderSettingsPage />);
    fireEvent.click(
      await screen.findByRole("button", { name: "Set reminder" }),
    );
    fireEvent.change(screen.getByLabelText("Reminder time 1"), {
      target: { value: "18:30" },
    });
    profileSettings.locale = "es-MX";
    view.rerender(<ReminderSettingsPage />);
    expect(screen.getByLabelText("Hora del recordatorio 1")).toHaveValue(
      "18:30",
    );
    expect(
      screen.getByRole("button", { name: "Guardar recordatorio" }),
    ).toBeDisabled();
    expect(put).not.toHaveBeenCalled();
  });

  it("shows an honest Spanish empty state and allows an explicit refresh", async () => {
    profileSettings.locale = "es-MX";
    get.mockResolvedValue([]);
    render(<ReminderSettingsPage />);
    expect(
      await screen.findByText("No hay recordatorios para configurar"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Actualizar recordatorios" }),
    );
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
  });
});
