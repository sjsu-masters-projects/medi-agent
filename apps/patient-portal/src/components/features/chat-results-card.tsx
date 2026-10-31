"use client";

import Link from "next/link";
import { useId, useState } from "react";
import { Icon } from "@/components/ui/icons";
import { getChatResultsCopy } from "@/content/chat-copy";
import type { DocumentResult } from "@/services/documents";
import type { ChatDocumentResultsAttachment, Locale } from "@/types";
import { printedValue, resultChip, ResultStatusChip } from "./document-results";
import { recordsCopy } from "./records-copy";
import { cleanRecordTitle } from "./record-row";

/** Records opens this document directly from `?document=`. */
export function buildRecordsDocumentHref(documentId: string): string {
  return `/records?document=${encodeURIComponent(documentId)}`;
}

/** Out-of-range rows first: critical, then every other flagged row in printed order. */
function orderFlagged(results: DocumentResult[]) {
  return results
    .map((result, index) => ({ result, index, critical: resultChip(result) === "critical" }))
    .sort((a, b) => Number(b.critical) - Number(a.critical) || a.index - b.index)
    .map((item) => item.result);
}

function documentTitle(
  attachment: ChatDocumentResultsAttachment,
  language: Locale | undefined,
  fallback: string,
): { text: string; lang?: Locale } {
  const titled = language ? attachment.title[language] : undefined;
  if (titled) return { text: titled, lang: language };
  // A cleaned file name reads as a title; the raw name stays on the record itself.
  return { text: attachment.fileName ? cleanRecordTitle(attachment.fileName) : fallback };
}

/**
 * Results of a document Nora's reply cited, built by the server from that document's
 * extracted, source-checked facts. Nothing here is read from the reply text, and the
 * status chips restate the report's own flags and ranges exactly as Records does.
 */
export function ChatResultsCard({
  attachment,
  language,
  locale,
}: {
  attachment: ChatDocumentResultsAttachment;
  /** The message's own language, used to pick the document title. */
  language?: Locale;
  /** The interface language, used for this card's own copy like the rest of the chat. */
  locale: Locale;
}) {
  const copy = getChatResultsCopy(locale);
  const titleId = useId();
  const panelId = useId();
  const measurementsId = useId();
  const [expanded, setExpanded] = useState(false);

  const flagged = orderFlagged(attachment.results.filter((result) => resultChip(result) !== null));
  const unflagged = attachment.results.filter((result) => resultChip(result) === null);
  const inRange = unflagged.filter((result) => result.kind === "lab_result");
  const measurements = unflagged.filter((result) => result.kind === "vital_sign");
  const critical = flagged.some((result) => result.flag_meaning === "critical");
  const unreviewed = attachment.results.some((result) => !result.reviewed);
  const title = documentTitle(attachment, language, copy.fallbackTitle);
  const hiddenCount = inRange.length || measurements.length;
  const toggleLabel = inRange.length
    ? (expanded ? copy.hideInRange : copy.showInRange(inRange.length))
    : (expanded ? copy.hideMeasurements : copy.showMeasurements(measurements.length));

  return (
    <section
      aria-labelledby={titleId}
      className="mt-3 overflow-hidden rounded-2xl border border-line-strong bg-background/60"
      data-testid="chat-results-card"
      lang={locale}
    >
      {critical ? (
        <div className="flex items-start gap-2 bg-danger-tint px-3 py-2.5 text-danger-ink">
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <div className="min-w-0 space-y-0.5 text-[14px] leading-snug">
            <p className="font-semibold">{copy.criticalContact}</p>
            <p>{copy.criticalEmergency}</p>
          </div>
        </div>
      ) : null}
      <div className="flex items-start gap-2.5 px-3 pt-3 pb-1">
        <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-lab-tint text-lab-ink">
          <Icon name="lab" className="h-4 w-4" />
        </span>
        <div className="min-w-0 flex-1">
          <p className="text-xs font-medium text-muted">{copy.eyebrow}</p>
          <h2
            id={titleId}
            className="break-words text-[15px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]"
            lang={title.lang}
          >
            {title.text}
          </h2>
        </div>
      </div>

      {flagged.length ? (
        <ResultList label={copy.outOfRange} locale={locale} results={flagged} />
      ) : inRange.length ? (
        <p className="px-3 pt-1 pb-2 text-[13px] leading-snug text-ink-2">{copy.allWithinRange}</p>
      ) : null}

      {hiddenCount ? (
        <div className="border-t border-line">
          <button
            aria-controls={panelId}
            aria-expanded={expanded}
            className="ma-press flex min-h-11 w-full items-center gap-2 px-3 py-2 text-left text-[14px] font-medium text-brand-ink hover:bg-surface-2/60"
            onClick={() => setExpanded((current) => !current)}
            type="button"
          >
            <span className="min-w-0 flex-1 break-words">{toggleLabel}</span>
            <Icon
              name="chevronDown"
              className={`h-4 w-4 shrink-0 transition-transform duration-[240ms] ${expanded ? "rotate-180" : ""}`}
            />
          </button>
          <div hidden={!expanded} id={panelId}>
            {inRange.length ? <ResultList label={copy.inRange} locale={locale} results={inRange} /> : null}
            {measurements.length ? (
              <div className={inRange.length ? "border-t border-line" : undefined}>
                <h3 id={measurementsId} className="px-3 pt-2.5 font-mono text-[11px] uppercase tracking-[0.08em] text-muted">
                  {copy.measurements}
                </h3>
                <ResultList labelledBy={measurementsId} locale={locale} results={measurements} />
              </div>
            ) : null}
          </div>
        </div>
      ) : null}

      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 border-t border-line px-3 py-1.5 text-[13px] leading-snug">
        <p className="flex min-w-0 flex-1 basis-[180px] items-start gap-1.5 py-1.5 text-ink-2">
          {unreviewed ? <Icon name="spark" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand" /> : null}
          <span className="min-w-0 break-words">{unreviewed ? copy.notReviewed : copy.reviewed}</span>
        </p>
        <Link
          className="ma-press inline-flex min-h-11 shrink-0 items-center gap-1 rounded-lg font-semibold text-brand-ink hover:underline"
          href={buildRecordsDocumentHref(attachment.documentId)}
        >
          {copy.seeInRecords}
          <Icon name="arrow" className="h-3.5 w-3.5" />
        </Link>
      </div>
    </section>
  );
}

function ResultList({
  label,
  labelledBy,
  locale,
  results,
}: {
  label?: string;
  labelledBy?: string;
  locale: Locale;
  results: DocumentResult[];
}) {
  const records = (text: string) => recordsCopy(locale, text);
  return (
    <ul aria-label={labelledBy ? undefined : label} aria-labelledby={labelledBy} className="[&>*+*]:border-t [&>*+*]:border-line">
      {results.map((result, index) => {
        const chip = resultChip(result);
        return (
          <li key={`${result.name}-${index}`} className="px-3 py-2.5">
            <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
              <p className="min-w-0 flex-1 basis-[120px] break-words text-[14px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]">
                {result.name}
              </p>
              <p className="min-w-0 max-w-full break-words text-[14px] tabular-nums text-ink [overflow-wrap:anywhere]">
                {printedValue(result)}
              </p>
            </div>
            {chip || result.reference_range ? (
              <div className="mt-1 flex flex-wrap items-center gap-x-2.5 gap-y-1">
                {chip ? <ResultStatusChip chip={chip} locale={locale} /> : null}
                {result.reference_range ? (
                  <p className="min-w-0 break-words text-[13px] text-muted [overflow-wrap:anywhere]">
                    {records("Range")}: {result.reference_range}
                  </p>
                ) : null}
              </div>
            ) : null}
            {result.flag_meaning === "unrecognized" && result.flag ? (
              <p className="mt-0.5 break-words text-[13px] text-muted [overflow-wrap:anywhere]">
                {records("Flag as printed")}: {result.flag}
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}
