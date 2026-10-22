"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store/store";
import { careConversations } from "@/services/care-conversations";
import { getChatControlsCopy } from "@/content/chat-copy";
import { Icon } from "@/components/ui/icons";
import { Modal } from "@/components/ui/modal";
import { ProcessingDots } from "@/components/ui/motion";
import { PullToRefresh } from "@/components/ui/pull-to-refresh";
import { ChatTextarea, chatButton, chatDisplayTime } from "./chat-presentation";
import { normalizeLocale, type Locale } from "@/types";
import { ConversationActivityAttachment, ConversationActivityContext } from "./conversation-activity";
import { TranslationNote } from "./translation-note";
import type { CareConversation, CareConversationMessage, ConversationDraft, ConversationRecipient } from "@/types/care-conversations";
import { applyTranslationResult, conversationAccessDenied, conversationRoleLabel, conversationSendFailure, getConversationCopy, mergeConversationMessages, requestPendingTranslations } from "../../../../../packages/shared/src/utils/care-conversations";

const button = chatButton;
const input = "min-h-[52px] w-full rounded-2xl border border-line-strong bg-surface px-4 py-2 text-base font-normal text-ink outline-none focus:border-brand focus:ring-4 focus:ring-brand/15";
type Presentation = {
  compact?: boolean;
  conversationId?: string | null;
  recipientId?: string | null;
  /** Patient tasks that belong to the care-team inbox, never the Nora thread. */
  inboxLead?: ReactNode;
  onThreadPresentationChange?: (id: string | null) => void;
};

export function CareConversations({ locale = "en-US", audience = "patient", visible = true, ...presentation }: { locale?: Locale; audience?: "patient" | "clinician"; visible?: boolean } & Presentation) {
  const { accessToken, user } = useSelector((state: RootState) => state.auth);
  if (!accessToken || !user) return null;
  return <ConversationInbox key={user.id} token={accessToken} locale={locale} audience={audience} visible={visible} {...presentation} />;
}

function ConversationInbox({ token, locale, audience, visible, compact = false, conversationId, recipientId, inboxLead, onThreadPresentationChange }: { token: string; locale: Locale; audience: "patient" | "clinician"; visible: boolean } & Presentation) {
  const copy = getConversationCopy(locale);
  const [recipients, setRecipients] = useState<ConversationRecipient[]>([]);
  const [threads, setThreads] = useState<CareConversation[]>([]);
  const [recipient, setRecipient] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [threadFocused, setThreadFocused] = useState(false);
  const [showRecipient, setShowRecipient] = useState(false);
  const contactButtons = useRef(new Map<string, HTMLButtonElement>());
  const backLabel = locale === "es-MX" ? "Volver a conversaciones" : "Back to conversations";
  const newLabel = locale === "es-MX" ? "Nuevo mensaje" : "New message";
  const [drafts, setDrafts] = useState<Record<string, ConversationDraft>>({});
  const [loading, setLoading] = useState(true);
  const [opening, setOpening] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<"loadError" | "denied" | null>(null);
  const [attempt, setAttempt] = useState(0);
  const version = useRef(0);
  const pollVersion = useRef(0);
  const pollController = useRef<AbortController | null>(null);
  const [pollFailed, setPollFailed] = useState(false);
  const handledDestination = useRef<string | null>(null);
  const [destinationUnavailable, setDestinationUnavailable] = useState(false);
  const inboxUi = useRef({ visible, loading, opening, sending });
  useEffect(() => { inboxUi.current = { visible, loading, opening, sending }; }, [visible, loading, opening, sending]);
  const invalidateInbox = useCallback(() => {
    pollVersion.current++;
    pollController.current?.abort();
  }, []);

  const refreshInbox = useCallback(async () => {
    const ui = inboxUi.current;
    if (!ui.visible || ui.loading || ui.opening || ui.sending || document.visibilityState !== "visible") return;
    const session = version.current;
    const request = ++pollVersion.current;
    pollController.current?.abort();
    const controller = new AbortController();
    pollController.current = controller;
    try {
      const [people, conversations] = await Promise.all([
        careConversations.recipients(token, controller.signal),
        careConversations.list(token, controller.signal),
      ]);
      if (controller.signal.aborted || request !== pollVersion.current || session !== version.current) return;
      setRecipients(people);
      setRecipient((current) => people.some((person) => person.id === current) ? current : "");
      setThreads(conversations);
      setSelected((current) => conversations.some((thread) => thread.id === current) ? current : null);
      setPollFailed(false);
    } catch (failure) {
      if (controller.signal.aborted || request !== pollVersion.current || session !== version.current) return;
      if (conversationAccessDenied(failure)) {
        setThreads([]); setRecipients([]); setSelected(null); setError("denied");
      } else setPollFailed(true);
    }
  }, [token]);

  useEffect(() => {
    const request = ++version.current;
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      setLoading(true);
      setOpening(false);
      setError(null);
      return Promise.all([careConversations.recipients(token, controller.signal), careConversations.list(token, controller.signal)])
        .then(([people, conversations]) => {
          if (request !== version.current || controller.signal.aborted) return;
          setRecipients(people);
          setThreads(conversations);
          setRecipient((value) => people.some((person) => person.id === value) ? value : "");
          setSelected((value) => conversations.some((thread) => thread.id === value) ? value : null);
        }).catch((failure: unknown) => {
          if (request !== version.current || controller.signal.aborted) return;
          setError(conversationAccessDenied(failure) ? "denied" : "loadError");
          setRecipients([]);
          setThreads([]);
          setSelected(null);
        }).finally(() => {
          if (request === version.current && !controller.signal.aborted) setLoading(false);
        });
    });
    return () => { controller.abort(); version.current = request + 1; };
  }, [token, attempt]);

  useEffect(() => {
    if (!visible || loading || opening || sending) return;
    const refresh = () => { void refreshInbox(); };
    refresh();
    // Paused while the tab is hidden; it refreshes once when the tab shows again.
    const timer = setInterval(() => { if (document.visibilityState !== "hidden") refresh(); }, 15000);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
      invalidateInbox();
    };
  }, [refreshInbox, invalidateInbox, visible, loading, opening, sending]);

  useEffect(() => {
    const destination = conversationId ? `conversation:${conversationId}` : recipientId ? `recipient:${recipientId}` : null;
    if (!destination) { handledDestination.current = null; return; }
    if (loading || !visible || error || handledDestination.current === destination) return;
    handledDestination.current = destination;
    const thread = conversationId ? threads.find((item) => item.id === conversationId) : threads.find((item) => item.clinician_id === recipientId);
    if (thread) { setSelected(thread.id); setThreadFocused(true); setDestinationUnavailable(false); return; }
    // A missing exact thread must never fall back to another recipient.
    setSelected(null); setThreadFocused(false);
    if (conversationId || !recipients.some((person) => person.id === recipientId)) { setDestinationUnavailable(true); return; }
    const session = version.current;
    setOpening(true); setDestinationUnavailable(false);
    void careConversations.open(token, recipientId!).then((opened) => {
      if (session !== version.current || handledDestination.current !== destination) return;
      setThreads((current) => [opened, ...current.filter((item) => item.id !== opened.id)]);
      setSelected(opened.id); setThreadFocused(true);
    }).catch(() => { if (session === version.current && handledDestination.current === destination) setDestinationUnavailable(true); })
      .finally(() => { if (session === version.current && handledDestination.current === destination) setOpening(false); });
  }, [conversationId, recipientId, loading, visible, error, threads, recipients, token]);

  async function open() {
    if (!recipient || opening || sending) return;
    const request = version.current;
    setOpening(true);
    setError(null);
    try {
      const thread = await careConversations.open(token, recipient);
      if (request !== version.current) return;
      setThreads((current) => [thread, ...current.filter((item) => item.id !== thread.id)]);
      setSelected(thread.id);
      setThreadFocused(true);
      setShowRecipient(false);
    } catch (failure) {
      if (request === version.current) setError(conversationAccessDenied(failure) ? "denied" : "loadError");
    } finally {
      if (request === version.current) setOpening(false);
    }
  }

  const active = threads.find((thread) => thread.id === selected);
  const presentationId = compact && threadFocused && visible ? active?.id ?? null : null;
  useEffect(() => {
    onThreadPresentationChange?.(presentationId);
    return () => onThreadPresentationChange?.(null);
  }, [presentationId, onThreadPresentationChange]);
  const name = (thread: CareConversation) => audience === "patient" ? thread.clinician_name : thread.patient_name;
  const focused = compact && threadFocused && Boolean(active);
  const backAction = focused ? <button className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-surface text-ink-2 disabled:opacity-50" type="button" aria-label={backLabel} disabled={sending || opening} onClick={() => { setThreadFocused(false); requestAnimationFrame(() => { if (selected) contactButtons.current.get(selected)?.focus(); }); }}><Icon name="back" /></button> : undefined;
  const recipientForm = <div className="flex flex-wrap items-end gap-3">
      <label className="min-w-0 basis-full space-y-2 text-sm font-semibold text-ink-2 sm:flex-1 sm:basis-auto">{copy.recipient}
        <select className={input} value={recipient} disabled={loading || opening || sending} onChange={(event) => setRecipient(event.target.value)}>
          <option value="">{copy.choose}</option>
          {recipients.map((person) => <option key={person.id} value={person.id}>{person.name} · {conversationRoleLabel(person.role, locale)} · {person.clinic_name}</option>)}
        </select>
      </label>
      <button className={compact ? "ma-press min-h-[52px] w-full rounded-2xl bg-brand px-4 text-base font-semibold text-white hover:bg-brand-hover disabled:opacity-40" : button} disabled={!recipient || loading || opening || sending} onClick={() => void open()} type="button">{opening ? copy.loading : copy.open}</button>
      {!compact ? <button className={button} disabled={loading || opening || sending} onClick={() => setAttempt((value) => value + 1)} type="button">{loading ? copy.loading : copy.refresh}</button> : null}
    </div>;
  return <section className="min-w-0 space-y-4 text-sm text-ink-2" aria-busy={loading}>
    {destinationUnavailable && <p role="alert" className="rounded-2xl bg-danger-tint p-3 text-danger-ink">{locale === "es-MX" ? "Esta conversación no está disponible. Elige un contacto autorizado." : "This conversation is unavailable. Choose an authorized contact."}</p>}
    {compact ? <>
      <div hidden={focused} className="flex items-end justify-between gap-2 pl-1.5 pt-2">
        <h2 className="pb-2 font-mono text-xs uppercase tracking-[0.08em] text-muted">{locale === "es-MX" ? "Tu equipo clínico" : "Your care team"}</h2>
        <div className="flex items-center gap-0.5">
          <button className="ma-press inline-flex min-h-11 items-center gap-1.5 rounded-xl px-2.5 text-sm font-semibold text-brand hover:bg-brand-tint/60" type="button" onClick={() => setShowRecipient(true)}><Icon name="plus" className="h-4 w-4" strokeWidth={2.2} />{newLabel}</button>
          <button aria-label={loading ? copy.loading : copy.refresh} title={copy.refresh} className="ma-press flex h-11 w-11 items-center justify-center rounded-xl text-muted hover:bg-surface hover:text-ink-2 disabled:opacity-50" disabled={loading || opening || sending} onClick={() => setAttempt((value) => value + 1)} type="button"><Icon name="refresh" className={`h-[18px] w-[18px] ${loading ? "motion-safe:animate-spin" : ""}`} /></button>
        </div>
      </div>
      <Modal open={showRecipient} onClose={() => setShowRecipient(false)} title={newLabel} closeLabel={copy.cancel}>{recipientForm}</Modal>
    </> : recipientForm}
    {compact && inboxLead ? <div hidden={focused} className="empty:hidden">{inboxLead}</div> : null}
    {error && <p role="alert" className="flex items-start gap-2 rounded-2xl bg-danger-tint px-3.5 py-3 text-sm text-danger-ink"><Icon name="alert" className="h-[18px] w-[18px] shrink-0" />{copy[error]}</p>}
    {pollFailed && <p role="alert" className="flex items-start gap-2 rounded-2xl bg-danger-tint px-3.5 py-3 text-sm text-danger-ink"><Icon name="alert" className="h-[18px] w-[18px] shrink-0" />{copy.loadError}</p>}
    {loading ? <p role="status" className={compact ? "flex items-center gap-3 rounded-[22px] bg-surface px-4 py-4 text-muted" : undefined}>{compact ? <span aria-hidden="true" className="ma-skeleton h-12 w-12 shrink-0 rounded-full" /> : null}{copy.loading}</p> : <>
      {!recipients.length && <p className={compact ? "px-1.5 text-[13px] text-muted" : undefined}>{copy.noRecipients}</p>}
      {!compact && <h2 className="text-lg font-semibold text-ink">{copy.threads}</h2>}
      {!threads.length && <p className={compact ? "rounded-[22px] bg-surface px-4 py-5 text-center text-[15px] text-muted" : undefined}>{copy.empty}</p>}
      <div hidden={focused}><PullToRefresh onRefresh={refreshInbox} busy={opening || sending} label={copy.refresh}>
      <ul className={`overflow-hidden rounded-[22px] bg-surface [&>li+li]:border-t [&>li+li]:border-line ${threads.length ? "" : "hidden"}`}>
        {threads.map((thread) => <li key={thread.id}>
          <button ref={(element) => { if (element) contactButtons.current.set(thread.id, element); else contactButtons.current.delete(thread.id); }} className={`flex min-h-11 w-full items-center gap-3 px-[14px] py-3.5 text-left transition-colors duration-[160ms] hover:bg-[#FBF7F0] disabled:opacity-60 ${selected === thread.id && !compact ? "bg-brand-tint" : ""}`} type="button" aria-label={[`${name(thread)} · ${thread.clinic_name}`, thread.unread_count > 0 ? `${thread.unread_count} ${copy.unread}` : null, thread.last_message_preview, thread.last_message_at ? chatDisplayTime(thread.last_message_at, locale) : null].filter(Boolean).join(" · ")} aria-pressed={selected === thread.id} disabled={sending || opening} onClick={() => { setSelected(thread.id); setThreadFocused(true); }}>
            <span aria-hidden="true" className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-note-tint text-[15px] font-semibold text-note-ink">{name(thread).replace(/^Dr\.?\s*/i, "").split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("")}</span>
            <span className="min-w-0 flex-1">
            <span className="flex items-baseline gap-2">
              <span className="min-w-0 flex-1 break-words text-[15px] font-semibold text-ink">{name(thread)}</span>
              {thread.last_message_at && <time className="shrink-0 font-mono text-xs text-muted" dateTime={thread.last_message_at}>{chatDisplayTime(thread.last_message_at, locale)}</time>}
            </span>
            <span className="block break-words text-[13px] text-muted"><span className="sr-only"> · </span>{thread.clinic_name}</span>
            <span className="mt-0.5 flex items-center gap-2">
              <span className={`min-w-0 flex-1 truncate text-sm ${thread.unread_count > 0 ? "font-medium text-ink" : "text-muted"}`}>{thread.last_message_preview}</span>
              {thread.unread_count > 0 && <span className="inline-flex shrink-0 items-center gap-1.5"><span aria-hidden="true" className="h-[9px] w-[9px] rounded-full bg-brand" /><span className="sr-only">{thread.unread_count} {copy.unread}</span></span>}
            </span>
            </span>
          </button>
        </li>)}
      </ul>
      </PullToRefresh></div>
    </>}
    <p role="note" className={`flex items-start gap-2.5 text-sm leading-snug text-[#7A2A1B] ${compact && focused ? "-mx-4 -mt-4 justify-center bg-danger-tint px-4 py-2 text-center text-[13px]" : "rounded-2xl bg-danger-tint px-3.5 py-3"}`}><Icon name="alert" className="mt-px h-[18px] w-[18px] shrink-0" />{copy.notice}</p>
    {!loading && <>
      {active ? <div hidden={compact && !focused}><ConversationThread key={active.id} token={token} thread={active} locale={locale} visible={visible && (!compact || focused)} focusOnOpen={compact}
        audience={audience} backAction={backAction}
        draft={drafts[active.id] ?? { body: "" }}
        onDraft={(draft) => setDrafts((current) => ({ ...current, [active.id]: draft }))}
        onSending={setSending}
        onRead={() => { invalidateInbox(); void refreshInbox(); }}
        onSaved={(message) => {
          invalidateInbox();
          setThreads((current) => current.map((thread) => thread.id === message.conversation_id ? { ...thread, last_message_preview: message.body, last_message_at: message.created_at } : thread));
          void refreshInbox();
        }}
      /></div> : <p hidden={compact}>{copy.select}</p>}
    </>}
  </section>;
}

function ConversationThread({ token, thread, locale, visible, draft, onDraft, onSending, onRead, onSaved, focusOnOpen, audience, backAction }: {
  token: string; thread: CareConversation; locale: Locale; visible: boolean; draft: ConversationDraft;
  onDraft: (draft: ConversationDraft) => void; onSending: (sending: boolean) => void;
  onRead: (id: string) => void; onSaved: (message: CareConversationMessage) => void;
  focusOnOpen?: boolean;
  audience: "patient" | "clinician"; backAction?: ReactNode;
}) {
  const copy = getConversationCopy(locale);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (!visible || !focusOnOpen) return;
    const frame = requestAnimationFrame(() => heading.current?.focus());
    return () => cancelAnimationFrame(frame);
  }, [visible, focusOnOpen]);
  const [messages, setMessages] = useState<CareConversationMessage[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [sending, setSending] = useState(false);
  const [denied, setDenied] = useState(false);
  const [error, setError] = useState<"loadError" | "denied" | "readError" | "savedRefreshError" | null>(null);
  const [confirmNewKey, setConfirmNewKey] = useState(false);
  const [readAttempt, setReadAttempt] = useState(0);
  // LOC-003: message IDs whose original (pre-translation) text the patient chose to reveal.
  const [showOriginal, setShowOriginal] = useState<Set<string>>(new Set());
  const alive = useRef(false);
  const generation = useRef(0);
  const busy = useRef(false);
  const readThrough = useRef<string | null>(null);
  const deniedRef = useRef(false);
  const renderedMessages = useRef(messages);
  useEffect(() => { renderedMessages.current = messages; }, [messages]);
  const visibleRef = useRef(visible);
  useEffect(() => { visibleRef.current = visible; }, [visible]);
  const callbacks = useRef({ onRead, onSaved, onSending });
  useEffect(() => { callbacks.current = { onRead, onSaved, onSending }; }, [onRead, onSaved, onSending]);

  const load = useCallback(async (before?: string, polling = false) => {
    if (busy.current || deniedRef.current) return;
    const request = ++generation.current;
    if (!polling) setLoading(true);
    try {
      const page = await careConversations.messages(token, thread.id, before);
      if (!alive.current || request !== generation.current) return;
      const overlaps = page.items.some((item) => renderedMessages.current.some((old) => old.id === item.id));
      setMessages((current) => before ? mergeConversationMessages(page.items, current)
        : polling && overlaps ? mergeConversationMessages(current, page.items) : page.items);
      if (!polling || !overlaps) setCursor(page.next_cursor);
      setError(null);
      setReadAttempt((value) => value + 1);
    } catch (failure) {
      if (!alive.current || request !== generation.current) return;
      if (conversationAccessDenied(failure)) { deniedRef.current = true; setDenied(true); setMessages([]); setCursor(null); }
      setError(conversationAccessDenied(failure) ? "denied" : "loadError");
      throw failure;
    } finally {
      if (alive.current && request === generation.current) setLoading(false);
    }
  }, [token, thread.id]);

  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; onSending(false); };
  }, [load, onSending]);

  useEffect(() => {
    if (!visible) return;
    void load().catch(() => undefined);
    const refresh = () => {
      if (alive.current && document.visibilityState === "visible" && !busy.current) void load(undefined, true).catch(() => undefined);
    };
    const timer = setInterval(refresh, 15000);
    document.addEventListener("visibilitychange", refresh);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", refresh); };
  }, [load, visible]);

  // LOC-003: translations are requested one message at a time after the read, three at most in
  // parallel, so reading, typing and sending never wait for a model. The original shows first.
  const requestedTranslations = useRef(new Set<string>());
  useEffect(() => {
    if (!messages.some((message) => message.translation_pending && !requestedTranslations.current.has(message.id))) return;
    void requestPendingTranslations(
      messages,
      requestedTranslations.current,
      (messageId) => careConversations.translate(token, thread.id, messageId),
      (messageId, result) => setMessages((current) => current.map((message) => message.id === messageId ? applyTranslationResult(message, result) : message)),
      () => alive.current,
    );
  }, [messages, token, thread.id]);

  // Runs after rendering: the marker is the newest displayed message, never a server clock.
  const lastId = messages.at(-1)?.id;
  useEffect(() => {
    if (!visible || !lastId || denied || document.visibilityState !== "visible" || readThrough.current === lastId) return;
    let active = true;
    void careConversations.read(token, thread.id, lastId).then(() => {
      if (!active) return;
      readThrough.current = lastId;
      callbacks.current.onRead(thread.id);
    }).catch((failure: unknown) => {
      if (!active) return;
      if (conversationAccessDenied(failure)) { deniedRef.current = true; setDenied(true); setMessages([]); setCursor(null); setError("denied"); }
      else setError("readError");
    });
    return () => { active = false; };
  }, [token, thread.id, lastId, denied, readAttempt, visible]);

  async function send() {
    const body = draft.body.trim();
    if (!body || body.length > 4000 || busy.current || denied || !thread.writable || draft.failure === "mismatch") return;
    const clientMessageId = draft.clientMessageId ?? crypto.randomUUID();
    onDraft({ ...draft, body: draft.body, clientMessageId });
    busy.current = true;
    generation.current++;
    setSending(true);
    onSending(true);
    setConfirmNewKey(false);
    try {
      const message = draft.carePlanItemId
        ? await careConversations.send(token, thread.id, body, clientMessageId, draft.carePlanItemId)
        : await careConversations.send(token, thread.id, body, clientMessageId);
      if (!alive.current) return;
      onDraft({ body: "" });
      if (deniedRef.current) return;
      setMessages((current) => mergeConversationMessages(current, [message]));
      callbacks.current.onSaved(message);
      busy.current = false;
      if (visibleRef.current && document.visibilityState === "visible") {
        try { await load(); } catch { if (alive.current) setError((value) => value === "denied" ? value : "savedRefreshError"); }
      }
    } catch (failure) {
      if (!alive.current) return;
      if (conversationAccessDenied(failure)) { deniedRef.current = true; setDenied(true); setMessages([]); setCursor(null); setError("denied"); }
      else {
        const failureKind = conversationSendFailure(failure);
        onDraft({
          carePlanItemId: draft.carePlanItemId,
          body: draft.body,
          clientMessageId: failureKind === "invalid" || failureKind === "activityUnavailable" ? undefined : clientMessageId,
          failure: failureKind,
        });
      }
    } finally {
      busy.current = false;
      if (alive.current) { setSending(false); onSending(false); }
    }
  }

  const contactName = audience === "patient" ? thread.clinician_name : thread.patient_name;
  const sendLabel = sending ? copy.sending : draft.clientMessageId ? copy.retry : copy.send;
  const compactThread = Boolean(focusOnOpen);
  const initials = contactName.replace(/^Dr\.?\s*/i, "").split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("");
  return <div className={`flex min-w-0 flex-col gap-3 ${compactThread ? "min-h-[calc(100dvh-32px)]" : "min-h-[calc(100dvh-160px)]"}`} aria-busy={loading}>
    <header className={`flex items-center gap-2.5 ${compactThread ? "sticky top-0 z-20 -mx-4 bg-background/90 px-3 pt-1 pb-2.5 backdrop-blur-md" : "border-b border-line-strong pb-3"}`}>
      {backAction}
      <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-note-tint text-[13px] font-semibold text-note-ink">{initials}</span>
      <div className="min-w-0 flex-1">
        <h3 ref={heading} tabIndex={-1} className="break-words text-base font-semibold leading-tight text-ink outline-none">{contactName}</h3>
        <p className="break-words text-xs text-muted">{thread.clinic_name} · {audience === "patient" ? thread.patient_name : thread.clinician_name}</p>
      </div>
      <button aria-label={loading ? copy.loading : copy.refresh} title={copy.refresh} className="ma-press flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface text-ink-2 hover:bg-surface-2 disabled:opacity-50" disabled={sending || loading || denied} onClick={() => void load().catch(() => undefined)} type="button"><Icon name="refresh" className={`h-[18px] w-[18px] ${loading ? "motion-safe:animate-spin" : ""}`} /></button>
    </header>
    <p className="text-center text-xs text-muted">{getChatControlsCopy(normalizeLocale(locale)).humanOriginal}</p>
    {error && <p role="alert" className="rounded-2xl bg-danger-tint px-3.5 py-3 text-sm text-danger-ink">{copy[error]}</p>}
    {loading && <p role="status" className="text-center text-sm text-muted">{copy.loading}</p>}
    {cursor && !denied && <button className={button + " self-center"} disabled={loading || sending} onClick={() => void load(cursor).catch(() => undefined)} type="button">{copy.older}</button>}
    {!loading && !denied && !messages.length && <p className="py-6 text-center text-[15px] text-muted">{copy.noMessages}</p>}
    <ol className="flex flex-1 flex-col gap-3" aria-label={copy.threads}>
      {messages.map((message) => {
        const own = message.sender_role === "patient";
        // LOC-003: a translation from the other party (e.g. the clinician's English reply
        // rendered in the patient's Spanish). The original stays available behind a toggle.
        // A translation whose safety check failed (numbers changed) is never shown; the original
        // stays the main text and a short note says the automatic translation is unavailable.
        const guardFailed = !own && Boolean(message.translation) && message.translation_guard_passed === false;
        // Defence in depth: only a translation into the patient's own language is ever the main text.
        const hasTranslation = !own && Boolean(message.translation) && !guardFailed && message.translation_locale === locale;
        const originalShown = showOriginal.has(message.id);
        const displayBody = hasTranslation && !originalShown ? (message.translation ?? message.body) : message.body;
        const translatedLabel = message.translation_locale === "es-MX" ? copy.translatedFromEnglish : copy.translatedFromSpanish;
        return <li key={message.id} className={`ma-bubble flex flex-col gap-1 ${own ? "items-end" : "items-start"}`}>
          {message.activity_context ? <ConversationActivityContext activity={message.activity_context} locale={locale} /> : null}
          <p className={`whitespace-pre-wrap break-words text-[15px] leading-[1.45] [overflow-wrap:anywhere] ${own ? "max-w-[82%] rounded-[20px_20px_6px_20px] bg-brand px-3.5 py-[11px] text-white" : "max-w-[88%] rounded-[20px_20px_20px_6px] bg-surface px-[15px] py-[13px] text-ink shadow-[0_1px_0_rgba(16,32,43,.04)]"}`}>{displayBody}</p>
          {message.translation_pending && !own ? <p role="status" className="max-w-[88%] px-1 text-[11px] text-muted">{copy.translating}</p> : null}
          {guardFailed ? <p className="flex max-w-[88%] flex-wrap items-center gap-x-1 px-1 text-[11px] text-muted">
            <span>{copy.translationUnavailable}</span>
            <TranslationNote copy={copy} modelId={message.translation_model_id} />
          </p> : null}
          {hasTranslation ? <p className={`flex max-w-[88%] flex-wrap items-center gap-x-1 px-1 text-[11px] text-muted`}>
            {originalShown ? null : <span>{translatedLabel} ·</span>}
            <button type="button" className="underline underline-offset-2 hover:text-ink" onClick={() => setShowOriginal((current) => { const next = new Set(current); if (next.has(message.id)) next.delete(message.id); else next.add(message.id); return next; })}>{originalShown ? copy.showTranslation : copy.showOriginal}</button>
            {/* LOC-003 item 5: a computer made this, it may be wrong, and the original counts. */}
            <TranslationNote copy={copy} modelId={message.translation_model_id} />
          </p> : null}
          <p className={`max-w-[88%] break-words px-1 text-[11px] text-muted ${own ? "text-right" : ""}`}>{message.sender_name} · {conversationRoleLabel(message.sender_role, locale)} · {thread.clinic_name} · <time className="font-mono" dateTime={message.created_at}>{chatDisplayTime(message.created_at, locale)}</time></p>
        </li>;
      })}
    </ol>
    {draft.failure && <p role="alert" className="rounded-2xl bg-danger-tint px-3.5 py-3 text-sm text-danger-ink">{copy[draft.failure]}</p>}
    {draft.failure === "mismatch" && !denied && <>
      <button className={button} type="button" onClick={() => setConfirmNewKey(true)}>{copy.prepareNew}</button>
      <Modal open={confirmNewKey} onClose={() => setConfirmNewKey(false)} title={copy.prepareNew} closeLabel={`${copy.cancel}: ${copy.prepareNew}`}><div role="alertdialog" aria-label={copy.prepareNew} className="space-y-3 rounded-2xl bg-danger-tint p-4 text-danger-ink">
        <p>{copy.confirmWarning}</p>
        <button className={button} type="button" onClick={() => { onDraft({ body: draft.body, carePlanItemId: draft.carePlanItemId }); setConfirmNewKey(false); }}>{copy.confirmNew}</button>
        <button className={button} type="button" onClick={() => setConfirmNewKey(false)}>{copy.cancel}</button>
      </div></Modal>
    </>}
    {!denied && thread.writable && <form onSubmit={(event) => { event.preventDefault(); void send(); }} className={`sticky bottom-0 mt-auto space-y-1.5 bg-background pt-2 ${compactThread ? "-mx-4 px-3 pb-[calc(env(safe-area-inset-bottom)+12px)]" : "pb-3"}`}>
      <ConversationActivityAttachment token={token} patientId={thread.patient_id} locale={locale} value={draft.carePlanItemId} disabled={sending || Boolean(draft.clientMessageId)} onChange={(id) => onDraft({ ...draft, carePlanItemId: id, failure: undefined })} />
      <div className="flex items-end gap-2">
      <label className="block min-w-0 flex-1 font-medium">
        <span className={compactThread ? "sr-only" : "mb-1 block text-sm text-ink-2"}>{copy.message}</span>
        <ChatTextarea className="min-h-[52px] rounded-[26px] border border-line-strong bg-surface py-[14px] pl-[18px] transition focus:border-brand focus:ring-4 focus:ring-brand/12" maxLength={4000} value={draft.body} disabled={sending || Boolean(draft.clientMessageId)}
          placeholder={compactThread ? copy.message + "…" : undefined}
          onChange={(event) => onDraft({ body: event.target.value, carePlanItemId: draft.carePlanItemId })} />
      </label>
      <button aria-label={sendLabel} className="ma-press flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full bg-brand text-white shadow-[var(--shadow-fab)] hover:bg-brand-hover disabled:opacity-40 disabled:shadow-none"
        disabled={sending || loading || draft.failure === "mismatch" || !draft.body.trim() || draft.body.trim().length > 4000} type="submit">{sending ? <ProcessingDots className="bg-white" /> : <Icon name="send" />}<span className="sr-only">{sendLabel}</span></button>
      </div>
      {sending || draft.clientMessageId ? <p aria-hidden="true" className="px-2 text-right text-xs text-muted">{sendLabel}</p> : null}
      {draft.clientMessageId && !sending && draft.failure !== "mismatch" && <p className="px-2 text-[13px] text-muted">{copy.locked}</p>}
    </form>}
    {!thread.writable && !denied && <p className="rounded-2xl bg-surface-2 px-3.5 py-3 text-sm text-muted">{copy.denied}</p>}
  </div>;
}
