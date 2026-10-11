import { AiChip } from "@/components/ui/ai-chip";
import { Icon, type IconName } from "@/components/ui/icons";
import {
  DocumentParseStatus,
  DocumentType,
  type Document,
  type Locale,
} from "@/types";
import { recordsCopy } from "./records-copy";

/** Filename formatting only; source identity and clinical wording stay untouched. */
export function cleanRecordTitle(filename: string, patientName?: string) {
  let title = filename.replace(/\.[a-z0-9]+$/i, "");
  if (patientName?.trim()) {
    const prefix = patientName
      .trim()
      .split(/\s+/)
      .map((part) => part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"))
      .join("[-_ ]+");
    title = title.replace(new RegExp(`^${prefix}(?=[-_ ]|$)`, "i"), "");
  }
  title = title
    .replace(/(^|[-_ ])\d{4}[-_]\d{2}[-_]\d{2}(?=[-_ ]|$)/g, "$1")
    .replace(/(^|[-_ ])(?:en[-_]US|es[-_]MX)(?=[-_ ]|$)/gi, "$1")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
  return title ? title.charAt(0).toUpperCase() + title.slice(1) : filename;
}

export function groupRecordDates<T extends { createdAt: string }>(
  records: T[],
  now = new Date(),
  timezone = "UTC",
) {
  const dateKey = (date: Date) =>
    new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).format(date);
  const today = dateKey(now);
  const weekAgo = new Date(`${today}T12:00:00Z`);
  weekAgo.setUTCDate(weekAgo.getUTCDate() - 6);
  const start = weekAgo.toISOString().slice(0, 10);
  const sorted = [...records].sort(
    (a, b) => (Date.parse(b.createdAt) || 0) - (Date.parse(a.createdAt) || 0),
  );
  const recent: T[] = [];
  const earlier: T[] = [];
  for (const record of sorted) {
    const date = new Date(record.createdAt);
    const key = Number.isNaN(date.getTime()) ? "" : dateKey(date);
    (key >= start && key <= today ? recent : earlier).push(record);
  }
  return [
    { key: "recent", items: recent },
    { key: "earlier", items: earlier },
  ].filter((group) => group.items.length);
}

const tiles: Partial<
  Record<DocumentType, { icon: IconName; className: string }>
> = {
  [DocumentType.LAB_REPORT]: {
    icon: "lab",
    className: "bg-lab-tint text-lab-ink",
  },
  [DocumentType.PRESCRIPTION]: {
    icon: "rx",
    className: "bg-med-tint text-med-ink",
  },
  [DocumentType.DISCHARGE_SUMMARY]: {
    icon: "note",
    className: "bg-note-tint text-note-ink",
  },
};

export function RecordRow({
  document,
  patientName,
  locale,
  typeLabel,
  provider,
  date,
  statusLabel,
  onOpen,
}: {
  document: Document;
  patientName?: string;
  locale: Locale;
  typeLabel: string;
  provider: string;
  date: string;
  statusLabel?: string;
  onOpen: () => void;
}) {
  const duplicate = document.parseStatus === DocumentParseStatus.DUPLICATE;
  const processing =
    document.parseStatus === DocumentParseStatus.PENDING ||
    document.parseStatus === DocumentParseStatus.PROCESSING;
  const tile = tiles[document.documentType] ?? {
    icon: document.uploadedByRole === "patient" ? "up" : "note",
    className: "bg-upload-tint text-upload-ink",
  };
  const summary = statusLabel === recordsCopy(locale, "AI Summary");
  return (
    <button
      type="button"
      onClick={onOpen}
      className="flex min-h-11 w-full items-start gap-3 border-b border-line px-[14px] py-[13px] text-left last:border-b-0 hover:bg-surface-2"
    >
      <span
        className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-[13px] ${tile.className}`}
      >
        <Icon name={tile.icon} className="h-5 w-5" />
      </span>
      <span className="min-w-0 flex-1">
        <h3
          className={`break-words text-[15px] font-semibold ${duplicate ? "text-muted" : "text-ink"}`}
        >
          {cleanRecordTitle(document.fileName, patientName)}
        </h3>
        <span className="sr-only">{document.fileName}</span>
        <span className="mt-0.5 block break-words text-[13px] text-muted">
          <span>{typeLabel}</span> · {provider} · {date}
        </span>
        {duplicate ? (
          <span className="mt-1 block text-[13px] text-muted">
            {statusLabel}
          </span>
        ) : null}
        {!duplicate && statusLabel ? (
          <span className="mt-2 inline-flex max-w-full">
            {summary ? (
              <AiChip>{statusLabel}</AiChip>
            ) : (
              <span
                className={`inline-flex flex-wrap items-center gap-1.5 rounded-md px-2 py-1 text-xs font-medium ${document.parseStatus === DocumentParseStatus.FAILED ? "bg-danger-tint text-danger-ink" : "bg-surface-2 text-muted"}`}
              >
                {statusLabel}
                {processing ? (
                  <span aria-hidden="true" className="inline-flex gap-1">
                    {[
                      "",
                      "[animation-delay:150ms]",
                      "[animation-delay:300ms]",
                    ].map((delay, index) => (
                      <span
                        key={index}
                        className={`h-1 w-1 rounded-full bg-current motion-safe:animate-[ma-dot_1.2s_infinite] ${delay}`}
                      />
                    ))}
                  </span>
                ) : null}
              </span>
            )}
          </span>
        ) : null}
      </span>
      <Icon name="arrow" className="mt-3 h-5 w-5 shrink-0 text-muted" />
    </button>
  );
}
