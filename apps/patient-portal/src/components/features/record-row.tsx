import { Icon } from "@/components/ui/icons";
import { IconTile } from "@/components/ui/list";
import { documentTypeIcon } from "../../../../../packages/shared/src/utils/document-presentation";
import {
  DocumentParseStatus,
  type Document,
  type Locale,
} from "@/types";
import { recordsCopy } from "./records-copy";
import { RecordReviewStatus } from "./record-review-status";
import { RecordOrigin } from "./record-origin";

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
  // Drop a leading sequence number such as "05 " when words follow it.
  title = title.replace(/^\d{1,3}\s+(?=\D)/, "");
  return title ? title.charAt(0).toUpperCase() + title.slice(1) : filename;
}

/** The drafted title in the reader's language, else the cleaned file name. */
export function recordTitle(document: Pick<Document, "displayTitle" | "fileName">, locale: Locale, patientName?: string) {
  return document.displayTitle?.[locale]?.trim() || cleanRecordTitle(document.fileName, patientName);
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

export function RecordRow({
  document,
  patientName,
  locale,
  typeLabel,
  provider,
  date,
  statusLabel,
  onOpen,
  entering = false,
  leaving = false,
  highlight = false,
  onHighlightEnd,
  stalled = false,
}: {
  document: Document;
  patientName?: string;
  locale: Locale;
  typeLabel: string;
  provider: string;
  date: string;
  statusLabel?: string;
  onOpen: () => void;
  /** A row added during this visit, such as a new upload. */
  entering?: boolean;
  /** A removed row on its way out; it no longer takes input. */
  leaving?: boolean;
  /** A brief neutral highlight after processing finishes while the page is open. */
  highlight?: boolean;
  onHighlightEnd?: () => void;
  /** Still processing, but the page stopped checking: no moving dots. */
  stalled?: boolean;
}) {
  const duplicate = document.parseStatus === DocumentParseStatus.DUPLICATE;
  const processing =
    document.parseStatus === DocumentParseStatus.PENDING ||
    document.parseStatus === DocumentParseStatus.PROCESSING;
  const live = processing && !stalled;
  const failed = document.parseStatus === DocumentParseStatus.FAILED;
  const summary = statusLabel === recordsCopy(locale, "AI Summary");
  const spanish = locale === "es-MX";
  const motion = leaving ? "ma-leave pointer-events-none" : highlight ? "ma-ready" : entering ? "ma-enter" : "";
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-hidden={leaving || undefined}
      tabIndex={leaving ? -1 : undefined}
      onAnimationEnd={(event) => {
        // Child animations (dots, chip fade) bubble here; only the row's own highlight counts.
        if (event.target === event.currentTarget && event.animationName === "ma-ready")
          onHighlightEnd?.();
      }}
      className={`group flex min-h-11 w-full items-center gap-3 px-[14px] py-[13px] text-left transition-colors duration-[160ms] hover:bg-[#FBF7F0] active:bg-surface-2 ${motion}`}
    >
      <IconTile icon={documentTypeIcon(document.documentType)} tone="neutral" className={duplicate ? "opacity-70" : ""} />
      <span className="flex min-w-0 flex-1 flex-wrap items-center gap-x-3 gap-y-1.5">
        <span className="min-w-0 flex-1 basis-[128px]">
          <h3
            className={`break-words text-[15px] font-semibold leading-snug [overflow-wrap:anywhere] ${duplicate ? "text-nav-idle" : "text-ink"}`}
          >
            {recordTitle(document, locale, patientName)}
          </h3>
          <span className="sr-only">{document.fileName}</span>
          <span className="mt-0.5 block break-words text-[13px] leading-snug text-muted first-letter:uppercase">
            <span>{typeLabel}</span> · {provider} · {date}
          </span>
          <RecordOrigin document={document} locale={locale} />
          <RecordReviewStatus status={document.reviewStatus} locale={locale} />
          {duplicate ? (
            <span className="mt-0.5 block text-[13px] text-muted">
              {statusLabel}
            </span>
          ) : null}
        </span>
        {!duplicate && statusLabel ? (
          <span className="ml-auto inline-flex min-w-0 max-w-full [&>span]:max-w-full [&>span]:break-words [&_svg]:shrink-0">
            {summary ? (
              // A quiet marker: most records have a summary, so a pill on every row is noise.
              <span className="ma-fade inline-flex items-center gap-1 text-xs font-medium text-brand">
                <Icon name="spark" className="h-3.5 w-3.5" />
                <span className="sr-only">{statusLabel}</span>
                <span aria-hidden="true">
                  {spanish ? "Resumen" : "Summary"}
                </span>
              </span>
            ) : (
              <span
                className={`inline-flex flex-wrap items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${failed ? "bg-danger-tint text-danger-ink" : processing ? "bg-surface-2 text-muted" : "bg-note-tint text-note-ink"}`}
              >
                {live ? (
                  <>
                    <span className="sr-only">{statusLabel}</span>
                    <span aria-hidden="true">
                      {spanish ? "Leyendo" : "Reading"}
                    </span>
                  </>
                ) : processing ? (
                  recordsCopy(locale, "Still processing")
                ) : (
                  statusLabel
                )}
                {live ? (
                  <span aria-hidden="true" className="inline-flex gap-[3px]">
                    {[0, 0.15, 0.3].map((delay) => (
                      <span
                        key={delay}
                        className="h-1 w-1 rounded-full bg-current"
                        style={{ animation: `ma-dot 1.2s ${delay}s infinite` }}
                      />
                    ))}
                  </span>
                ) : null}
              </span>
            )}
          </span>
        ) : null}
      </span>
      <Icon name="chevron" className="h-[18px] w-[18px] shrink-0 text-faint transition-transform duration-[160ms] group-hover:translate-x-0.5" />
    </button>
  );
}
