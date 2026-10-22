"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store/store";
import { Skeleton } from "@/components/ui";
import { Icon } from "@/components/ui/icons";
import { TranslationInfo } from "@/components/ui/translation-note";
import { careConversations } from "@/services/care-conversations";
import { ConversationActivityReview } from "./conversation-activity";
import { confirmedTranslationFor, ReplyPreview, sendBlocker, useReplyPreview } from "./reply-preview";
import type { CareConversation, CareConversationMessage, ConversationDraft, ConversationRecipient } from "@/types/care-conversations";
import { applyTranslationResult, conversationAccessDenied, conversationRoleLabel, conversationSendFailure, getConversationCopy, mergeConversationMessages, requestPendingTranslations } from "../../../../../packages/shared/src/utils/care-conversations";

const button = "ma-press inline-flex h-[34px] shrink-0 items-center justify-center gap-2 rounded-[9px] border border-line-strong bg-surface px-4 text-[13px] font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8] disabled:hover:bg-surface";
const smallButton = "ma-press inline-flex h-8 shrink-0 items-center justify-center gap-1.5 rounded-lg border border-line-strong bg-surface px-3 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:cursor-not-allowed disabled:text-[#94A3B8] disabled:hover:bg-surface";
const field = "mt-1.5 block w-full rounded-[10px] border border-line-strong bg-surface px-3.5 font-normal text-ink outline-none transition placeholder:text-[#94A3B8] focus:border-primary focus:ring-4 focus:ring-[rgba(37,99,235,.12)] disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-muted";
const label = "block text-[13px] font-medium text-ink-2";
const alert = "flex items-start gap-2.5 rounded-xl border px-4 py-3 text-sm";

function initials(value: string) {
  return value.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase();
}

function shortTime(value: string, locale: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toDateString() === new Date().toDateString()
    ? date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" })
    : date.toLocaleDateString(locale, { month: "short", day: "numeric" });
}

export function CareConversations({ locale = "en-US", audience = "patient", visible = true, conversationId = null, clinicId = null, clinicEmpty = null }: { locale?: string; audience?: "patient" | "clinician"; visible?: boolean; conversationId?: string | null; clinicId?: string | null; clinicEmpty?: ReactNode }) {
  const { accessToken, user } = useSelector((state: RootState) => state.auth);
  if (!accessToken || !user) return null;
  return <ConversationInbox key={user.id} token={accessToken} locale={locale} audience={audience} visible={visible} conversationId={conversationId} clinicId={clinicId} clinicEmpty={clinicEmpty} />;
}

function ConversationInbox({ token, locale, audience, visible, conversationId, clinicId, clinicEmpty }: { token: string; locale: string; audience: "patient" | "clinician"; visible: boolean; conversationId: string | null; clinicId: string | null; clinicEmpty: ReactNode }) {
  const copy = getConversationCopy(locale);
  const [recipients, setRecipients] = useState<ConversationRecipient[]>([]);
  const [threads, setThreads] = useState<CareConversation[]>([]);
  const [recipient, setRecipient] = useState("");
  const [selected, setSelected] = useState<string | null>(conversationId);
  const [previousTarget, setPreviousTarget] = useState(conversationId);
  if (previousTarget !== conversationId) {
    setPreviousTarget(conversationId);
    setSelected(conversationId);
  }
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
        careConversations.recipients(token, controller.signal, clinicId),
        careConversations.list(token, controller.signal, clinicId),
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
  }, [token, clinicId]);

  useEffect(() => {
    const request = ++version.current;
    const controller = new AbortController();
    void Promise.resolve().then(() => {
      if (controller.signal.aborted) return;
      setLoading(true);
      setOpening(false);
      setError(null);
      return Promise.all([careConversations.recipients(token, controller.signal, clinicId), careConversations.list(token, controller.signal, clinicId)])
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
  }, [token, attempt, clinicId]);

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
    } catch (failure) {
      if (request === version.current) setError(conversationAccessDenied(failure) ? "denied" : "loadError");
    } finally {
      if (request === version.current) setOpening(false);
    }
  }

  const active = threads.find((thread) => thread.id === selected);
  const name = (thread: CareConversation) => audience === "patient" ? thread.clinician_name : thread.patient_name;
  return <section className="space-y-4 text-sm text-ink-2">
    {/* The emergency-services notice is patient safety copy; clinicians do not need it. */}
    {audience === "patient" && <p className={`${alert} border-warn-line bg-warn-soft text-warn-ink`}>
      <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
      <span>{copy.notice}</span>
    </p>}
    {error && <p role="alert" className={`${alert} border-risk-line bg-risk-soft text-risk-ink`}><Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" /><span>{copy[error]}</span></p>}
    {pollFailed && <p role="alert" className={`${alert} border-risk-line bg-risk-soft text-risk-ink`}><Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" /><span>{copy.loadError}</span></p>}
    {conversationId && !loading && !threads.some((thread) => thread.id === conversationId) && <p role="status" className="text-sm text-muted">The linked conversation is unavailable. Select an authorized conversation below.</p>}
    <div className="grid min-h-[calc(100dvh-180px)] grid-cols-1 overflow-hidden rounded-2xl border border-line bg-surface shadow-[var(--shadow-card)] md:h-[calc(100dvh-180px)] md:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[320px_minmax(0,1fr)]">
      <div className="flex min-h-0 min-w-0 flex-col border-b border-line md:border-b-0 md:border-r">
        <div className="space-y-3 border-b border-line px-4 py-4">
          <div className="flex items-center justify-between gap-3">
            {loading ? <p role="status" className="text-[13px] text-muted">{copy.loading}</p>
              : <h2 className="text-[15px] font-semibold text-ink">{copy.threads}</h2>}
            <button className={smallButton} disabled={loading || opening || sending} onClick={() => setAttempt((value) => value + 1)} type="button"><Icon name="refresh" className="h-3.5 w-3.5" />{copy.refresh}</button>
          </div>
          <div className="flex flex-col gap-2">
            <label className={`${label} min-w-0`}>{copy.recipient}
              <select className={`${field} h-[34px] text-[13px]`} value={recipient} disabled={loading || opening || sending} onChange={(event) => setRecipient(event.target.value)}>
                <option value="">{copy.choose}</option>
                {recipients.map((person) => <option key={person.id} value={person.id}>{person.name} · {conversationRoleLabel(person.role, locale)} · {person.clinic_name}</option>)}
              </select>
            </label>
            <button className={`${button} w-full justify-center`} disabled={!recipient || loading || opening || sending} onClick={() => void open()} type="button">{opening ? copy.loading : copy.open}</button>
          </div>
        </div>
        {loading ? <div aria-hidden="true" className="space-y-1 p-2">
          {[0, 1, 2].map((row) => <div key={row} className="flex items-center gap-3 px-2 py-2.5"><Skeleton variant="circle" className="h-12 w-12 shrink-0" /><div className="flex-1 space-y-2"><Skeleton variant="text" className="w-2/3" /><Skeleton variant="text" className="w-full" /></div></div>)}
        </div> : <div className="min-h-0 flex-1 overflow-y-auto">
          {!recipients.length && <p className="px-4 pt-3 text-[13px] text-muted">{copy.noRecipients}</p>}
          {!threads.length && <p className="px-4 pt-3 text-[13px] text-muted">{clinicId && clinicEmpty ? clinicEmpty : copy.empty}</p>}
          <ul className="space-y-0.5 p-2">
            {threads.map((thread) => <li key={thread.id}>
              <button className={`flex w-full items-center gap-3 rounded-xl px-2.5 py-2.5 text-left transition-colors disabled:cursor-not-allowed ${selected === thread.id ? "bg-[rgba(96,165,250,.1)]" : "hover:bg-[rgba(100,116,139,.06)]"}`} type="button" aria-pressed={selected === thread.id} disabled={sending || opening} onClick={() => setSelected(thread.id)}>
                <span aria-hidden="true" className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-track text-[13px] font-semibold text-ink-2">{initials(name(thread))}</span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="block truncate text-[13.5px] font-semibold text-ink">{name(thread)} · {thread.clinic_name}</span>
                    {thread.last_message_at && <time dateTime={thread.last_message_at} className="shrink-0 font-mono text-[11px] text-muted">{shortTime(thread.last_message_at, locale)}</time>}
                  </span>
                  <span className="mt-0.5 flex items-center gap-2">
                    <span className="block min-w-0 flex-1 truncate text-[13px] text-muted">{thread.last_message_preview}</span>
                    {thread.unread_count > 0 && <span className="inline-flex shrink-0 items-center gap-1.5 text-[11px] font-medium text-primary"><span aria-hidden="true" className="h-2 w-2 rounded-full bg-primary" /><span>{thread.unread_count} {copy.unread}</span></span>}
                  </span>
                </span>
              </button>
            </li>)}
          </ul>
        </div>}
      </div>
      <div className="flex min-h-[420px] min-w-0 flex-col md:min-h-0">
        {loading ? <div aria-hidden="true" className="flex-1 space-y-4 p-5">
          <Skeleton className="h-10 w-1/2" />
          <Skeleton className="ml-auto h-14 w-2/3" />
          <Skeleton className="h-14 w-1/2" />
        </div> : active ? <ConversationThread key={active.id} token={token} audience={audience} thread={active} locale={locale} visible={visible}
          draft={drafts[active.id] ?? { body: "" }}
          onDraft={(draft) => setDrafts((current) => ({ ...current, [active.id]: draft }))}
          onSending={setSending}
          onRead={() => { invalidateInbox(); void refreshInbox(); }}
          onSaved={(message) => {
            invalidateInbox();
            setThreads((current) => current.map((thread) => thread.id === message.conversation_id ? { ...thread, last_message_preview: message.body, last_message_at: message.created_at } : thread));
            void refreshInbox();
          }}
        /> : <div className="flex flex-1 flex-col items-center justify-center gap-3 px-6 py-12 text-center">
          <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-sunken text-muted"><Icon name="chat" className="h-6 w-6" /></span>
          <p className="max-w-[40ch] text-sm text-muted">{copy.select}</p>
        </div>}
      </div>
    </div>
  </section>;
}

function ConversationThread({ token, audience, thread, locale, visible, draft, onDraft, onSending, onRead, onSaved }: {
  token: string; audience: "patient" | "clinician"; thread: CareConversation; locale: string; visible: boolean; draft: ConversationDraft;
  onDraft: (draft: ConversationDraft) => void; onSending: (sending: boolean) => void;
  onRead: (id: string) => void; onSaved: (message: CareConversationMessage) => void;
}) {
  const copy = getConversationCopy(locale);
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

  /* LOC-003 decision 3: a clinician confirms the wording the patient will receive before
     sending it. A patient reading English needs no confirmation, which the preview says. */
  const requestPreview = useCallback(
    (body: string) => careConversations.preview(token, thread.id, body),
    [token, thread.id],
  );
  const preview = useReplyPreview(requestPreview, draft.body);
  const previewBlocker = audience === "clinician" && !draft.clientMessageId ? sendBlocker(preview.state, draft.body, preview.confirmed) : null;
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
    if (previewBlocker) return;
    const confirmedTranslation = draft.clientMessageId ? draft.confirmedTranslation ?? null : audience === "clinician"
      ? confirmedTranslationFor(preview.state, body, preview.confirmed)
      : null;
    const clientMessageId = draft.clientMessageId ?? crypto.randomUUID();
    onDraft({ body: draft.body, clientMessageId, confirmedTranslation });
    busy.current = true;
    generation.current++;
    setSending(true);
    onSending(true);
    setConfirmNewKey(false);
    try {
      const message = await careConversations.send(token, thread.id, body, clientMessageId, undefined, confirmedTranslation);
      if (!alive.current) return;
      onDraft({ body: "" });
      preview.reset();
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
          clientMessageId: failureKind === "invalid" || failureKind === "activityUnavailable" ? undefined : clientMessageId,
          confirmedTranslation,
          failure: failureKind,
        });
      }
    } finally {
      busy.current = false;
      if (alive.current) { setSending(false); onSending(false); }
    }
  }

  return <div className="flex min-h-0 flex-1 flex-col">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
      <h3 className="min-w-0 text-[15px] font-semibold text-ink">{thread.patient_name} · {thread.clinician_name} · {thread.clinic_name}</h3>
      <button className={smallButton} disabled={sending || loading || denied} onClick={() => void load().catch(() => undefined)} type="button"><Icon name="refresh" className="h-3.5 w-3.5" />{copy.refresh}</button>
    </div>
    <div className="flex min-h-0 flex-1 flex-col gap-3 px-5 py-4">
      {error && <p role="alert" className={`${alert} border-risk-line bg-risk-soft text-risk-ink`}><Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" /><span>{copy[error]}</span></p>}
      {loading && <p role="status" className="text-[13px] text-muted">{copy.loading}</p>}
      {cursor && !denied && <button className={`${smallButton} self-center`} disabled={loading || sending} onClick={() => void load(cursor).catch(() => undefined)} type="button"><Icon name="history" className="h-3.5 w-3.5" />{copy.older}</button>}
      {!loading && !denied && !messages.length && <p className="py-8 text-center text-[13px] text-muted">{copy.noMessages}</p>}
      <ol className="flex min-h-[160px] flex-1 flex-col gap-3 overflow-y-auto" aria-label={copy.threads}>
        {messages.map((message) => {
          const own = audience === "patient" ? message.sender_role === "patient" : message.sender_role !== "patient";
          const translation = message.translation;
          const translationLocale = message.translation_locale;
          const guardPassed = message.translation_guard_passed;
          // A clinician reads English: only a translation into English is ever shown.
          const sourceLabel = own ? undefined : (translationLocale === "en-US" ? "Translated from Spanish" : undefined);
          return <li key={message.id} className={`ma-bubble flex max-w-[78%] flex-col gap-1 ${own ? "items-end self-end" : "items-start self-start"}`}>
            <p className="px-1 text-[11px] text-muted">{message.sender_name} · {conversationRoleLabel(message.sender_role, locale)} · {thread.clinic_name} · <time className="font-mono" dateTime={message.created_at}>{new Date(message.created_at).toLocaleString(locale)}</time></p>
            <p className={`whitespace-pre-wrap break-words px-3.5 py-2.5 text-sm ${own ? "rounded-[18px_18px_6px_18px] bg-primary text-white" : "rounded-[18px_18px_18px_6px] bg-surface-2 text-ink"}`}>{message.body}</p>
            {message.activity_context ? <ConversationActivityReview activity={message.activity_context} token={token} conversationId={thread.id} messageId={message.id} patientId={thread.patient_id} /> : null}
            {message.translation_pending && !own ? <p role="status" className="px-1 text-[11px] text-muted">{copy.translating}</p> : null}
            {translation && sourceLabel && guardPassed === false ? <p className="px-1 text-[11px] text-muted">{copy.translationUnavailable}</p> : null}
            {translation && sourceLabel && guardPassed !== false ? <div className="mt-0.5 rounded-lg border border-line bg-surface px-3 py-2 text-xs text-ink-2">
              {/* LOC-003 item 5: the model and its caveat, one tap away from the text. */}
              <p className="flex flex-wrap items-center gap-1.5 text-[11px] font-medium text-muted"><Icon name="spark" className="h-3 w-3" />{sourceLabel}<TranslationInfo modelId={message.translation_model_id} /></p>
              <p className="mt-1 whitespace-pre-wrap break-words" lang="en-US">{translation}</p>
            </div> : null}
          </li>;
        })}
      </ol>
      {draft.failure && <p role="alert" className={`${alert} border-risk-line bg-risk-soft text-risk-ink`}><Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" /><span>{copy[draft.failure]}</span></p>}
      {draft.failure === "mismatch" && !denied && <>
        <button className={`${button} self-start`} type="button" onClick={() => setConfirmNewKey(true)}>{copy.prepareNew}</button>
        {confirmNewKey && <div role="alertdialog" aria-label={copy.prepareNew} className="ma-enter space-y-3 rounded-xl border border-warn-line bg-warn-soft px-4 py-3 text-sm text-warn-ink">
          <p>{copy.confirmWarning}</p>
          <div className="flex flex-wrap gap-2">
            <button className={button} type="button" onClick={() => { onDraft({ body: draft.body }); setConfirmNewKey(false); }}>{copy.confirmNew}</button>
            <button className={button} type="button" onClick={() => setConfirmNewKey(false)}>{copy.cancel}</button>
          </div>
        </div>}
      </>}
      {!thread.writable && !denied && <p className={`${alert} border-line bg-surface-2 text-ink-2`}><Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-muted" /><span>{copy.denied}</span></p>}
    </div>
    {!denied && thread.writable && <form onSubmit={(event) => { event.preventDefault(); void send(); }} className="space-y-2 border-t border-line px-5 py-4">
      {/* LOC-003 decision 3: what the patient will read, with its English back-translation. */}
      {audience === "clinician" ? <ReplyPreview body={draft.body} confirmed={preview.confirmed} disabled={sending || Boolean(draft.clientMessageId)} onConfirm={preview.setConfirmed} onPreview={() => void preview.preview()} state={preview.state} /> : null}
      <div className="flex items-end gap-2">
        <label className={`${label} min-w-0 flex-1`}>{copy.message}
          <textarea className={`${field} min-h-[42px] resize-y py-2.5 text-sm`} rows={2} maxLength={4000} value={draft.body} disabled={sending || Boolean(draft.clientMessageId)}
            onChange={(event) => onDraft({ body: event.target.value })} />
        </label>
        <button className="ma-press inline-flex h-[42px] shrink-0 items-center justify-center gap-2 rounded-[10px] bg-primary px-[18px] text-sm font-semibold text-white hover:bg-primary-hover disabled:cursor-not-allowed disabled:bg-track disabled:text-[#94A3B8]"
          disabled={sending || loading || draft.failure === "mismatch" || !draft.body.trim() || draft.body.trim().length > 4000 || Boolean(previewBlocker)} type="submit"><Icon name="send" className="h-4 w-4" />{sending ? copy.sending : draft.clientMessageId ? copy.retry : copy.send}</button>
      </div>
      {previewBlocker ? <p className="text-[13px] font-medium text-warn-ink" role="status">{previewBlocker}</p> : null}
      {draft.clientMessageId && !sending && draft.failure !== "mismatch" && <p className="text-[13px] text-muted">{copy.locked}</p>}
    </form>}
  </div>;
}
