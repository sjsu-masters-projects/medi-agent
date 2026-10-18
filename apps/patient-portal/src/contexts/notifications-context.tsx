"use client";

import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store/store";
import { useSharedPatientProfile } from "@/contexts/patient-profile-context";
import { normalizeLocale, type Locale } from "@/types";
import { ApiClientError } from "@/services/api";
import { notifications } from "@/services/notifications";
import type { NotificationPage, NotificationSummary } from "@/types/notifications";
import { useInitialPatientLocale } from "@/contexts/patient-locale-context";

/** Background refresh while the tab is visible. Every poll re-authorizes in the database,
 * so it stays slow; opening, focusing, reading or acting refreshes at once. */
export const NOTIFICATION_POLL_MS = 60_000;
/** After failures the poll backs off (60 s, 2 min, 4 min, then 5 min) and resets on success. */
export const NOTIFICATION_MAX_BACKOFF_MS = 300_000;
/** Focus and visibility events arrive together (and often) on phones; one refresh serves them. */
export const NOTIFICATION_MIN_GAP_MS = 10_000;

interface NotificationState {
  locale: Locale;
  timezone: string | null;
  page: NotificationPage | null;
  summary: NotificationSummary | null;
  unread: boolean;
  loading: boolean;
  busy: boolean;
  canMarkDisplayed: boolean;
  error: "load" | "write" | null;
  /** Items left unread by the last "mark all" because they are no longer available. */
  skipped: number;
  setUnread: (unread: boolean) => void;
  refresh: () => Promise<void>;
  loadMore: () => Promise<void>;
  markRead: (id: string) => Promise<void>;
  markAllRead: () => Promise<void>;
}
const NotificationContext = createContext<NotificationState | null>(null);

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { accessToken, user } = useSelector((state: RootState) => state.auth);
  const shared = useSharedPatientProfile();
  const initialLocale = useInitialPatientLocale();
  const locale = normalizeLocale(shared?.profile?.preferredLanguage ?? initialLocale);
  // Only identity changes remount child workflows; token/locale updates clear this cache.
  return <NotificationSession key={user?.id ?? "guest"} token={accessToken} locale={locale} timezone={shared?.timezoneMissing ? null : shared?.profile?.timezone ?? null}>{children}</NotificationSession>;
}

function NotificationSession({ children, token, locale, timezone }: { children: ReactNode; token: string | null; locale: Locale; timezone: string | null }) {
  const [page, setPage] = useState<NotificationPage | null>(null);
  const [summary, setSummary] = useState<NotificationSummary | null>(null);
  const [unread, setUnread] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [canMarkDisplayed, setCanMarkDisplayed] = useState(false);
  const [error, setError] = useState<NotificationState["error"]>(null);
  const [skipped, setSkipped] = useState(0);
  const revision = useRef(0);
  const inFlight = useRef(0);
  const lastStart = useRef(0);
  const failures = useRef(0);
  const hasPage = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const mounted = useRef(true);
  const writing = useRef(false);
  const epoch = useRef(0);
  const depth = useRef(1);
  const snapshots = useRef<string[]>([]);
  const clearDeniedCache = useCallback(() => {
    snapshots.current = []; depth.current = 1; hasPage.current = false;
    setCanMarkDisplayed(false); setPage(null); setSummary(null);
  }, []);
  const invalidate = useCallback(() => { revision.current++; inFlight.current = 0; controller.current?.abort(); }, []);
  const invalidateSession = useCallback(() => { epoch.current++; invalidate(); }, [invalidate]);
  const [cacheKey, setCacheKey] = useState({ token, locale });
  if (cacheKey.token !== token || cacheKey.locale !== locale) {
    hasPage.current = false; failures.current = 0;
    setCacheKey({ token, locale }); setPage(null); setSummary(null); setError(null); setLoading(true); setBusy(false); setCanMarkDisplayed(false);
  }
  useLayoutEffect(() => {
    invalidateSession();
    depth.current = 1; snapshots.current = []; writing.current = false;
    return invalidateSession;
  }, [token, locale, invalidateSession]);
  const denied = (failure: unknown) => failure instanceof ApiClientError && [401, 403].includes(failure.status);

  /** `background` refreshes (poll, focus) never interrupt one already running, keep what is
   * shown when they fail, and stay quiet unless there is nothing to show. */
  const refresh = useCallback(async (cursor?: string, background = false) => {
    if (!token || writing.current || document.visibilityState !== "visible") return;
    if (background && inFlight.current) return;
    const request = ++revision.current;
    inFlight.current = request; lastStart.current = Date.now();
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    if (!background) setLoading(true);
    const readPages = async () => {
      const pages: NotificationPage[] = [];
      let next = cursor;
      const count = cursor ? 1 : depth.current;
      for (let index = 0; index < count; index++) {
        const result = await notifications.list(token, locale, unread, next, abort.signal);
        if (abort.signal.aborted) throw new Error("Cancelled");
        pages.push(result);
        if (!result.next_cursor) break;
        next = result.next_cursor;
      }
      const last = pages[pages.length - 1];
      return { page: { ...last, items: pages.flatMap((value) => value.items) }, tokens: pages.flatMap((value) => value.read_through ? [value.read_through] : []), depth: pages.length };
    };
    const [list, counts] = await Promise.allSettled([
      readPages(), notifications.summary(token, abort.signal),
    ]);
    if (!mounted.current || abort.signal.aborted || request !== revision.current) return;
    inFlight.current = 0;
    const failed = list.status === "rejected" || counts.status === "rejected";
    failures.current = failed ? Math.min(failures.current + 1, 6) : 0;
    if ((list.status === "rejected" && denied(list.reason)) || (counts.status === "rejected" && denied(counts.reason))) {
      clearDeniedCache(); setError("load");
    } else {
      if (list.status === "fulfilled") {
        hasPage.current = true;
        snapshots.current = cursor ? [...snapshots.current, ...list.value.tokens] : list.value.tokens;
        setCanMarkDisplayed(snapshots.current.length > 0);
        depth.current = cursor ? depth.current + 1 : list.value.depth;
        setPage((current) => cursor && current ? { ...list.value.page, items: [...current.items, ...list.value.page.items.filter((item) => !current.items.some((old) => old.id === item.id))] } : list.value.page);
      }
      // A failed count keeps the last known one; a person never sees a stale zero replaced by
      // a question mark (or an error banner) because a background poll hit a slow database.
      if (counts.status === "fulfilled") setSummary(counts.value);
      setError(failed && (!background || !hasPage.current) ? "load" : null);
    }
    setLoading(false);
  }, [token, locale, unread, clearDeniedCache]);

  useEffect(() => {
    mounted.current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const schedule = () => {
      const delay = Math.min(NOTIFICATION_POLL_MS * 2 ** failures.current, NOTIFICATION_MAX_BACKOFF_MS);
      timer = setTimeout(() => { void refresh(undefined, true).finally(() => { if (mounted.current) schedule(); }); }, delay);
    };
    // The scope changed (sign-in, language, filter): read at once, then poll.
    void refresh();
    schedule();
    const nudge = () => {
      if (Date.now() - lastStart.current < NOTIFICATION_MIN_GAP_MS) return;
      void refresh(undefined, true);
    };
    window.addEventListener("focus", nudge);
    document.addEventListener("visibilitychange", nudge);
    return () => {
      mounted.current = false; invalidate();
      clearTimeout(timer); window.removeEventListener("focus", nudge); document.removeEventListener("visibilitychange", nudge);
    };
  }, [refresh, invalidate]);

  async function write(id?: string) {
    if (!token || writing.current || (!id && !snapshots.current.length)) return;
    const captured = [...snapshots.current];
    const session = epoch.current;
    writing.current = true; setBusy(true); setError(null); setSkipped(0);
    revision.current++; inFlight.current = 0; controller.current?.abort();
    try {
      if (id) await notifications.read(token, id);
      else {
        let total = 0;
        for (const snapshot of captured) {
          if (!mounted.current || session !== epoch.current) return;
          total += (await notifications.readThrough(token, snapshot)).skipped;
        }
        if (mounted.current && session === epoch.current) setSkipped(total);
      }
    } catch (failure) {
      if (mounted.current && session === epoch.current) {
        if (denied(failure)) clearDeniedCache();
        setError("write");
      }
      return;
    } finally {
      if (session === epoch.current) {
        writing.current = false;
        if (mounted.current) { setBusy(false); setLoading(false); }
      }
    }
    if (mounted.current && session === epoch.current) await refresh();
  }

  return <NotificationContext.Provider value={{ locale, timezone, page, summary, unread, loading, busy, error, skipped, canMarkDisplayed,
    setUnread: (value) => { if (value === unread || writing.current) return; revision.current++; inFlight.current = 0; controller.current?.abort(); depth.current = 1; snapshots.current = []; hasPage.current = false; setCanMarkDisplayed(false); setPage(null); setUnread(value); },
    refresh: () => refresh(), loadMore: () => page?.next_cursor ? refresh(page.next_cursor) : Promise.resolve(),
    markRead: (id) => write(id), markAllRead: () => write(),
  }}>{children}</NotificationContext.Provider>;
}

export function useNotifications() {
  const context = useContext(NotificationContext);
  if (!context) throw new Error("Notifications require the authenticated shell provider");
  return context;
}

export function useOptionalNotifications() { return useContext(NotificationContext); }
