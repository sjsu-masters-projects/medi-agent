import type { Document, Locale } from "@/types";

/** Source approval never implies approval of an explanation or treatment. */
export function RecordReviewStatus({
  status,
  locale,
}: {
  status: Document["reviewStatus"];
  locale: Locale;
}) {
  const spanish = locale === "es-MX";
  const label =
    status === "approved"
      ? spanish
        ? "Documento aprobado por tu equipo de atención"
        : "Source approved by your care team"
      : status === "pending"
        ? spanish
          ? "En espera de revisión del equipo de atención"
          : "Awaiting care-team review"
        : status === "rejected"
          ? spanish
            ? "Documento no aprobado por tu equipo de atención"
            : "Source not approved by your care team"
          : spanish
            ? "Estado de revisión no disponible"
            : "Review status unavailable";
  return (
    <span
      className={`mt-1 inline-flex max-w-full rounded-lg px-2 py-1 text-xs font-medium leading-5 ${status === "approved" ? "bg-brand-tint text-brand-ink" : status === "rejected" ? "bg-danger-tint text-danger-ink" : "bg-surface-2 text-muted"}`}
    >
      {label}
    </span>
  );
}
