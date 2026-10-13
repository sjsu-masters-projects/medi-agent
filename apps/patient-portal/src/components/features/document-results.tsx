"use client";

import { useEffect, useId, useState } from "react";
import { Icon } from "@/components/ui/icons";
import { Button, ErrorState, Skeleton } from "@/components/ui";
import { fetchDocumentResults, type DocumentResult } from "@/services/documents";
import type { Locale } from "@/types";
import { recordsCopy } from "./records-copy";

type ResultChip = "critical" | "high" | "low" | "outside";

/**
 * The status chip restates the report's own flag, else its own printed range.
 *
 * Nothing is compared or interpreted here: `flag_meaning` and `range_status` are what
 * the document itself printed. A flag this app does not recognise falls back to the
 * printed range, and a value within range gets no chip at all.
 */
export function resultChip(result: Pick<DocumentResult, "flag_meaning" | "range_status">): ResultChip | null {
  switch (result.flag_meaning) {
    case "critical":
      return "critical";
    case "high":
      return "high";
    case "low":
      return "low";
    case "abnormal":
      return "outside";
    default:
      break;
  }
  return result.range_status === "above" || result.range_status === "below" ? "outside" : null;
}

const CHIP_LABELS: Record<ResultChip, string> = {
  critical: "Critical",
  high: "High",
  low: "Low",
  outside: "Outside range",
};

/** Lab results grouped by their printed panel, keeping the order they were printed in. */
function groupByPanel(results: DocumentResult[]) {
  const groups: { panel: string | null; items: DocumentResult[] }[] = [];
  for (const result of results) {
    const group = groups.find((item) => item.panel === result.panel);
    if (group) group.items.push(result);
    else groups.push({ panel: result.panel, items: [result] });
  }
  return groups;
}

function printedValue(result: DocumentResult) {
  return result.unit ? `${result.value} ${result.unit}` : result.value;
}

type LoadState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; results: DocumentResult[] };

/**
 * Test results and measurements read from one opened document.
 *
 * Mount this only for the document a patient has opened; it fetches on mount. Give it a
 * `key` of the document id so switching documents starts from a fresh loading state.
 */
export function DocumentResults({
  documentId,
  locale,
  token,
}: {
  documentId: string;
  locale: Locale;
  token?: string | null;
}) {
  const copy = (text: string) => recordsCopy(locale, text);
  const headingId = useId();
  const measurementsId = useId();
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    fetchDocumentResults(documentId, token, controller.signal)
      .then((results) => {
        if (!controller.signal.aborted) setState({ status: "ready", results });
      })
      .catch(() => {
        if (!controller.signal.aborted) setState({ status: "error" });
      });
    return () => controller.abort();
  }, [documentId, token, attempt]);

  if (!token) return null;

  if (state.status === "loading") {
    return (
      <div className="space-y-2.5">
        <p className="sr-only" role="status">
          {copy("Loading test results…")}
        </p>
        <Skeleton className="h-3 w-28" variant="text" />
        <Skeleton className="h-[96px] w-full" />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <ErrorState
        title={copy("Could not load test results")}
        description={copy("We could not load the results from this document. Please try again.")}
        action={
          <Button
            onClick={() => {
              setState({ status: "loading" });
              setAttempt((value) => value + 1);
            }}
            size="sm"
            variant="secondary"
          >
            {copy("Try again")}
          </Button>
        }
      />
    );
  }

  const labs = state.results.filter((result) => result.kind === "lab_result");
  const vitals = state.results.filter((result) => result.kind === "vital_sign");
  if (!labs.length && !vitals.length) return null;
  const panels = groupByPanel(labs);
  const namedPanels = panels.some((group) => group.panel);

  return (
    <section aria-labelledby={headingId} className="ma-enter rounded-[22px] border border-line-strong bg-surface">
      <h4 id={headingId} className="flex items-center gap-2 px-4 pt-4 pb-1 text-[17px] font-semibold text-ink">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-lab-tint text-lab-ink">
          <Icon name="lab" className="h-4 w-4" />
        </span>
        {copy("Test results")}
      </h4>
      {panels.map((group, index) => (
        <ResultGroup
          key={group.panel ?? `unnamed-${index}`}
          heading={group.panel ?? (namedPanels ? copy("Other results") : null)}
          items={group.items}
          locale={locale}
        />
      ))}
      {vitals.length ? (
        <div className="pt-2">
          <h5 id={measurementsId} className="px-4 pt-2 pb-1 font-mono text-xs uppercase tracking-[0.08em] text-muted">
            {copy("Measurements")}
          </h5>
          <ul aria-labelledby={measurementsId} className="[&>*+*]:border-t [&>*+*]:border-line">
            {vitals.map((result, index) => (
              <li key={`${result.name}-${index}`} className="px-4 py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                  <p className="min-w-0 flex-1 basis-[150px] break-words text-[15px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]">
                    {result.name}
                  </p>
                  <p className="min-w-0 max-w-full break-words text-[15px] tabular-nums text-ink [overflow-wrap:anywhere]">
                    {printedValue(result)}
                  </p>
                </div>
                {result.observed_at ? (
                  <p className="mt-0.5 break-words text-[13px] text-muted [overflow-wrap:anywhere]">{result.observed_at}</p>
                ) : null}
                <RowFooter result={result} locale={locale} />
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      <div className="mt-1 space-y-1.5 border-t border-line px-4 pt-3 pb-4 text-[13px] leading-5 text-ink-2">
        <p className="flex gap-2">
          <Icon name="spark" className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand" />
          <span>
            {copy("These results were read automatically from this document. Any not yet reviewed by your care team are marked.")}
          </span>
        </p>
        <p className="font-medium text-ink">{copy("Your care team will review your results with you.")}</p>
      </div>
    </section>
  );
}

function ResultGroup({
  heading,
  items,
  locale,
}: {
  heading: string | null;
  items: DocumentResult[];
  locale: Locale;
}) {
  const copy = (text: string) => recordsCopy(locale, text);
  const headingId = useId();
  return (
    <div className="pt-2">
      {heading ? (
        <h5 id={headingId} className="break-words px-4 pt-2 pb-1 font-mono text-xs uppercase tracking-[0.08em] text-muted [overflow-wrap:anywhere]">
          {heading}
        </h5>
      ) : null}
      <ul
        aria-labelledby={heading ? headingId : undefined}
        aria-label={heading ? undefined : copy("Test results")}
        className="[&>*+*]:border-t [&>*+*]:border-line"
      >
        {items.map((result, index) => {
          const chip = resultChip(result);
          return (
            <li key={`${result.name}-${index}`} className="px-4 py-3">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                <p className="min-w-0 flex-1 basis-[150px] break-words text-[15px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]">
                  {result.name}
                </p>
                <p className="min-w-0 max-w-full break-words text-[15px] tabular-nums text-ink [overflow-wrap:anywhere]">
                  {printedValue(result)}
                </p>
              </div>
              {result.reference_range ? (
                <p className="mt-0.5 break-words text-[13px] text-muted [overflow-wrap:anywhere]">
                  {copy("Range")}: {result.reference_range}
                </p>
              ) : null}
              {result.flag_meaning === "unrecognized" && result.flag ? (
                <p className="mt-0.5 break-words text-[13px] text-muted [overflow-wrap:anywhere]">
                  {copy("Flag as printed")}: {result.flag}
                </p>
              ) : null}
              {chip ? (
                <p className="mt-2">
                  <span
                    className={`inline-flex max-w-full items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-semibold ${chip === "critical" ? "bg-danger-ink text-white" : "bg-note-tint text-note-ink"}`}
                  >
                    <Icon name="alert" className="h-3.5 w-3.5 shrink-0" />
                    <span className="sr-only">{copy("Result status")}: </span>
                    {copy(CHIP_LABELS[chip])}
                  </span>
                </p>
              ) : null}
              {chip === "critical" ? (
                <p className="mt-2 rounded-xl bg-danger-tint px-3 py-2 text-sm font-semibold text-danger-ink">
                  {copy("Contact your care team today.")}
                </p>
              ) : null}
              <RowFooter result={result} locale={locale} />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function RowFooter({ result, locale }: { result: DocumentResult; locale: Locale }) {
  const copy = (text: string) => recordsCopy(locale, text);
  if (result.reviewed && result.page === null) return null;
  return (
    <p className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted">
      {!result.reviewed ? (
        <span className="inline-flex items-center gap-1">
          <Icon name="clock" className="h-3.5 w-3.5 shrink-0" />
          {copy("Not yet reviewed by your care team")}
        </span>
      ) : null}
      {result.page !== null ? (
        <span className="font-mono text-xs">
          {copy("Page")} {result.page}
        </span>
      ) : null}
    </p>
  );
}
