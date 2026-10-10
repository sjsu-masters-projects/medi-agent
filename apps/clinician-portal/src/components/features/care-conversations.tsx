"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store/store";
import { careConversations } from "@/services/care-conversations";
import type { CareConversation, CareConversationMessage, ConversationDraft, ConversationRecipient } from "@/types/care-conversations";
import { conversationAccessDenied, conversationRoleLabel, conversationSendFailure, getConversationCopy, mergeConversationMessages } from "../../../../../packages/shared/src/utils/care-conversations";

const button = "rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50";
const input = "w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 focus:border-blue-500 focus:ring-2 focus:ring-blue-500";

export function CareConversations({ locale = "en-US", audience = "patient", visible = true }: { locale?: string; audience?: "patient" | "clinician"; visible?: boolean }) {
  const { accessToken, user } = useSelector((state: RootState) => state.auth);
  if (!accessToken || !user) return null;
  return <ConversationInbox key={user.id} token={accessToken} locale={locale} audience={audience} visible={visible} />;
}

function ConversationInbox({ token, locale, audience, visible }: { token: string; locale: string; audience: "patient" | "clinician"; visible: boolean }) {
  const copy = getConversationCopy(locale);
  const [recipients, setRecipients] = useState<ConversationRecipient[]>([]);
  const [threads, setThreads] = useState<CareConversation[]>([]);
  const [recipient, setRecipient] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
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
    } catch (failure) {
      if (request === version.current) setError(conversationAccessDenied(failure) ? "denied" : "loadError");
    } finally {
      if (request === version.current) setOpening(false);
    }
  }

  const active = threads.find((thread) => thread.id === selected);
  const name = (thread: CareConversation) => audience === "patient" ? thread.clinician_name : thread.patient_name;
  return <section className="space-y-4 rounded-xl border border-gray-200 bg-white p-5 text-sm text-gray-700">
    <p className="rounded-lg bg-yellow-100 p-3 text-yellow-800">{copy.notice}</p>
    <div className="flex flex-wrap items-end gap-3">
      <label className="min-w-0 flex-1 font-medium">{copy.recipient}
        <select className={input} value={recipient} disabled={loading || opening || sending} onChange={(event) => setRecipient(event.target.value)}>
          <option value="">{copy.choose}</option>
          {recipients.map((person) => <option key={person.id} value={person.id}>{person.name} · {conversationRoleLabel(person.role, locale)} · {person.clinic_name}</option>)}
        </select>
      </label>
      <button className={button} disabled={!recipient || loading || opening || sending} onClick={() => void open()} type="button">{opening ? copy.loading : copy.open}</button>
      <button className={button} disabled={loading || opening || sending} onClick={() => setAttempt((value) => value + 1)} type="button">{copy.refresh}</button>
    </div>
    {error && <p role="alert">{copy[error]}</p>}
    {pollFailed && <p role="alert">{copy.loadError}</p>}
    {loading ? <p role="status">{copy.loading}</p> : <>
      {!recipients.length && <p>{copy.noRecipients}</p>}
      <h2 className="text-lg font-semibold text-gray-900">{copy.threads}</h2>
      {!threads.length && <p>{copy.empty}</p>}
      <ul className="space-y-2">
        {threads.map((thread) => <li key={thread.id}>
          <button className={`${button} w-full text-left ${selected === thread.id ? "border-blue-600 bg-blue-50" : ""}`} type="button" aria-pressed={selected === thread.id} disabled={sending || opening} onClick={() => setSelected(thread.id)}>
            <span className="block font-semibold">{name(thread)} · {thread.clinic_name}</span>
            {thread.unread_count > 0 && <span className="rounded-full bg-blue-100 px-2 py-0.5 text-xs text-blue-800">{thread.unread_count} {copy.unread}</span>}
            <span className="block truncate text-gray-500">{thread.last_message_preview}</span>
          </button>
        </li>)}
      </ul>
      {active ? <ConversationThread key={active.id} token={token} thread={active} locale={locale} visible={visible}
        draft={drafts[active.id] ?? { body: "" }}
        onDraft={(draft) => setDrafts((current) => ({ ...current, [active.id]: draft }))}
        onSending={setSending}
        onRead={() => { invalidateInbox(); void refreshInbox(); }}
        onSaved={(message) => {
          invalidateInbox();
          setThreads((current) => current.map((thread) => thread.id === message.conversation_id ? { ...thread, last_message_preview: message.body, last_message_at: message.created_at } : thread));
          void refreshInbox();
        }}
      /> : <p>{copy.select}</p>}
    </>}
  </section>;
}

function ConversationThread({ token, thread, locale, visible, draft, onDraft, onSending, onRead, onSaved }: {
  token: string; thread: CareConversation; locale: string; visible: boolean; draft: ConversationDraft;
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

  return <div className="space-y-4 border-t border-gray-200 pt-4">
    <h3 className="font-semibold text-gray-900">{thread.patient_name} · {thread.clinician_name} · {thread.clinic_name}</h3>
    {error && <p role="alert">{copy[error]}</p>}
    <button className={button} disabled={sending || loading || denied} onClick={() => void load().catch(() => undefined)} type="button">{copy.refresh}</button>
    {loading && <p role="status">{copy.loading}</p>}
    {cursor && !denied && <button className={button} disabled={loading || sending} onClick={() => void load(cursor).catch(() => undefined)} type="button">{copy.older}</button>}
    {!loading && !denied && !messages.length && <p>{copy.noMessages}</p>}
    <ol className="max-h-96 space-y-3 overflow-y-auto" aria-label={copy.threads}>
      {messages.map((message) => <li key={message.id} className="rounded-xl border border-gray-200 bg-gray-50 p-3">
        <p className="text-xs text-gray-500">{message.sender_name} · {conversationRoleLabel(message.sender_role, locale)} · {thread.clinic_name} · <time dateTime={message.created_at}>{new Date(message.created_at).toLocaleString(locale)}</time></p>
        <p className="whitespace-pre-wrap break-words text-sm text-gray-800">{message.body}</p>
      </li>)}
    </ol>
    {draft.failure && <p role="alert">{copy[draft.failure]}</p>}
    {draft.failure === "mismatch" && !denied && <>
      <button className={button} type="button" onClick={() => setConfirmNewKey(true)}>{copy.prepareNew}</button>
      {confirmNewKey && <div role="alertdialog" aria-label={copy.prepareNew} className="space-y-3 rounded-lg bg-yellow-100 p-3 text-yellow-800">
        <p>{copy.confirmWarning}</p>
        <button className={button} type="button" onClick={() => { onDraft({ body: draft.body }); setConfirmNewKey(false); }}>{copy.confirmNew}</button>
        <button className={button} type="button" onClick={() => setConfirmNewKey(false)}>{copy.cancel}</button>
      </div>}
    </>}
    {!denied && thread.writable && <form onSubmit={(event) => { event.preventDefault(); void send(); }} className="space-y-3">
      <label className="block font-medium">{copy.message}
        <textarea className={input} maxLength={4000} value={draft.body} disabled={sending || Boolean(draft.clientMessageId)}
          onChange={(event) => onDraft({ body: event.target.value })} />
      </label>
      {draft.clientMessageId && !sending && draft.failure !== "mismatch" && <p>{copy.locked}</p>}
      <button className="rounded-lg bg-blue-600 px-4 py-2 font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        disabled={sending || loading || draft.failure === "mismatch" || !draft.body.trim() || draft.body.trim().length > 4000} type="submit">{sending ? copy.sending : draft.clientMessageId ? copy.retry : copy.send}</button>
    </form>}
    {!thread.writable && !denied && <p>{copy.denied}</p>}
  </div>;
}
