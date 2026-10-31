"use client";

import { useEffect, useState } from "react";
import { Skeleton } from "@/components/ui";
import { ProcessingDots } from "@/components/ui/motion";
import type { ExplanationSection } from "@/services/documents";
import type { Locale } from "@/types";
import { recordsCopy } from "./records-copy";

/** Same threshold as the chat slow-turn note, so both waits read the same way. */
export const EXPLANATION_SLOW_MS = 15_000;

/**
 * Work in progress for the record explanation: moving dots beside the status text and,
 * optionally, a placeholder shaped like the opening sentence and detail bullets.
 *
 * Mount only while work is actually running. Give it a `key` per request so the slow
 * note restarts for a retry or another document. The text stays readable with reduced
 * motion; only the dots and shimmer stop.
 */
export function ExplanationPending({
  label,
  locale,
  placeholder = false,
  slowAfterMs,
}: {
  label: string;
  locale: Locale;
  placeholder?: boolean;
  slowAfterMs?: number;
}) {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (slowAfterMs === undefined) return;
    const timer = window.setTimeout(() => setSlow(true), slowAfterMs);
    return () => window.clearTimeout(timer);
  }, [slowAfterMs]);
  return (
    <div className="mt-3" lang={locale}>
      <p className="flex items-center gap-2.5 break-words text-base leading-7 text-ink-2">
        <ProcessingDots className="bg-brand" />
        <span>{label}</span>
      </p>
      {placeholder ? (
        <div aria-hidden="true" className="mt-3 space-y-2.5">
          <Skeleton variant="text" className="w-full" />
          <Skeleton variant="text" className="w-4/5" />
          <div className="space-y-2.5 pt-1.5">
            {["w-11/12", "w-3/4", "w-5/6"].map((width) => (
              <div key={width} className="flex items-center gap-2.5">
                <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-line-strong" />
                <Skeleton variant="text" className={`h-3.5 ${width}`} />
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {slow ? (
        <p className="ma-enter mt-3 text-sm leading-6 text-muted">
          {recordsCopy(
            locale,
            "This is taking longer than usual. You can read the original document while you wait.",
          )}
        </p>
      ) : null}
    </div>
  );
}

export function ExplanationSections({
  sections,
  locale,
}: {
  sections: ExplanationSection[];
  locale: Locale;
}) {
  const overview = sections
    .filter((section) => section.kind === "overview")
    .flatMap((section) => section.items);
  const details = sections
    .filter(
      (section) => section.kind !== "overview" && section.kind !== "questions",
    )
    .flatMap((section) => section.items);
  const questions = sections
    .filter((section) => section.kind === "questions")
    .flatMap((section) => section.items);
  const spanish = locale === "es-MX";
  return (
    <div
      role="region"
      aria-label={spanish ? "Resumen del documento" : "Document summary"}
      lang={locale}
      className="ma-enter mt-4 max-w-[65ch] space-y-4 text-base leading-7 text-ink"
    >
      {overview.map((item, index) => (
        <p key={index} className="break-words">
          {item}
        </p>
      ))}
      {details.length ? (
        <ul
          aria-label={spanish ? "Detalles del documento" : "Document details"}
          className="list-disc space-y-3 pl-5 marker:text-brand"
        >
          {details.map((item, index) => (
            <li key={index} className="break-words pl-1">
              {item}
            </li>
          ))}
        </ul>
      ) : null}
      {questions.length ? (
        <ul
          aria-label={
            spanish
              ? "Preguntas para tu equipo de atención"
              : "Questions for your care team"
          }
          className="space-y-2 border-t border-brand/15 pt-4 text-ink-2"
        >
          {questions.map((item, index) => (
            <li key={index} className="break-words">
              {item}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
