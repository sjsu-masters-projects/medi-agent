import type { Document, Locale } from "@/types";

type OriginFields = Pick<Document, "uploadedByRole" | "uploadedBy" | "patientId">;

/** Who added the record, in words; null when that is not recorded (UX-007: no placeholder line). */
export function recordOriginLabel(document: OriginFields, locale: Locale): string | null {
  const spanish = locale === "es-MX";
  const ownUpload =
    document.uploadedByRole === "patient" &&
    document.uploadedBy &&
    document.uploadedBy === document.patientId;
  if (ownUpload) return spanish ? "Subido por ti" : "Uploaded by you";
  if (document.uploadedByRole === "clinician")
    return spanish ? "Subido por tu equipo de atención" : "Uploaded by your care team";
  return null;
}

export function RecordOrigin({
  document,
  locale,
}: {
  document: OriginFields;
  locale: Locale;
}) {
  const label = recordOriginLabel(document, locale);
  if (!label) return null;
  return <span className="block text-xs leading-5 text-muted">{label}</span>;
}
