import type { Document, Locale } from "@/types";

export function RecordOrigin({
  document,
  locale,
}: {
  document: Pick<Document, "uploadedByRole" | "uploadedBy" | "patientId">;
  locale: Locale;
}) {
  const spanish = locale === "es-MX";
  const ownUpload =
    document.uploadedByRole === "patient" &&
    document.uploadedBy &&
    document.uploadedBy === document.patientId;
  return (
    <span className="block text-xs leading-5 text-muted">
      {ownUpload
        ? spanish
          ? "Subido por ti"
          : "Uploaded by you"
        : document.uploadedByRole === "clinician"
          ? spanish
            ? "Subido por tu equipo de atención"
            : "Uploaded by your care team"
          : spanish
            ? "Quién lo subió: no disponible"
            : "Uploader unavailable"}
    </span>
  );
}
