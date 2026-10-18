"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { useSelector } from "react-redux";
import type { RootState } from "@/store/store";
import { ApiClientError } from "@/services/api";
import { notificationCentre } from "@/services/notification-centre";
import type { CentreItem, CentrePage, CentreSummary, NotificationCategory } from "@/types/notification-centre";

/** Background refresh while the tab is visible. Every poll re-authorizes in the database,
 * so it stays slow; opening, focusing, reading or acting refreshes at once. */
export const NOTIFICATION_POLL_MS = 60_000;
/** After failures the poll backs off (60 s, 2 min, 4 min, then 5 min) and resets on success. */
export const NOTIFICATION_MAX_BACKOFF_MS = 300_000;
/** Focus and visibility events arrive together; one refresh serves them. */
export const NOTIFICATION_MIN_GAP_MS = 10_000;

type Feed = "history" | "actions";
type Resource<T> = { data: T | null; error: string | null };
type Cache = { history: Resource<CentrePage>; actions: Resource<CentrePage>; summary: Resource<CentreSummary> };
const empty = (): Cache => ({ history: { data: null, error: null }, actions: { data: null, error: null }, summary: { data: null, error: null } });
interface CentreContext extends Cache {
  busy: boolean;
  writeError: string | null;
  /** Items left unread by the last "mark all" because they are no longer available. */
  skipped: number;
  refresh: () => Promise<void>;
  more: (feed: Feed) => Promise<void>;
  read: (id: string) => Promise<boolean>;
  readAll: () => Promise<boolean>;
  acknowledge: (item: CentreItem, note?: string) => Promise<boolean>;
  actionsCategory: NotificationCategory | "";
  filterActions: (category: NotificationCategory | "") => void;
}
const Context = createContext<CentreContext | null>(null);
export function useNotificationCentre() {
  const value = useContext(Context);
  if (!value) throw new Error("Notification centre requires its portal provider.");
  return value;
}
/** For shell chrome that can render outside the provider (for example in tests). */
export function useOptionalNotificationCentre() {
  return useContext(Context);
}

export function NotificationProvider({ children }: { children: ReactNode }) {
  const { accessToken, user } = useSelector((state: RootState) => state.auth);
  return <SessionCache key={user?.id ?? "signed-out"} token={accessToken}>{children}</SessionCache>;
}

function SessionCache({ token, children }: { token: string | null; children: ReactNode }) {
  const [cache, setCache] = useState<Cache>(empty);
  const [cacheToken, setCacheToken] = useState(token);
  const [busy, setBusy] = useState(false);
  const [writeError, setWriteError] = useState<string | null>(null);
  const [skipped, setSkipped] = useState(0);
  const [actionsCategory, setActionsCategory] = useState<NotificationCategory | "">("");
  const categoryRef = useRef<NotificationCategory | "">("");
  const generation = useRef(0);
  const inFlight = useRef(0);
  const lastStart = useRef(0);
  const failures = useRef(0);
  const alive = useRef(false);
  const session = useRef(0);
  const lock = useRef(false);
  const controller = useRef<AbortController | null>(null);
  const depth = useRef({ history: 1, actions: 1 });

  /** `background` refreshes (poll, focus) never interrupt one already running and stay quiet
   * about a failure when there is already something to show. */
  const refresh = useCallback(async (background = false) => {
    if (!token || !alive.current || lock.current) return;
    if (background && inFlight.current) return;
    const request = ++generation.current;
    inFlight.current = request; lastStart.current = Date.now();
    controller.current?.abort();
    const abort = new AbortController();
    controller.current = abort;
    async function pages(feed: Feed): Promise<CentrePage> {
      const category = feed === "actions" ? categoryRef.current : "";
      const first = await notificationCentre.list(token!, feed === "actions", undefined, abort.signal, category || undefined);
      let result = { ...first, read_snapshots: first.read_through ? [first.read_through] : [] };
      for (let page = 1; page < depth.current[feed] && result.next_cursor; page++) {
        const next = await notificationCentre.list(token!, feed === "actions", result.next_cursor, abort.signal, category || undefined);
        result = { ...first, items: [...result.items, ...next.items], next_cursor: next.next_cursor, read_snapshots: [...result.read_snapshots, ...(next.read_through ? [next.read_through] : [])] };
      }
      return result;
    }
    const results = await Promise.allSettled([pages("history"), pages("actions"), notificationCentre.summary(token, abort.signal)]);
    if (!alive.current || abort.signal.aborted || request !== generation.current) return;
    inFlight.current = 0;
    failures.current = results.some((result) => result.status === "rejected") ? Math.min(failures.current + 1, 6) : 0;
    setCache((previous) => {
      const next = { ...previous };
      const keys = ["history", "actions", "summary"] as const;
      results.forEach((result, index) => {
        const key = keys[index];
        if (result.status === "fulfilled") {
          // Each request owns the corresponding resource.
          Object.assign(next, { [key]: { data: result.value, error: null } });
        } else {
          const denied = result.reason instanceof ApiClientError && [401, 403].includes(result.reason.status);
          const quiet = background && !denied && previous[key].data !== null;
          Object.assign(next, { [key]: { data: denied ? null : previous[key].data, error: quiet ? previous[key].error : denied ? "Access to alerts is unavailable." : "Could not refresh alerts. Previously loaded data remains visible." } });
        }
      });
      return next;
    });
  }, [token]);

  useEffect(() => {
    alive.current = true;
    const identity = ++session.current;
    lock.current = false;
    void Promise.resolve().then(() => {
      if (!alive.current || identity !== session.current) return;
      depth.current = { history: 1, actions: 1 };
      categoryRef.current = ""; setActionsCategory("");
      setCache(empty()); setCacheToken(token); setBusy(false); setWriteError(null);
      if (document.visibilityState === "visible") void refresh();
    });
    let timer: number | undefined;
    const schedule = () => {
      const delay = Math.min(NOTIFICATION_POLL_MS * 2 ** failures.current, NOTIFICATION_MAX_BACKOFF_MS);
      timer = window.setTimeout(() => {
        const run = document.visibilityState === "visible" ? refresh(true) : Promise.resolve();
        void run.finally(() => { if (alive.current) schedule(); });
      }, delay);
    };
    schedule();
    const visibleRefresh = () => {
      if (document.visibilityState !== "visible" || Date.now() - lastStart.current < NOTIFICATION_MIN_GAP_MS) return;
      void refresh(true);
    };
    window.addEventListener("focus", visibleRefresh);
    document.addEventListener("visibilitychange", visibleRefresh);
    return () => {
      alive.current = false; controller.current?.abort();
      window.clearTimeout(timer);
      window.removeEventListener("focus", visibleRefresh);
      document.removeEventListener("visibilitychange", visibleRefresh);
    };
  }, [refresh, token]);

  async function write(operation: () => Promise<unknown>) {
    if (!token || cacheToken !== token || lock.current || !alive.current) return false;
    lock.current = true; generation.current++; inFlight.current = 0; controller.current?.abort();
    const identity = session.current;
    setBusy(true); setWriteError(null);
    try {
      await operation();
      if (!alive.current || identity !== session.current) return false;
      lock.current = false;
      await refresh();
      return true;
    } catch {
      if (alive.current && identity === session.current) setWriteError("The change could not be confirmed. Refresh before trying again.");
      return false;
    } finally {
      if (alive.current && identity === session.current) { lock.current = false; setBusy(false); }
    }
  }

  async function more(feed: Feed) {
    const cursor = cache[feed].data?.next_cursor;
    if (!token || !cursor || lock.current) return;
    lock.current = true; setBusy(true);
    const request = ++generation.current;
    inFlight.current = 0;
    const identity = session.current;
    controller.current?.abort();
    try {
      const category = feed === "actions" ? categoryRef.current : "";
      const page = category ? await notificationCentre.list(token, feed === "actions", cursor, undefined, category) : await notificationCentre.list(token, feed === "actions", cursor);
      if (!alive.current || identity !== session.current || request !== generation.current) return;
      depth.current[feed]++;
      setCache((previous) => {
        const existing = previous[feed].data!;
        const items = [...new Map([...existing.items, ...page.items].map((item) => [item.id, item])).values()];
        return { ...previous, [feed]: { data: { ...existing, items, next_cursor: page.next_cursor, read_snapshots: [...(existing.read_snapshots ?? []), ...(page.read_through ? [page.read_through] : [])] }, error: null } };
      });
    } catch (failure) {
      if (alive.current && identity === session.current && request === generation.current) {
        const denied = failure instanceof ApiClientError && [401, 403].includes(failure.status);
        setCache((previous) => ({ ...previous, [feed]: {
          data: denied ? null : previous[feed].data,
          error: denied ? "Access to alerts is unavailable." : "Could not load more alerts. Retry.",
        } }));
      }
    } finally { if (alive.current && identity === session.current) { lock.current = false; setBusy(false); } }
  }

  const value: CentreContext = {
    ...(cacheToken === token ? cache : empty()), busy, writeError, skipped, refresh: () => refresh(), more,
    actionsCategory,
    filterActions: (category) => {
      if (lock.current || category === categoryRef.current) return;
      categoryRef.current = category; setActionsCategory(category);
      depth.current.actions = 1;
      setCache((previous) => ({ ...previous, actions: { data: null, error: null } }));
      void refresh();
    },
    read: (id) => write(() => notificationCentre.read(token!, id)),
    readAll: () => {
      const snapshots = cache.history.data?.read_snapshots ?? [];
      const identity = session.current;
      setSkipped(0);
      return snapshots.length ? write(async () => {
        let total = 0;
        for (const snapshot of new Set(snapshots)) {
          if (!alive.current || identity !== session.current) return;
          total += (await notificationCentre.readThrough(token!, snapshot)).skipped;
        }
        if (alive.current && identity === session.current) setSkipped(total);
      }) : Promise.resolve(false);
    },
    acknowledge: (item, note) => {
      const authorized = cache.actions.data?.items.find((entry) => entry.id === item.id);
      return !cache.actions.error && authorized?.can_acknowledge && (!note || note.length <= 1000)
        ? write(() => notificationCentre.acknowledge(token!, item.id, note)) : Promise.resolve(false);
    },
  };
  return <Context.Provider value={value}>{children}</Context.Provider>;
}
