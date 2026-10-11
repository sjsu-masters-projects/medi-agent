"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store/store";
import { careConversations } from "@/services/care-conversations";
import { getChatControlsCopy } from "@/content/chat-copy";
import { Icon } from "@/components/ui/icons";
import { Modal } from "@/components/ui/modal";
import { PullToRefresh } from "@/components/ui/pull-to-refresh";
import { ChatTextarea, chatButton, chatDisplayTime } from "./chat-presentation";
import { normalizeLocale } from "@/types";
import type { CareConversation, CareConversationMessage, ConversationDraft, ConversationRecipient } from "@/types/care-conversations";
import { conversationAccessDenied, conversationRoleLabel, conversationSendFailure, getConversationCopy, mergeConversationMessages } from "../../../../../packages/shared/src/utils/care-conversations";

const button = chatButton;
const input = "min-h-11 w-full rounded-[14px] border border-line-strong bg-surface px-3 py-2 text-base text-ink";
type Presentation = { compact?: boolean; onThreadPresentationChange?: (id: string | null) => void };

export function CareConversations({ locale = "en-US", audience = "patient", visible = true, ...presentation }: { locale?: string; audience?: "patient" | "clinician"; visible?: boolean } & Presentation) {
  const { accessToken, user } = useSelector((state: RootState) => state.auth);
  if (!accessToken || !user) return null;
  return <ConversationInbox key={user.id} token={accessToken} locale={locale} audience={audience} visible={visible} {...presentation} />;
}

function ConversationInbox({ token, locale, audience, visible, compact = false, onThreadPresentationChange }: { token: string; locale: string; audience: "patient" | "clinician"; visible: boolean } & Presentation) {
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
    const timer = setInterval(refresh, 15000);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", refresh);
      invalidateInbox();
    };
  }, [refreshInbox, invalidateInbox, visible, loading, opening, sending]);

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
      <label className="min-w-0 basis-full font-medium sm:flex-1 sm:basis-auto">{copy.recipient}
        <select className={input} value={recipient} disabled={loading || opening || sending} onChange={(event) => setRecipient(event.target.value)}>
          <option value="">{copy.choose}</option>
          {recipients.map((person) => <option key={person.id} value={person.id}>{person.name} · {conversationRoleLabel(person.role, locale)} · {person.clinic_name}</option>)}
        </select>
      </label>
      <button className={button} disabled={!recipient || loading || opening || sending} onClick={() => void open()} type="button">{opening ? copy.loading : copy.open}</button>
      <button className={button} disabled={loading || opening || sending} onClick={() => setAttempt((value) => value + 1)} type="button">{loading ? copy.loading : copy.refresh}</button>
    </div>;
  return <section className="min-w-0 space-y-4 text-sm text-ink-2" aria-busy={loading}>
    {compact ? <>
      <div hidden={focused} className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-mono text-xs uppercase tracking-[0.08em] text-muted">{locale === "es-MX" ? "Tu equipo clínico" : "Your care team"}</h2>
        <button className="min-h-11 px-2 py-2 text-sm font-semibold text-brand" type="button" onClick={() => setShowRecipient(true)}>{newLabel}</button>
        <button className={button} disabled={loading || opening || sending} onClick={() => setAttempt((value) => value + 1)} type="button">{loading ? copy.loading : copy.refresh}</button>
      </div>
      <Modal open={showRecipient} onClose={() => setShowRecipient(false)} title={newLabel} closeLabel={copy.cancel}>{recipientForm}</Modal>
    </> : recipientForm}
    {error && <p role="alert">{copy[error]}</p>}
    {pollFailed && <p role="alert">{copy.loadError}</p>}
    {loading ? <p role="status">{copy.loading}</p> : <>
      {!recipients.length && <p>{copy.noRecipients}</p>}
      {!compact && <h2 className="text-lg font-semibold text-ink">{copy.threads}</h2>}
      {!threads.length && <p>{copy.empty}</p>}
      <div hidden={focused}><PullToRefresh onRefresh={refreshInbox} busy={loading || opening || sending} label={copy.refresh}>
      <ul className="overflow-hidden rounded-[22px] bg-surface">
        {threads.map((thread) => <li key={thread.id}>
          <button ref={(element) => { if (element) contactButtons.current.set(thread.id, element); else contactButtons.current.delete(thread.id); }} className={`flex min-h-11 w-full items-center gap-3 border-b border-line p-3.5 text-left ${selected === thread.id ? "bg-brand-tint" : ""}`} type="button" aria-label={[`${name(thread)} · ${thread.clinic_name}`, thread.unread_count > 0 ? `${thread.unread_count} ${copy.unread}` : null, thread.last_message_preview, thread.last_message_at ? chatDisplayTime(thread.last_message_at, locale) : null].filter(Boolean).join(" · ")} aria-pressed={selected === thread.id} disabled={sending || opening} onClick={() => { setSelected(thread.id); setThreadFocused(true); }}>
            <span aria-hidden="true" className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-note-tint font-semibold text-note-ink">{name(thread).replace(/^Dr\.?\s*/i, "").split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("")}</span>
            <span className="min-w-0 flex-1">
            <span className="block break-words text-[15px] font-semibold text-ink">{name(thread)}</span>
            <span className="block break-words text-[13px] text-muted"><span className="sr-only"> · </span>{thread.clinic_name}</span>
            {thread.unread_count > 0 && <span className="inline-flex items-center gap-1.5 text-xs font-medium text-brand-ink"><span aria-hidden="true" className="h-2 w-2 rounded-full bg-brand" />{thread.unread_count} {copy.unread}</span>}
            <span className="block truncate text-muted">{thread.last_message_preview}</span>
            </span>
            {thread.last_message_at && <time className="shrink-0 font-mono text-xs text-muted" dateTime={thread.last_message_at}>{chatDisplayTime(thread.last_message_at, locale)}</time>}
          </button>
        </li>)}
      </ul>
      </PullToRefresh></div>
    </>}
    <p role="note" className="flex items-start gap-2.5 rounded-2xl bg-danger-tint p-3.5 text-sm text-[#7A2A1B]"><Icon name="alert" className="shrink-0" />{copy.notice}</p>
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
      /></div> : <p>{copy.select}</p>}
    </>}
  </section>;
}

function ConversationThread({ token, thread, locale, visible, draft, onDraft, onSending, onRead, onSaved, focusOnOpen, audience, backAction }: {
  token: string; thread: CareConversation; locale: string; visible: boolean; draft: ConversationDraft;
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
    onDraft({ body: draft.body, clientMessageId });
    busy.current = true;
    generation.current++;
    setSending(true);
    onSending(true);
    setConfirmNewKey(false);
    try {
      const message = await careConversations.send(token, thread.id, body, clientMessageId);
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
          body: draft.body,
          clientMessageId: failureKind === "invalid" ? undefined : clientMessageId,
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
  return <div className="flex min-h-[calc(100dvh-160px)] min-w-0 flex-col gap-4" aria-busy={loading}>
    <header className="flex items-center gap-2.5 border-b border-line-strong pb-3">
      {backAction}
      <span aria-hidden="true" className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-note-tint text-sm font-semibold text-note-ink">{contactName.replace(/^Dr\.?\s*/i, "").split(" ").filter(Boolean).slice(0, 2).map((part) => part[0]).join("")}</span>
      <div className="min-w-0 flex-1">
        <h3 ref={heading} tabIndex={-1} className="break-words text-base font-semibold text-ink">{contactName}</h3>
        <p className="break-words text-xs text-muted">{thread.clinic_name} · {audience === "patient" ? thread.patient_name : thread.clinician_name}</p>
      </div>
      <button className="min-h-11 shrink-0 rounded-xl bg-surface px-2 text-xs font-medium text-ink-2 disabled:opacity-50" disabled={sending || loading || denied} onClick={() => void load().catch(() => undefined)} type="button">{loading ? copy.loading : copy.refresh}</button>
    </header>
    <p className="text-xs text-muted">{getChatControlsCopy(normalizeLocale(locale)).humanOriginal}</p>
    {error && <p role="alert">{copy[error]}</p>}
    {loading && <p role="status">{copy.loading}</p>}
    {cursor && !denied && <button className={button} disabled={loading || sending} onClick={() => void load(cursor).catch(() => undefined)} type="button">{copy.older}</button>}
    {!loading && !denied && !messages.length && <p>{copy.noMessages}</p>}
    <ol className="flex-1 space-y-3" aria-label={copy.threads}>
      {messages.map((message) => <li key={message.id} className={`flex flex-col gap-1 ${message.sender_role === "patient" ? "items-end" : "items-start"}`}>
        <p className={`whitespace-pre-wrap break-words px-3.5 py-3 text-[15px] leading-relaxed ${message.sender_role === "patient" ? "max-w-[82%] rounded-[20px_20px_6px_20px] bg-brand text-white" : "max-w-[88%] rounded-[20px_20px_20px_6px] bg-surface text-ink"}`}>{message.body}</p>
        <p className="break-words text-xs text-muted">{message.sender_name} · {conversationRoleLabel(message.sender_role, locale)} · {thread.clinic_name} · <time className="font-mono" dateTime={message.created_at}>{chatDisplayTime(message.created_at, locale)}</time></p>
      </li>)}
    </ol>
    {draft.failure && <p role="alert">{copy[draft.failure]}</p>}
    {draft.failure === "mismatch" && !denied && <>
      <button className={button} type="button" onClick={() => setConfirmNewKey(true)}>{copy.prepareNew}</button>
      <Modal open={confirmNewKey} onClose={() => setConfirmNewKey(false)} title={copy.prepareNew} closeLabel={`${copy.cancel}: ${copy.prepareNew}`}><div role="alertdialog" aria-label={copy.prepareNew} className="space-y-3 rounded-2xl bg-danger-tint p-3 text-danger-ink">
        <p>{copy.confirmWarning}</p>
        <button className={button} type="button" onClick={() => { onDraft({ body: draft.body }); setConfirmNewKey(false); }}>{copy.confirmNew}</button>
        <button className={button} type="button" onClick={() => setConfirmNewKey(false)}>{copy.cancel}</button>
      </div></Modal>
    </>}
    {!denied && thread.writable && <form onSubmit={(event) => { event.preventDefault(); void send(); }} className="sticky bottom-0 mt-auto space-y-2 bg-background pt-3 pb-[calc(env(safe-area-inset-bottom)+12px)]">
      <div className="flex items-end gap-2">
      <label className="block min-w-0 flex-1 font-medium">{copy.message}
        <ChatTextarea className="mt-1 rounded-[26px] border border-line-strong bg-surface" maxLength={4000} value={draft.body} disabled={sending || Boolean(draft.clientMessageId)}
          onChange={(event) => onDraft({ body: event.target.value })} />
      </label>
      <button aria-label={sendLabel} className="flex h-[52px] w-[52px] shrink-0 items-center justify-center rounded-full bg-brand text-white hover:bg-brand-hover disabled:opacity-50"
        disabled={sending || loading || draft.failure === "mismatch" || !draft.body.trim() || draft.body.trim().length > 4000} type="submit"><Icon name="send" /><span className="sr-only">{sendLabel}</span></button>
      </div>
      <p aria-hidden="true" className="text-right text-xs text-muted">{sendLabel}</p>
      {draft.clientMessageId && !sending && draft.failure !== "mismatch" && <p>{copy.locked}</p>}
    </form>}
    {!thread.writable && !denied && <p>{copy.denied}</p>}
  </div>;
}
