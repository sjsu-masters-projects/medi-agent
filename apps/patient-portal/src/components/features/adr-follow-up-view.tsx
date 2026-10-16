"use client";

import Link from "next/link";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useSelector } from "react-redux";
import { ADRFollowUpForm } from "@/components/features/adr-follow-up-form";
import { Badge, Button, EmptyState, ErrorState, Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { IconTile } from "@/components/ui/list";
import {
  formatFollowUpDate,
  getADRFollowUpCopy,
  type ADRFollowUpCopy,
} from "@/content/adr-follow-up-copy";
import {
  classifyADRFollowUpError,
  fetchADRFollowUpOverview,
  type ADRFollowUpOverview,
  type ADRFollowUpRequest,
  type ADRFollowUpSelector,
} from "@/services/adr-follow-up";
import type { RootState } from "@/store/store";
import type { Locale } from "@/types";

const RECENT_SHOWN = 5;

const linkAction =
  "ma-press -ml-2 inline-flex min-h-11 items-center gap-1 rounded-xl px-2 text-sm font-semibold text-brand-ink hover:bg-brand-tint";
const backAction =
  "ma-press inline-flex min-h-11 items-center justify-center gap-1.5 rounded-[14px] bg-surface-2 px-4 py-2 text-sm font-semibold text-ink-2 hover:bg-line-strong";
const wrap = "break-words [overflow-wrap:anywhere]";

interface ADRFollowUpViewProps {
  /** The patient's saved locale; undefined while the profile loads. */
  locale: Locale | undefined;
  /** The patient's saved IANA timezone, used for answered and closed dates. */
  timeZone?: string | null;
  /** Open one request by ID (any status). Takes precedence over `assessmentId`. */
  requestId?: string | null;
  /** Open the newest request for an assessment. */
  assessmentId?: string | null;
  /** Leaves the view; without it the not-found action links to `/chat`. */
  onBack?: () => void;
}

type ViewState =
  | { phase: "loading" }
  | { phase: "error" }
  | { phase: "notFound" }
  | {
      phase: "ready";
      selectorKey: string;
      overview: ADRFollowUpOverview;
      /** Stable slot order: selected request first, then pending, never reshuffled by a refetch. */
      order: string[];
      /** Last known copy of every request seen, so a sent slot keeps its context. */
      known: Record<string, ADRFollowUpRequest>;
    };

function followUpHref(requestId: string): string {
  return `/chat?view=follow-up&request=${encodeURIComponent(requestId)}`;
}

function selectorFor(
  requestId: string | null | undefined,
  assessmentId: string | null | undefined,
): { key: string; selector: ADRFollowUpSelector } {
  if (requestId) return { key: `request:${requestId}`, selector: { requestId } };
  if (assessmentId) {
    return { key: `assessment:${assessmentId}`, selector: { assessmentId } };
  }
  return { key: "", selector: {} };
}

function selectedPendingId(overview: ADRFollowUpOverview): string | null {
  return overview.selected?.status === "pending" ? overview.selected.id : null;
}

function applyOverview(
  previous: ViewState,
  overview: ADRFollowUpOverview,
  selectorKey: string,
): ViewState {
  const ready = previous.phase === "ready" ? previous : null;
  const selectorChanged = !ready || ready.selectorKey !== selectorKey;
  const lead = selectedPendingId(overview);
  const prevOrder = ready?.order ?? [];
  const base = selectorChanged
    ? [...(lead ? [lead] : []), ...prevOrder]
    : [...prevOrder, ...(lead ? [lead] : [])];
  const order = Array.from(
    new Set([...base, ...overview.pending.map((request) => request.id)]),
  );
  const known = { ...(ready?.known ?? {}) };
  for (const request of [
    ...(overview.selected ? [overview.selected] : []),
    ...overview.pending,
    ...overview.recent,
  ]) {
    known[request.id] = request;
  }
  return { phase: "ready", selectorKey, overview, order, known };
}

/**
 * Host for the care team's follow-up questions: loads the patient's overview
 * and shows pending forms, the answered or closed state of a selected request,
 * and a short recent history. Never shows a score or causality.
 */
export function ADRFollowUpView({
  locale,
  timeZone,
  requestId,
  assessmentId,
  onBack,
}: ADRFollowUpViewProps) {
  const accessToken = useSelector((state: RootState) => state.auth.accessToken);
  const [state, setState] = useState<ViewState>({ phase: "loading" });
  const [reload, setReload] = useState(0);
  const [sentIds, setSentIds] = useState<string[]>([]);
  const [closedIds, setClosedIds] = useState<string[]>([]);
  const [focusId, setFocusId] = useState<string | null>(null);
  const confirmations = useRef(new Map<string, HTMLDivElement>());

  useEffect(() => {
    if (!accessToken) return;
    const { key: selectorKey, selector } = selectorFor(requestId, assessmentId);
    // Each run supersedes the last; a late response for an old selector is dropped.
    let current = true;
    fetchADRFollowUpOverview(accessToken, selector)
      .then((overview) => {
        if (current) {
          setState((previous) => applyOverview(previous, overview, selectorKey));
        }
      })
      .catch((error: unknown) => {
        if (!current) return;
        const failure = classifyADRFollowUpError(error);
        setState((previous) => {
          if (failure === "notFound") return { phase: "notFound" };
          // A background refresh of the same selection keeps what is on screen,
          // including any confirmation; a new selection must not show stale data.
          if (previous.phase === "ready" && previous.selectorKey === selectorKey) {
            return previous;
          }
          return { phase: "error" };
        });
      });
    return () => {
      current = false;
    };
  }, [accessToken, requestId, assessmentId, reload]);

  useEffect(() => {
    if (focusId) confirmations.current.get(focusId)?.focus();
  }, [focusId]);

  const refetch = useCallback(() => setReload((value) => value + 1), []);

  const handleSent = useCallback(
    (id: string) => {
      setSentIds((ids) => (ids.includes(id) ? ids : [...ids, id]));
      setFocusId(id);
      refetch();
    },
    [refetch],
  );

  const handleClosed = useCallback(
    (id: string) => {
      setClosedIds((ids) => (ids.includes(id) ? ids : [...ids, id]));
      refetch();
    },
    [refetch],
  );

  const retry = () => {
    setState({ phase: "loading" });
    refetch();
  };

  const confirmationRef = (id: string) => (node: HTMLDivElement | null) => {
    if (node) confirmations.current.set(id, node);
    else confirmations.current.delete(id);
  };

  if (!locale || state.phase === "loading") {
    return <LoadingState locale={locale} />;
  }

  const copy = getADRFollowUpCopy(locale);

  if (state.phase === "error") {
    return (
      <div className="ma-enter" key="error" lang={locale}>
        {/* Retry is passed as an action so its label follows `locale`, not the profile context. */}
        <ErrorState
          action={
            <Button onClick={retry} size="sm" variant="secondary">
              {copy.states.retry}
            </Button>
          }
          description={copy.states.error.detail}
          title={copy.states.error.title}
        />
      </div>
    );
  }

  if (state.phase === "notFound") {
    return (
      <div className="ma-enter rounded-[22px] bg-surface" key="not-found" lang={locale}>
        <EmptyState
          action={
            onBack ? (
              <Button onClick={onBack} size="sm" variant="secondary">
                <Icon className="h-4 w-4" name="back" />
                {copy.back}
              </Button>
            ) : (
              <Link className={backAction} href="/chat" prefetch={false}>
                <Icon className="h-4 w-4" name="back" />
                {copy.back}
              </Link>
            )
          }
          description={copy.states.notFound.detail}
          icon={<Icon name="search" />}
          title={copy.states.notFound.title}
        />
      </div>
    );
  }

  const { overview, order, known } = state;
  const selected = overview.selected;
  const sent = new Set(sentIds);
  const closed = new Set(closedIds);
  const pendingNow = new Set(overview.pending.map((request) => request.id));
  const lead = selectedPendingId(overview);
  if (lead) pendingNow.add(lead);
  const fresh = new Map<string, ADRFollowUpRequest>();
  for (const request of [...overview.recent, ...overview.pending]) {
    fresh.set(request.id, request);
  }
  if (selected) fresh.set(selected.id, selected);

  // A selected request that is no longer pending shows its outcome, unless the
  // patient just answered it here: then the confirmation stays in its slot.
  const showSelectedOutcome =
    selected !== null && selected.status !== "pending" && !sent.has(selected.id);
  const slots = showSelectedOutcome
    ? []
    : order.filter((id) => pendingNow.has(id) || sent.has(id) || closed.has(id));

  let body: ReactNode;
  if (showSelectedOutcome && selected) {
    body = (
      <RequestOutcome copy={copy} locale={locale} request={selected} timeZone={timeZone} />
    );
  } else if (slots.length === 0) {
    body = (
      <div className="ma-enter rounded-[22px] bg-surface" key="empty">
        <EmptyState
          description={copy.states.empty.detail}
          icon={<Icon name="note" />}
          title={copy.states.empty.title}
        />
      </div>
    );
  } else {
    body = slots.map((id) => {
      const request = fresh.get(id) ?? known[id];
      if (!request) return null;
      if (sent.has(id)) {
        return (
          <div
            className="ma-enter flex items-start gap-3 rounded-2xl bg-brand-tint p-3.5 text-brand-ink"
            key={`sent-${id}`}
            ref={confirmationRef(id)}
            role="status"
            tabIndex={-1}
          >
            <Icon className="mt-0.5 h-5 w-5 shrink-0" name="send" />
            <div className={`min-w-0 flex-1 space-y-1 ${wrap}`}>
              <p className="text-[13px] font-medium">{copy.heading(request.symptom)}</p>
              <p className="text-[15px] font-semibold leading-snug">{copy.sent}</p>
              <p className="text-sm leading-snug">{copy.states.answered.detail}</p>
            </div>
          </div>
        );
      }
      if (pendingNow.has(id) && request.status === "pending") {
        return (
          <ADRFollowUpForm
            copy={copy}
            key={`form-${id}`}
            locale={locale}
            onClosed={() => handleClosed(id)}
            onSent={handleSent}
            request={request}
          />
        );
      }
      // Closed while open here (answered elsewhere or withdrawn): show its outcome in place.
      const outcome =
        request.status === "pending"
          ? { ...request, status: "cancelled" as const, replacementRequestId: null }
          : request;
      return (
        <RequestOutcome
          copy={copy}
          key={`outcome-${id}`}
          locale={locale}
          request={outcome}
          timeZone={timeZone}
        />
      );
    });
  }

  return (
    <div className="space-y-3" lang={locale}>
      {body}
      <RecentRequests
        copy={copy}
        currentId={selected?.id ?? null}
        locale={locale}
        requests={overview.recent}
        timeZone={timeZone}
      />
    </div>
  );
}

function LoadingState({ locale }: { locale: Locale | undefined }) {
  return (
    <div aria-busy="true" className="space-y-3" lang={locale} role="status">
      {/* Before the saved locale resolves, announce in both supported locales. */}
      {locale ? (
        <span className="sr-only">{getADRFollowUpCopy(locale).states.loading}</span>
      ) : (
        <span className="sr-only">
          <span lang="en-US">{getADRFollowUpCopy("en-US").states.loading}</span>{" "}
          <span lang="es-MX">{getADRFollowUpCopy("es-MX").states.loading}</span>
        </span>
      )}
      <Skeleton className="h-32" />
      <Skeleton className="h-56" />
    </div>
  );
}

function RequestHeader({
  copy,
  request,
}: {
  copy: ADRFollowUpCopy;
  request: ADRFollowUpRequest;
}) {
  return (
    <header className="flex items-start gap-3 border-b border-line px-[14px] py-[13px]">
      <IconTile icon="note" size="sm" tone="note" />
      <div className="min-w-0 flex-1">
        <p className="font-mono text-xs uppercase tracking-[0.08em] text-muted">
          {copy.eyebrow}
        </p>
        <h2 className={`mt-1 text-[17px] font-semibold leading-snug text-ink ${wrap}`}>
          {copy.heading(request.symptom)}
        </h2>
        <p className={`mt-1 text-sm text-muted ${wrap}`}>
          {copy.reportedWith(request.suspectMedicationName)}
        </p>
      </div>
    </header>
  );
}

/** Read-only outcome of an answered or closed request. No score or causality. */
function RequestOutcome({
  copy,
  locale,
  request,
  timeZone,
}: {
  copy: ADRFollowUpCopy;
  locale: Locale;
  request: ADRFollowUpRequest;
  timeZone?: string | null;
}) {
  if (request.status === "answered") {
    const answeredOn = request.respondedAt
      ? formatFollowUpDate(request.respondedAt, locale, timeZone ?? undefined)
      : null;
    const responses = request.responses.filter(
      (item) => item.question in copy.questions && item.answer in copy.answers,
    );
    return (
      <section className="ma-enter overflow-hidden rounded-[22px] bg-surface" key={`answered-${request.id}`}>
        <RequestHeader copy={copy} request={request} />
        <div className="border-b border-line px-[14px] py-[13px]">
          <div className={`rounded-2xl bg-brand-tint p-3.5 text-brand-ink ${wrap}`}>
            <p className="text-[15px] font-semibold leading-snug">
              {copy.states.answered.title}
            </p>
            <p className="mt-1 text-sm leading-snug">{copy.states.answered.detail}</p>
          </div>
          {answeredOn && request.respondedAt ? (
            <p className="mt-2.5 text-[13px] text-muted">
              <time dateTime={request.respondedAt}>
                {copy.states.answered.answeredOn(answeredOn)}
              </time>
            </p>
          ) : null}
        </div>
        {responses.length > 0 ? (
          <div className="px-[14px] py-[13px]">
            <h3 className="text-[15px] font-semibold text-ink">
              {copy.states.answered.yourAnswers}
            </h3>
            <dl className="mt-2 divide-y divide-line">
              {responses.map((item) => (
                <div className="py-2.5" key={item.question}>
                  <dt className={`text-[13px] text-muted ${wrap}`}>
                    {copy.questions[item.question].label}
                  </dt>
                  <dd className="mt-0.5 text-sm font-semibold text-ink">
                    {copy.answers[item.answer]}
                  </dd>
                  {item.evidence ? (
                    <dd className={`mt-1 whitespace-pre-wrap text-sm text-ink-2 ${wrap}`}>
                      {item.evidence}
                    </dd>
                  ) : null}
                </div>
              ))}
            </dl>
          </div>
        ) : null}
      </section>
    );
  }

  return (
    <section className="ma-enter overflow-hidden rounded-[22px] bg-surface" key={`closed-${request.id}`}>
      <RequestHeader copy={copy} request={request} />
      <div className="px-[14px] py-[13px]">
        <div className={`flex items-start gap-2.5 rounded-2xl bg-surface-2 p-3.5 text-ink-2 ${wrap}`}>
          <Icon className="mt-0.5 h-5 w-5 shrink-0" name="info" />
          <div className="min-w-0 flex-1">
            <p className="text-[15px] font-semibold leading-snug text-ink">
              {copy.states.closed.title}
            </p>
            <p className="mt-1 text-sm leading-snug">{copy.states.closed.detail}</p>
          </div>
        </div>
        {request.replacementRequestId ? (
          <Link
            className={`${linkAction} mt-2`}
            href={followUpHref(request.replacementRequestId)}
            prefetch={false}
          >
            <span className={`min-w-0 ${wrap}`}>{copy.states.openNewer}</span>
            <Icon className="h-4 w-4 shrink-0" name="chevron" />
          </Link>
        ) : null}
      </div>
    </section>
  );
}

function RecentRequests({
  copy,
  currentId,
  locale,
  requests,
  timeZone,
}: {
  copy: ADRFollowUpCopy;
  currentId: string | null;
  locale: Locale;
  requests: ADRFollowUpRequest[];
  timeZone?: string | null;
}) {
  const [open, setOpen] = useState(false);
  const listId = useId();
  const rows = requests
    .filter((request) => request.status !== "pending")
    .slice(0, RECENT_SHOWN);
  if (rows.length === 0) return null;
  return (
    <section className="overflow-hidden rounded-[22px] bg-surface">
      <button
        aria-controls={listId}
        aria-expanded={open}
        className="ma-press flex min-h-14 w-full items-center gap-3 px-[14px] py-3 text-left hover:bg-surface-2/60"
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <IconTile icon="history" tone="neutral" />
        <span className={`min-w-0 flex-1 text-[15px] font-medium text-ink ${wrap}`}>
          {copy.recent.toggle(rows.length)}
        </span>
        <Icon
          className={`h-[18px] w-[18px] shrink-0 text-muted transition-transform duration-[240ms] ${open ? "rotate-180" : ""}`}
          name="chevronDown"
        />
      </button>
      <ul className="ma-enter divide-y divide-line border-t border-line" hidden={!open} id={listId}>
        {rows.map((request) => {
          const answered = request.status === "answered";
          const iso = answered
            ? request.respondedAt
            : (request.closedAt ?? request.createdAt);
          const date = iso
            ? formatFollowUpDate(iso, locale, timeZone ?? undefined)
            : null;
          return (
            <li key={request.id}>
              <Link
                aria-current={request.id === currentId ? "page" : undefined}
                className="ma-press flex min-h-14 w-full items-center gap-3 px-[14px] py-2.5 hover:bg-surface-2/60"
                href={followUpHref(request.id)}
                prefetch={false}
              >
                <span className={`min-w-0 flex-1 ${wrap}`}>
                  <span className="block text-[15px] font-medium text-ink">
                    {request.symptom}
                  </span>
                  <span className="mt-0.5 block text-[13px] text-muted">
                    {request.suspectMedicationName}
                  </span>
                  <span className="mt-1.5 flex flex-wrap items-center gap-2">
                    <Badge variant={answered ? "success" : "neutral"}>
                      {answered ? copy.recent.answered : copy.recent.closed}
                    </Badge>
                    {date && iso ? (
                      <time className="font-mono text-xs text-muted" dateTime={iso}>
                        {date}
                      </time>
                    ) : null}
                  </span>
                </span>
                <Icon className="h-4 w-4 shrink-0 text-muted" name="chevron" />
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
