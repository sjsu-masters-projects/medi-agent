import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import VisitsPage from "@/app/(app)/visits/page";
import { AppointmentStatus, type Appointment } from "@/types";

const respond = vi.fn();
const retrySettings = vi.fn();
let settings: {
  profile: { preferredLanguage: "en-US" | "es-MX"; timezone: string } | null;
  loading: boolean;
  error: boolean;
  timezoneMissing: boolean;
  refresh: typeof retrySettings;
};
vi.mock("@/hooks/use-patient-profile", () => ({
  usePatientProfileState: () => settings,
}));

interface VisitsHookState {
  accessToken?: string;
  visits: Appointment[];
  loading: boolean;
  error: string | null;
  actionError: string | null;
  respond: typeof respond;
  respondingId: string | null;
  refresh: () => void;
}

let hookState: VisitsHookState;

vi.mock("next/navigation", () => ({
  useRouter: () => ({ back: vi.fn(), push: vi.fn() }),
}));

vi.mock("@/hooks/use-visits-data", () => ({
  useVisitsData: () => hookState,
}));

function makeVisit(overrides: Partial<Appointment> = {}): Appointment {
  return {
    id: "appt-1",
    patientId: "pt-1",
    careTeamId: "ct-1",
    clinicianName: "Elena Park",
    scheduledAt: "2026-05-08T17:00:00Z",
    durationMinutes: 30,
    appointmentType: "follow_up",
    status: AppointmentStatus.PROPOSED,
    createdAt: "2026-05-07T10:00:00Z",
    reason: "Blood pressure check",
    ...overrides,
  };
}

beforeEach(() => {
  respond.mockReset();
  retrySettings.mockReset();
  settings = {
    profile: { preferredLanguage: "en-US", timezone: "America/Los_Angeles" },
    loading: false,
    error: false,
    timezoneMissing: false,
    refresh: retrySettings,
  };
  hookState = {
    visits: [],
    loading: false,
    error: null,
    actionError: null,
    respond,
    respondingId: null,
    refresh: vi.fn(),
  };
});

describe("VisitsPage", () => {
  it.each(["en-US", "es-MX"] as const)(
    "offers calendar export only for booked visits in %s",
    (locale) => {
      settings.profile!.preferredLanguage = locale;
      hookState.accessToken = "synthetic-session";
      hookState.visits = Object.values(AppointmentStatus).map((status, index) =>
        makeVisit({ id: `visit-${index}`, status }),
      );
      render(<VisitsPage />);
      expect(
        screen.getAllByRole("button", {
          name:
            locale === "es-MX" ? "Agregar al calendario" : "Add to calendar",
        }),
      ).toHaveLength(2);
    },
  );
  it.each([
    [
      "en-US",
      "APPOINTMENT_CONFLICT",
      "This time overlaps another booked visit",
    ],
    [
      "es-MX",
      "APPOINTMENT_CONFLICT",
      "Este horario se empalma con otra cita programada",
    ],
    ["en-US", "APPOINTMENT_EXPIRED", "This offer has expired"],
    ["es-MX", "APPOINTMENT_EXPIRED", "Esta propuesta venció"],
    [
      "en-US",
      "APPOINTMENT_UNAVAILABLE",
      "This appointment is no longer available",
    ],
    ["es-MX", "APPOINTMENT_UNAVAILABLE", "Esta cita ya no está disponible"],
    ["en-US", "APPOINTMENT_PAST", "This appointment time has passed"],
    ["es-MX", "APPOINTMENT_PAST", "El horario de esta cita ya pasó"],
  ] as const)(
    "shows localized %s %s errors and keeps visits visible",
    (locale, code, message) => {
      settings.profile!.preferredLanguage = locale;
      hookState.visits = [makeVisit()];
      hookState.actionError = code;
      render(<VisitsPage />);
      expect(screen.getByRole("alert")).toHaveTextContent(message);
      expect(screen.getByText("Blood pressure check")).toBeInTheDocument();
      expect(
        screen.getByRole("button", {
          name: locale === "en-US" ? "Refresh visits" : "Actualizar citas",
        }),
      ).toBeInTheDocument();
    },
  );

  it.each([
    ["en-US", "Expired"],
    ["es-MX", "Vencida"],
  ] as const)(
    "shows %s expired history without response controls",
    (locale, label) => {
      settings.profile!.preferredLanguage = locale;
      hookState.visits = [
        makeVisit({
          status: AppointmentStatus.EXPIRED,
          patientNote: "As written",
        }),
      ];
      render(<VisitsPage />);
      expect(screen.getByText(label)).toBeInTheDocument();
      expect(screen.getByText(/As written/)).toBeInTheDocument();
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    },
  );

  it("shows response deadlines in the saved Spanish timezone", () => {
    settings.profile!.preferredLanguage = "es-MX";
    hookState.visits = [
      makeVisit({
        proposalGroupId: "offer",
        proposalExpiresAt: "2026-05-08T16:00:00Z",
      }),
    ];
    render(<VisitsPage />);
    expect(
      screen.getByText(/Disponible hasta.*8 de mayo de 2026.*9:00/),
    ).toBeInTheDocument();
    expect(screen.getByText("America/Los_Angeles")).toBeInTheDocument();
  });

  it("shows an empty state when there are no visits", () => {
    render(<VisitsPage />);
    expect(screen.getByText(/No visits yet/i)).toBeInTheDocument();
  });

  it("shows a proposed visit and responds on accept/decline", () => {
    hookState.visits = [makeVisit()];
    render(<VisitsPage />);

    expect(screen.getByText(/Awaiting your response/i)).toBeInTheDocument();
    expect(screen.getByText(/Blood pressure check/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Accept/i }));
    expect(respond).toHaveBeenCalledWith("appt-1", "accept", undefined);

    fireEvent.click(screen.getByRole("button", { name: /Decline/i }));
    expect(respond).toHaveBeenCalledWith("appt-1", "decline", undefined);
  });

  it("lets the patient request a different time with a note", () => {
    hookState.visits = [makeVisit()];
    render(<VisitsPage />);

    fireEvent.click(
      screen.getByRole("button", { name: /Request a different time/i }),
    );
    fireEvent.change(screen.getByPlaceholderText(/mornings/i), {
      target: { value: "Afternoons please" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Send request/i }));

    expect(respond).toHaveBeenCalledWith(
      "appt-1",
      "request_alternative",
      "Afternoons please",
    );
  });

  it("lets the patient cancel a confirmed visit", () => {
    hookState.visits = [
      makeVisit({ id: "appt-2", status: AppointmentStatus.CONFIRMED }),
    ];
    render(<VisitsPage />);

    expect(screen.getByText("Confirmed")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Accept/i }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Cancel visit/i }));
    fireEvent.click(
      screen.getByRole("button", { name: /Confirm cancellation/i }),
    );

    expect(respond).toHaveBeenCalledWith("appt-2", "cancel", "");
  });

  it("groups an alternative-requested visit under waiting, with no actions", () => {
    hookState.visits = [
      makeVisit({
        id: "appt-3",
        status: AppointmentStatus.ALTERNATIVE_REQUESTED,
        patientNote: "Mornings work better",
      }),
    ];
    render(<VisitsPage />);

    expect(screen.getByText(/Waiting on your care team/i)).toBeInTheDocument();
    expect(screen.getByText(/Mornings work better/i)).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Cancel/i }),
    ).not.toBeInTheDocument();
  });

  it("shows an error state with the failure message", () => {
    hookState.error = "The network is unavailable.";
    render(<VisitsPage />);
    expect(
      screen.getByText(/Please try loading your visits again/i),
    ).toBeInTheDocument();
  });

  it("shows an action error inline without hiding the visits", () => {
    hookState.visits = [
      makeVisit({ id: "appt-4", status: AppointmentStatus.CONFIRMED }),
    ];
    hookState.actionError = "This appointment cannot be changed right now";
    render(<VisitsPage />);

    // The failed-action message shows...
    expect(
      screen.getByText(/Could not update this visit/i),
    ).toBeInTheDocument();
    // ...and the visit list is still rendered (not replaced by a load error).
    expect(screen.getByText("Confirmed")).toBeInTheDocument();
  });
});

describe("Visits settings and translation", () => {
  it("waits for settings before displaying appointment times", () => {
    settings.loading = true;
    settings.profile = null;
    hookState.visits = [makeVisit()];
    render(<VisitsPage />);
    expect(screen.getByText(/Loading your visit settings/)).toBeInTheDocument();
    expect(screen.queryByText("Blood pressure check")).not.toBeInTheDocument();
  });

  it.each([undefined, "", "not/a-timezone"])(
    "uses labelled UTC for an unavailable zone (%s)",
    (timezone) => {
      settings.profile = {
        preferredLanguage: "es-MX",
        timezone: timezone ?? "UTC",
      };
      settings.timezoneMissing = timezone === undefined || timezone === "";
      hookState.visits = [makeVisit()];
      render(<VisitsPage />);
      expect(
        screen.getByText(/Los horarios se muestran en UTC/),
      ).toBeInTheDocument();
      expect(screen.getByText("UTC")).toBeInTheDocument();
      fireEvent.click(
        screen.getByRole("button", { name: "Intentar de nuevo" }),
      );
      expect(retrySettings).toHaveBeenCalledOnce();
    },
  );

  it("keeps visits usable in English and UTC after profile failure", () => {
    settings.profile = null;
    settings.error = true;
    settings.timezoneMissing = true;
    hookState.visits = [makeVisit()];
    render(<VisitsPage />);
    expect(screen.getByText(/Times are shown in UTC/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Accept" }));
    expect(respond).toHaveBeenCalledWith("appt-1", "accept", undefined);
  });

  it("translates dates, controls and prompts while preserving user text", () => {
    settings.profile!.preferredLanguage = "es-MX";
    hookState.visits = [makeVisit({ patientNote: "Keep my original note" })];
    render(<VisitsPage />);
    expect(
      screen.getByRole("heading", { name: "Citas", level: 1 }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/viernes, 8 de mayo de 2026, 10:00/),
    ).toBeInTheDocument();
    expect(screen.getByText("America/Los_Angeles")).toBeInTheDocument();
    expect(screen.getByText("Propuesta")).toBeInTheDocument();
    expect(screen.getByText("Blood pressure check")).toBeInTheDocument();
    expect(screen.getByText(/Keep my original note/)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Solicitar otro horario" }),
    );
    fireEvent.change(
      screen.getByLabelText("¿Qué horarios te convienen más? (opcional)"),
      { target: { value: "Por la tarde" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Enviar solicitud" }));
    expect(respond).toHaveBeenCalledWith(
      "appt-1",
      "request_alternative",
      "Por la tarde",
    );
  });

  it("localizes errors and retry without exposing server text", () => {
    settings.profile!.preferredLanguage = "es-MX";
    hookState.error = "Private raw backend failure";
    const view = render(<VisitsPage />);
    expect(screen.queryByText(hookState.error)).not.toBeInTheDocument();
    expect(
      screen.getByText("No se pudieron cargar tus citas"),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Intentar de nuevo" }));
    expect(hookState.refresh).toHaveBeenCalledOnce();
    hookState.error = null;
    hookState.actionError = "Raw English action error";
    hookState.visits = [makeVisit({ status: AppointmentStatus.CONFIRMED })];
    view.rerender(<VisitsPage />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "No se pudo actualizar esta cita",
    );
    expect(screen.queryByText(hookState.actionError)).not.toBeInTheDocument();
    expect(screen.getByText("Confirmada")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cancelar cita" }));
    expect(
      screen.getByLabelText("Motivo de la cancelación (opcional)"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Confirmar cancelación" }),
    );
    expect(respond).toHaveBeenCalledWith("appt-1", "cancel", "");
  });
});

describe("Spanish Visits states", () => {
  it("translates the empty state", () => {
    settings.profile!.preferredLanguage = "es-MX";
    render(<VisitsPage />);
    expect(screen.getByText("Aún no tienes citas")).toBeInTheDocument();
  });
  it.each([
    [AppointmentStatus.SCHEDULED, "Programada", "Próximas citas"],
    [AppointmentStatus.DECLINED, "Rechazada", "Citas pasadas y otras"],
    [
      AppointmentStatus.ALTERNATIVE_REQUESTED,
      "Cambio solicitado",
      "Esperando a tu equipo de atención",
    ],
    [AppointmentStatus.CANCELLED, "Cancelada", "Citas pasadas y otras"],
    [AppointmentStatus.COMPLETED, "Completada", "Citas pasadas y otras"],
    [AppointmentStatus.NO_SHOW, "No asististe", "Citas pasadas y otras"],
  ])("translates status %s and its group", (status, label, group) => {
    settings.profile!.preferredLanguage = "es-MX";
    hookState.visits = [makeVisit({ status })];
    render(<VisitsPage />);
    expect(screen.getByText(label)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: group })).toBeInTheDocument();
  });
});

describe("Grouped appointment offers", () => {
  function offerSlots() {
    return [
      makeVisit({
        id: "slot-late",
        proposalGroupId: "offer-1",
        scheduledAt: "2026-10-02T17:00:00Z",
      }),
      makeVisit({
        id: "slot-early",
        proposalGroupId: "offer-1",
        scheduledAt: "2026-10-01T17:00:00Z",
      }),
    ];
  }
  it("shows one offer with sorted choices and sends the chosen slot", () => {
    hookState.visits = offerSlots();
    render(<VisitsPage />);
    expect(
      screen.getAllByText("Your clinician offered these times"),
    ).toHaveLength(1);
    const choices = screen.getAllByRole("button", {
      name: /^Choose this time:/,
    });
    expect(choices).toHaveLength(2);
    expect(choices[0]).toHaveAccessibleName(/October 1.*America\/Los_Angeles/);
    fireEvent.click(choices[0]);
    expect(respond).toHaveBeenCalledWith("slot-early", "accept");
    expect(
      screen.queryByRole("button", { name: "Cancel" }),
    ).not.toBeInTheDocument();
  });
  it("declines the whole offer with an optional note", () => {
    hookState.visits = offerSlots();
    render(<VisitsPage />);
    fireEvent.click(
      screen.getByRole("button", { name: "Decline these times" }),
    );
    fireEvent.change(screen.getByLabelText("Reason for declining (optional)"), {
      target: { value: "Out of town" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Decline offer" }));
    expect(respond).toHaveBeenCalledWith(
      "slot-early",
      "decline",
      "Out of town",
    );
  });
  it("requests new times in Spanish and disables every choice while responding", () => {
    settings.profile!.preferredLanguage = "es-MX";
    hookState.visits = offerSlots();
    const view = render(<VisitsPage />);
    fireEvent.click(
      screen.getByRole("button", { name: "Solicitar otros horarios" }),
    );
    fireEvent.change(
      screen.getByLabelText("¿Qué horarios te convienen más? (opcional)"),
      { target: { value: "Por la tarde" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Enviar solicitud" }));
    expect(respond).toHaveBeenCalledWith(
      "slot-early",
      "request_alternative",
      "Por la tarde",
    );
    hookState.respondingId = "slot-early";
    view.rerender(<VisitsPage />);
    for (const button of screen.getAllByRole("button"))
      expect(button).toBeDisabled();
  });
  it("keeps unrelated offers and legacy proposals separate", () => {
    hookState.visits = [
      ...offerSlots(),
      makeVisit({ id: "other", proposalGroupId: "offer-2" }),
      makeVisit({ id: "legacy" }),
    ];
    render(<VisitsPage />);
    expect(
      screen.getAllByText("Your clinician offered these times"),
    ).toHaveLength(2);
    expect(
      screen.getAllByRole("button", { name: /^Choose this time:/ }),
    ).toHaveLength(3);
    expect(screen.getByRole("button", { name: "Accept" })).toBeInTheDocument();
  });
});
