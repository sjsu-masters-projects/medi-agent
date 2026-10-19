/**
 * One poller per tab for a kind of data, however many components ask for it.
 *
 * - Subscribers share one request, one timer and one cached result.
 * - It fetches at most once per `intervalMs` (60 s for background data): a second subscriber,
 *   a remount, or a focus or visibility event inside that window reuses the result.
 * - It never fetches while the tab is hidden, and fetches once when the tab shows again after
 *   the interval has passed.
 * - The cache and timer end with the last subscriber, and a result belongs to the token that
 *   produced it, so signing out or in never shows the previous session's data.
 */
export interface PollSnapshot<T> {
  token: string;
  value: T;
  loaded: boolean;
}

type Fetcher<T> = (token: string) => Promise<T>;

export function createSharedPoll<T>(fetcher: Fetcher<T>, options: { intervalMs: number; fallback: T }) {
  const { intervalMs, fallback } = options;
  const listeners = new Set<(snapshot: PollSnapshot<T>) => void>();
  let token: string | null = null;
  let snapshot: PollSnapshot<T> | null = null;
  let lastStart = 0;
  let generation = 0;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let detach: (() => void) | undefined;

  const visible = () => document.visibilityState !== "hidden";
  const publish = (next: PollSnapshot<T>) => {
    snapshot = next;
    listeners.forEach((listener) => listener(next));
  };

  function load(force = false) {
    if (!token) return;
    const current = token;
    // Deduplicated: a request inside the window already answers every subscriber.
    if (!force && lastStart !== 0 && Date.now() - lastStart < intervalMs) return;
    const request = ++generation;
    lastStart = Date.now();
    fetcher(current)
      .catch(() => fallback)
      .then((value) => {
        if (request === generation && token === current) publish({ token: current, value, loaded: true });
      });
  }

  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(() => {
      if (visible()) load();
      if (listeners.size) schedule();
    }, intervalMs);
  }

  function start() {
    const nudge = () => {
      if (visible()) load();
    };
    window.addEventListener("focus", nudge);
    document.addEventListener("visibilitychange", nudge);
    detach = () => {
      window.removeEventListener("focus", nudge);
      document.removeEventListener("visibilitychange", nudge);
    };
    schedule();
  }

  function stop() {
    clearTimeout(timer);
    detach?.();
    detach = undefined;
    token = null;
    snapshot = null;
    lastStart = 0;
    generation++;
  }

  return {
    /** Subscribe for `nextToken`. Returns the unsubscribe function. */
    subscribe(nextToken: string, listener: (value: PollSnapshot<T>) => void) {
      if (token !== nextToken) {
        // A different session: drop the old result and its in-flight request.
        token = nextToken;
        snapshot = null;
        lastStart = 0;
        generation++;
      }
      listeners.add(listener);
      if (!detach) start();
      if (snapshot) listener(snapshot);
      if (visible()) load();
      return () => {
        listeners.delete(listener);
        if (!listeners.size) stop();
      };
    },
    /** Explicit user action: fetch now, ignoring the interval. */
    refresh() {
      if (listeners.size && visible()) load(true);
    },
  };
}
