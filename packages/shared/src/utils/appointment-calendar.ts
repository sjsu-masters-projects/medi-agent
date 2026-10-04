import {
  resolveLocaleResource,
  type Locale,
  type LocaleResourceMap,
} from "../types";

export interface AppointmentCalendarExport {
  filename: string;
  content: string;
}

const english = {
  download: "Add to calendar",
  downloading: "Preparing calendar file…",
  notice:
    "Downloads a one-time copy. Changes and cancellations do not sync. Your calendar may display its own timezone.",
  error:
    "Could not download this appointment. Refresh appointments to check its status, then try again.",
};
const resources: LocaleResourceMap<typeof english> = {
  default: english,
  "en-US": english,
  "es-MX": {
    download: "Agregar al calendario",
    downloading: "Preparando el archivo del calendario…",
    notice:
      "Descarga una copia. Los cambios y las cancelaciones no se sincronizan. Tu calendario puede mostrar su propia zona horaria.",
    error:
      "No se pudo descargar esta cita. Actualiza las citas para revisar su estado e inténtalo de nuevo.",
  },
};

export function getAppointmentCalendarCopy(locale: Locale) {
  return resolveLocaleResource(locale, resources);
}

/** Local file only: never navigates with an auth token or sends calendar invitations. */
export function saveAppointmentCalendar(file: AppointmentCalendarExport) {
  const url = URL.createObjectURL(
    new Blob([file.content], { type: "text/calendar;charset=utf-8" }),
  );
  const anchor = document.createElement("a");
  try {
    anchor.href = url;
    anchor.download = /^appointment-[a-zA-Z0-9-]+\.ics$/.test(file.filename)
      ? file.filename
      : "appointment.ics";
    document.body.appendChild(anchor);
    anchor.click();
  } finally {
    anchor.remove();
    // Allow the browser to consume the clicked download before releasing the Blob.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
