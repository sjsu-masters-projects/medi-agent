"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { useSelector } from "react-redux";
import { Icon } from "@/components/ui/icons";
import { IconTile, GroupedList } from "@/components/ui/list";
import { EmptyState, ErrorState, Skeleton } from "@/components/ui";
import {
  formatSymptomTime,
  getSymptomHistoryCopy,
} from "@/content/symptom-history-copy";
import {
  fetchSymptomHistory,
  fetchSymptomReport,
  type SymptomReportDetail,
  type SymptomReportEvent,
  type SymptomReportList,
  type SymptomReportSummary,
} from "@/services/symptom-history";
import { ApiClientError } from "@/services/api";
import type { RootState } from "@/store/store";
import type { Locale } from "@/types";

type Load<T> =
  | { state: "loading" }
  | { state: "error"; notFound?: boolean }
  | { state: "ready"; data: T };

/** One request per token; a retry counter re-runs it. Nothing is cached across patients. */
function useLoad<T>(load: (token: string, signal: AbortSignal) => Promise<T>, key: string) {
  const token = useSelector((state: RootState) => state.auth.accessToken);
  const [result, setResult] = useState<{ key: string; value: Load<T> } | null>(null);
  const [attempt, setAttempt] = useState(0);
  const retry = useCallback(() => {
    setResult(null);
    setAttempt((value) => value + 1);
  }, []);
  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    const current = `${key}:${token}:${attempt}`;
    load(token, controller.signal).then(
      (data) => !controller.signal.aborted && setResult({ key: current, value: { state: "ready", data } }),
      (error: unknown) =>
        !controller.signal.aborted &&
        setResult({
          key: current,
          value: {
            state: "error",
            notFound: error instanceof ApiClientError && error.status === 404,
          },
        }),
    );
    return () => controller.abort();
    // `load` is stable per caller key.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token, key, attempt]);
  const value: Load<T> =
    result && result.key === `${key}:${token}:${attempt}` ? result.value : { state: "loading" };
  return { value, retry };
}

function severityTone(severity: number | null) {
  if (severity === null) return "bg-surface-2 text-muted";
  if (severity >= 8) return "bg-danger-tint text-danger-ink";
  if (severity >= 5) return "bg-note-tint text-note-ink";
  return "bg-brand-tint text-brand";
}

function SeverityChip({ severity, locale }: { severity: number | null; locale: Locale }) {
  const copy = getSymptomHistoryCopy(locale);
  return (
    <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${severityTone(severity)}`}>
      {copy.severity(severity)}
    </span>
  );
}

export function SymptomHistoryList({ locale, timezone }: { locale: Locale; timezone: string }) {
  const copy = getSymptomHistoryCopy(locale);
  const { value, retry } = useLoad<SymptomReportList>(
    (token, signal) => fetchSymptomHistory(token, signal),
    "list",
  );

  return (
    <section aria-labelledby="symptom-history-heading" className="space-y-2">
      <h2
        id="symptom-history-heading"
        className="px-1 font-mono text-xs uppercase tracking-[0.08em] text-muted"
      >
        {copy.heading}
      </h2>
      {value.state === "loading" ? (
        <div role="status" aria-label={copy.loading} className="space-y-2">
          <Skeleton className="h-[68px] w-full rounded-[22px]" />
          <Skeleton className="h-[68px] w-full rounded-[22px]" />
          <span className="sr-only">{copy.loading}</span>
        </div>
      ) : value.state === "error" ? (
        <ErrorState title={copy.errorTitle} description={copy.errorDetail} onRetry={retry} />
      ) : value.data.items.length === 0 ? (
        <div className="rounded-[22px] bg-surface">
          <EmptyState title={copy.emptyTitle} description={copy.emptyDetail} />
        </div>
      ) : (
        <>
          <GroupedList className="!mx-0" label={copy.heading}>
            {value.data.items.map((item) => (
              <li key={item.id}>
                <HistoryRow item={item} locale={locale} timezone={timezone} />
              </li>
            ))}
          </GroupedList>
          {value.data.has_more ? (
            <p className="px-1 text-xs text-muted">{copy.more}</p>
          ) : null}
        </>
      )}
    </section>
  );
}

function HistoryRow({
  item,
  locale,
  timezone,
}: {
  item: SymptomReportSummary;
  locale: Locale;
  timezone: string;
}) {
  const copy = getSymptomHistoryCopy(locale);
  const when = formatSymptomTime(item.confirmed_at, locale, timezone);
  return (
    <Link
      href={`/symptoms/${item.id}`}
      aria-label={copy.rowLabel(item.symptom, copy.severity(item.severity), when)}
      className="group flex min-h-11 w-full items-center gap-3 px-[14px] py-[13px] transition-colors duration-[160ms] hover:bg-surface-2"
    >
      <IconTile icon="note" tone="note" />
      <span className="min-w-0 flex-1">
        <span
          lang={item.locale}
          className="block break-words text-[15px] font-semibold leading-snug text-ink [overflow-wrap:anywhere]"
        >
          {item.symptom}
        </span>
        <span className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted">
          <SeverityChip severity={item.severity} locale={locale} />
          <span>{when}</span>
        </span>
        <span className="mt-0.5 block text-[13px] text-muted">{copy.status[item.status]}</span>
      </span>
      <Icon
        name="chevron"
        className="h-[18px] w-[18px] shrink-0 text-faint transition-transform duration-[160ms] group-hover:translate-x-0.5 motion-reduce:transition-none motion-reduce:group-hover:translate-x-0"
      />
    </Link>
  );
}

function eventLabel(event: SymptomReportEvent, locale: Locale) {
  const copy = getSymptomHistoryCopy(locale);
  return event.kind === "reviewed"
    ? copy.events.reviewed(event.actor_name)
    : copy.events[event.kind];
}

export function SymptomReportView({
  id,
  locale,
  timezone,
}: {
  id: string;
  locale: Locale;
  timezone: string;
}) {
  const copy = getSymptomHistoryCopy(locale);
  const { value, retry } = useLoad<SymptomReportDetail>(
    (token, signal) => fetchSymptomReport(token, id, signal),
    `report:${id}`,
  );

  if (value.state === "loading")
    return (
      <div role="status" aria-label={copy.loading} className="space-y-3">
        <Skeleton className="h-40 w-full rounded-[22px]" />
        <span className="sr-only">{copy.loading}</span>
      </div>
    );
  if (value.state === "error")
    return value.notFound ? (
      <div className="rounded-[22px] bg-surface">
        <EmptyState title={copy.notFoundTitle} description={copy.notFoundDetail} />
      </div>
    ) : (
      <ErrorState title={copy.errorTitle} description={copy.errorDetail} onRetry={retry} />
    );

  const report = value.data;
  const when = formatSymptomTime(report.confirmed_at, locale, timezone);
  return (
    <div className="space-y-4">
      <section className="space-y-3 rounded-[22px] bg-surface p-[14px]" aria-labelledby="report-title">
        <div className="flex items-start gap-3">
          <IconTile icon="note" tone="note" />
          <div className="min-w-0 flex-1">
            <h2
              id="report-title"
              lang={report.locale}
              className="break-words text-[17px] font-semibold text-ink [overflow-wrap:anywhere]"
            >
              {report.symptom}
            </h2>
            <p className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[13px] text-muted">
              <SeverityChip severity={report.severity} locale={locale} />
              <span>{copy.whenReported} {when}</span>
            </p>
          </div>
        </div>
        <dl className="grid gap-x-4 gap-y-2 border-t border-line pt-3 text-[14px] sm:grid-cols-[max-content_1fr]">
          {report.onset ? (
            <>
              <dt className="text-muted">{copy.onset}</dt>
              <dd lang={report.locale} className="break-words text-ink">{report.onset}</dd>
            </>
          ) : null}
          {report.duration ? (
            <>
              <dt className="text-muted">{copy.duration}</dt>
              <dd lang={report.locale} className="break-words text-ink">{report.duration}</dd>
            </>
          ) : null}
        </dl>
      </section>

      <section className="rounded-[22px] bg-surface p-[14px]" aria-labelledby="answers-title">
        <h3 id="answers-title" className="text-[15px] font-semibold text-ink">{copy.answers}</h3>
        <p className="mt-0.5 text-xs text-muted">{copy.answersNote}</p>
        {report.answers.length === 0 ? (
          <p className="mt-3 text-sm text-muted">{copy.noAnswers}</p>
        ) : (
          <dl lang={report.locale} className="mt-3 divide-y divide-line">
            {report.answers.map((answer) => (
              <div key={answer.question_id} className="py-2.5">
                <dt className="text-xs font-medium text-muted">{answer.label}</dt>
                <dd className="mt-0.5 break-words text-[15px] text-ink [overflow-wrap:anywhere]">
                  {answer.display}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      <section className="rounded-[22px] bg-surface p-[14px]" aria-labelledby="progress-title">
        <h3 id="progress-title" className="text-[15px] font-semibold text-ink">{copy.progress}</h3>
        <ol className="mt-3">
          {report.events.map((event, index) => (
            <li key={`${event.kind}-${event.at}`} className="relative flex gap-3 pb-4 last:pb-0">
              {index < report.events.length - 1 ? (
                <span aria-hidden="true" className="absolute left-[5px] top-4 h-full w-px bg-line-strong" />
              ) : null}
              <span
                aria-hidden="true"
                className={`relative mt-1.5 h-[11px] w-[11px] shrink-0 rounded-full ${event.kind === "reviewed" ? "bg-brand" : event.kind === "flagged_urgent" || event.kind === "not_sent_no_care_team" ? "bg-danger-ink" : "bg-line-strong"}`}
              />
              <div className="min-w-0">
                <p className="break-words text-[14px] font-medium text-ink">{eventLabel(event, locale)}</p>
                {event.kind === "reviewed" && event.team_label ? (
                  <p className="break-words text-xs text-muted">{event.team_label}</p>
                ) : null}
                <p className="text-xs text-muted">
                  <time dateTime={event.at}>{formatSymptomTime(event.at, locale, timezone)}</time>
                </p>
              </div>
            </li>
          ))}
        </ol>
      </section>
      <p role="note" className="px-1 text-xs leading-5 text-muted">{copy.disclaimer}</p>
    </div>
  );
}
